"""(k3)③：计划模式指令强化 + 受控重试。
plan_mode 下必须注入「必须提交计划」专用指令段；execution 正常结束但既无
plan_card 也无审批/错误时，以追加指令再驱动一轮（仅一次，防循环）；
run trace 的 steps 随多轮正常累加。"""
import json

from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from zhishi.agent.runtime import AgentRuntime


def make_runtime(db, model=None) -> AgentRuntime:
    if model is None:
        from pydantic_ai.models.test import TestModel
        model = TestModel(call_tools=[])
    return AgentRuntime(model=model, db=db)


def test_plan_mode_agent_instructions_injected(db):
    """plan_mode 的 agent instructions 必须含计划模式专用段；普通模式不含。"""
    rt = make_runtime(db)

    def joined(agent):
        return "\n".join(i.instruction for i in agent._instructions if isinstance(i.instruction, str))

    assert "【计划模式】" not in joined(rt._build_agent(plan_mode=False))
    plan_text = joined(rt._build_agent(plan_mode=True))
    assert "【计划模式】" in plan_text
    assert "必须调用 propose_plan" in plan_text
    assert "禁止直接文本答复" in plan_text


async def test_plan_mode_retry_after_plain_text_round(db):
    """首轮纯文本收尾（无 plan_card）→ 追加指令再驱动一轮：次轮模型输入含
    「必须调用 propose_plan」且发起 propose_plan 调用 → plan_card 出现，run 正常收敛。"""
    state = {"n": 0, "retry_input": None}

    async def scripted(messages, info):
        state["n"] += 1
        if state["n"] == 1:
            yield "这些资料我已经看完了。"      # 违规：纯文本收尾，不提交计划
        elif state["n"] == 2:
            last = [m for m in messages if isinstance(m, ModelRequest)][-1]
            state["retry_input"] = "".join(
                p.content for p in last.parts if isinstance(p, UserPromptPart))
            yield {0: DeltaToolCall(
                name="propose_plan",
                json_args=json.dumps({"title": "导入课表计划",
                                      "steps": [{"action": "读取课表", "tool": "import_document"}]},
                                     ensure_ascii=False),
                tool_call_id="p1")}
        else:
            yield "计划已提交，等待审阅。"

    rt = make_runtime(db, model=FunctionModel(stream_function=scripted))
    events = [e async for e in rt.run_stream(user_text="把课表导进去", conversation_id=None,
                                             plan_mode=True)]
    types = [e["type"] for e in events]
    assert "plan_card" in types, "受控重试后 plan_card 必须出现"
    assert state["retry_input"] is not None and "必须调用 propose_plan" in state["retry_input"]
    assert types[-1] == "done" and "run_error" not in types

    # run trace：steps 随重试轮正常累加（3 次模型请求：首轮文本 + 次轮工具 + 次轮收尾）
    from zhishi.domain.models import AIRun
    conv_id = next(e for e in events if e["type"] == "run_started")["conversation_id"]
    run_row = db.query(AIRun).filter_by(conversation_id=conv_id).one()
    assert run_row.steps == 3
    assert run_row.status == "completed"


async def test_plan_mode_retry_only_once_then_finish(db):
    """两轮纯文本仍无 plan_card → 恰好两轮后正常结束：不死循环、无 run_error。"""
    state = {"n": 0}

    async def scripted(messages, info):
        state["n"] += 1
        yield f"第{state['n']}轮纯文本，没有计划。"

    rt = make_runtime(db, model=FunctionModel(stream_function=scripted))
    events = [e async for e in rt.run_stream(user_text="hi", conversation_id=None,
                                             plan_mode=True)]
    types = [e["type"] for e in events]
    assert types[-1] == "done" and "run_error" not in types
    assert state["n"] == 2, "受控重试仅允许一轮"
    from zhishi.domain.models import AIRun
    conv_id = next(e for e in events if e["type"] == "run_started")["conversation_id"]
    assert db.query(AIRun).filter_by(conversation_id=conv_id).one().steps == 2
