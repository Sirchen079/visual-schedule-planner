import json
import pytest
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel
from zhishi.agent.runtime import AgentRuntime, AgentDeps


def make_runtime(db, model=None) -> AgentRuntime:
    return AgentRuntime(model=model or TestModel(call_tools=[]), db=db)


async def test_plain_text_run_emits_contract_sequence(db):
    rt = make_runtime(db)
    events = [e async for e in rt.run_stream(user_text="你好", conversation_id=None)]
    types = [e["type"] for e in events]
    assert types[0] == "run_started"
    assert "text_delta" in types
    assert types[-1] == "done"
    assert "run_completed" in types


async def test_stage_events_present(db):
    rt = make_runtime(db)
    events = [e async for e in rt.run_stream(user_text="你好", conversation_id=None)]
    stages = [e["stage"] for e in events if e["type"] == "stage_changed"]
    assert "preparing" in stages and "finalizing" in stages


async def test_tool_call_events_via_function_model(db):
    from pydantic_ai.models.function import DeltaToolCall
    state = {"step": 0}

    async def stream_tools(messages, info):  # 模拟：先调用一次 get_current_time，再收尾
        state["step"] += 1
        if state["step"] == 1:
            yield {0: DeltaToolCall(name="get_current_time", json_args="{}", tool_call_id="tc1")}
        else:
            yield "时间已校准"

    rt = make_runtime(db, model=FunctionModel(stream_function=stream_tools))
    events = [e async for e in rt.run_stream(user_text="现在几点", conversation_id=None)]
    types = [e["type"] for e in events]
    assert "tool_call_started" in types
    idx = types.index("tool_call_result")
    assert json.loads(events[idx]["result_preview"])["now"]  # 工具真实执行且结果回传


async def test_run_persists_messages(db):
    from zhishi.domain.models import AIMessage
    rt = make_runtime(db)
    events = [e async for e in rt.run_stream(user_text="你好", conversation_id=None)]
    run_started = next(e for e in events if e["type"] == "run_started")
    conv_id = run_started["conversation_id"]
    msgs = db.query(AIMessage).filter_by(conversation_id=conv_id).all()
    assert any(m.role == "user" for m in msgs)
    assert any(m.role == "assistant" and m.history_json != "[]" for m in msgs)


async def test_function_model_pure_text_persists_assistant_message(db):
    """回归锁定：FunctionModel 纯文本流下 run.result 正常收敛（done_reason=model_done），
    assistant 消息（含 history）必须落库。pydantic-ai 2.38 的 AgentRun.result 在
    节点迭代结束后即已填充，runtime 在 async with 块内读取是正确时机。"""
    from zhishi.domain.models import AIMessage, AIRun

    async def pure_text(messages, info):
        yield "纯文本回复，无工具调用"

    rt = make_runtime(db, model=FunctionModel(stream_function=pure_text))
    events = [e async for e in rt.run_stream(user_text="hi", conversation_id=None)]
    run_started = next(e for e in events if e["type"] == "run_started")
    conv_id = run_started["conversation_id"]

    run_row = db.query(AIRun).filter_by(conversation_id=conv_id).one()
    assert run_row.done_reason == "model_done"
    assert run_row.status == "completed"

    msgs = db.query(AIMessage).filter_by(conversation_id=conv_id).order_by(AIMessage.id).all()
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert "纯文本回复" in json.loads(msgs[-1].display_json)["text"]
    assert msgs[-1].history_json != "[]"   # 续跑所需的边界消息已保存


# ---- Bug B 回归：工具执行失败不得毒化 Session，错误文本回灌模型 ----

async def test_tool_failure_returns_error_and_next_tool_call_succeeds(db, monkeypatch):
    """第一次 create_event 中途失败（flush 异常模拟）→ 工具结果 ok=False 含错误文本、
    流不崩；第二次调用在全新 Session 上正常建成；run 收口 completed 而非 run_error。"""
    from datetime import date as _date
    from sqlalchemy.exc import IntegrityError
    from zhishi.domain.models import AIRun, Event
    from zhishi.domain.schedule import service as ss
    from pydantic_ai.models.function import DeltaToolCall

    real_create = ss.create_event
    seen_sessions: list = []
    calls = {"n": 0}

    def flaky_create(tool_db, **fields):
        seen_sessions.append(tool_db)
        calls["n"] += 1
        if calls["n"] == 1:
            # 模拟中途失败：session 里残留未提交写入后再抛 IntegrityError
            tool_db.add(Event(title="毒化残留", date=_date(2026, 9, 8)))
            raise IntegrityError("INSERT INTO events", {}, Exception("UNIQUE constraint failed"))
        return real_create(tool_db, **fields)

    monkeypatch.setattr(ss, "create_event", flaky_create)

    step = {"n": 0}

    async def scripted(messages, info):
        step["n"] += 1
        if step["n"] == 1:   # ① 必失败的工具调用
            yield {0: DeltaToolCall(name="create_event", tool_call_id="t1",
                                    json_args=json.dumps(
                                        {"title": "组会", "day": "2026-09-08",
                                         "start_time": "09:00", "end_time": "10:00"}))}
        elif step["n"] == 2:  # ② 模型自纠：重试同一操作
            yield {0: DeltaToolCall(name="create_event", tool_call_id="t2",
                                    json_args=json.dumps(
                                        {"title": "组会", "day": "2026-09-08",
                                         "start_time": "09:00", "end_time": "10:00"}))}
        else:
            yield "第一次失败已恢复，日程已建成。"

    rt = make_runtime(db, model=FunctionModel(stream_function=scripted))
    events = [e async for e in rt.run_stream(user_text="建个日程", conversation_id=None)]
    types = [e["type"] for e in events]

    # 流不崩：无 run_error，正常收口 completed
    assert "run_error" not in types and types[-1] == "done"
    run_started = next(e for e in events if e["type"] == "run_started")
    run_row = db.query(AIRun).filter_by(
        conversation_id=run_started["conversation_id"]).one()
    assert run_row.status == "completed" and run_row.done_reason == "model_done"

    # 失败以错误文本回灌模型（工具结果 ok=False），而非抛异常中断
    results = [e for e in events if e["type"] == "tool_call_result"]
    first = json.loads(results[0]["result_preview"])
    assert first["ok"] is False and "UNIQUE constraint failed" in first["error"]
    second = json.loads(results[1]["result_preview"])
    assert second.get("event_id")

    # 每次工具调用独立 Session（互不相同、非 run 级 db），用完即关：
    # is_active=True（未毒化）且事务/连接已释放（in_transaction=False，close 生效）
    assert len(seen_sessions) == 2
    assert seen_sessions[0] is not seen_sessions[1]
    assert seen_sessions[0] is not db and seen_sessions[1] is not db
    assert all(s.is_active and not s.in_transaction() for s in seen_sessions)

    # 失败调用的残留写入已回滚，不落库；成功调用真实落库
    assert [e.title for e in db.query(Event).all()] == ["组会"]
