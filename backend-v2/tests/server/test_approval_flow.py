# tests/server/test_approval_flow.py
import json
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelRequest
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from zhishi.server.app import create_app
from tests.server.test_ai_routes import parse_sse

_CALLS = {"n": 0}


async def _stream_delete(messages, info):
    """模拟模型：history 尾部无 delete_task 结果 → 发起调用；已有结果（执行/被拒）→ 收尾文本。"""
    def has_result() -> bool:
        for msg in reversed(messages):
            if isinstance(msg, ModelRequest):
                return any(getattr(p, "tool_name", None) == "delete_task" for p in msg.parts)
        return False
    if not has_result():
        _CALLS["n"] += 1
        yield {0: DeltaToolCall(name="delete_task", json_args='{"task_id": 42}',
                                tool_call_id=f"tc{_CALLS['n']}")}
    else:
        yield "好的，已按审批结果处理。"


def test_confirm_tool_triggers_approval_then_resume(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        import zhishi.server.routes.ai as ai_route

        ai_route.build_model = lambda cfg, api_key=None: FunctionModel(stream_function=_stream_delete)
        from zhishi.domain.models import AIConfig
        with c.app.state.session_factory() as db:
            db.add(AIConfig(name="t", provider_kind="openai_compat", model="t",
                            base_url="http://x", enabled=True)); db.commit()
        r = c.post("/ai/chat/stream", json={"message": "删掉任务42"})
        events = parse_sse(r.text)
        types = [e["type"] for e in events]
        assert "tool_approval_requested" in types
        approval = next(e for e in events if e["type"] == "tool_approval_requested")
        action_id = approval["action_id"]

        # 拒绝 → resolved 事件 + 状态落库；单卡批次结案即 ready（re #023 建议③）
        r2 = c.post(f"/ai/actions/{action_id}/reject")
        assert r2.status_code == 200
        assert r2.json()["ready_to_resume"] is True
        from zhishi.domain.models import AIPendingAction
        with c.app.state.session_factory() as db:
            assert db.get(AIPendingAction, action_id).status == "rejected"

        # 批准路径：再来一轮，approve 触发 resume 流（SSE）
        r3 = c.post("/ai/chat/stream", json={"message": "再删一次42"})
        events3 = parse_sse(r3.text)
        approval3 = next(e for e in events3 if e["type"] == "tool_approval_requested")
        r4 = c.post(f"/ai/actions/{approval3['action_id']}/approve")
        assert r4.status_code == 200
        # approve 的响应体本身是 resume 的 SSE 或 JSON（实现取 JSON + 单独 resume 端点均可，
        # 本测试锁定：approve 后 pending 状态变为 executed 且 run 终态不再是 awaiting_approval）
        with c.app.state.session_factory() as db:
            action = db.get(AIPendingAction, approval3["action_id"])
            assert action.status in ("confirmed", "executed")


def _seed_pending_action(c, tool_name: str, args_json: str = "{}") -> int:
    from zhishi.domain.models import AIConversation, AIPendingAction
    with c.app.state.session_factory() as db:
        conv = AIConversation(title="审批测试")
        db.add(conv); db.commit(); db.refresh(conv)
        action = AIPendingAction(conversation_id=conv.id, run_id="run-1",
                                 tool_call_id="tc1", tool_name=tool_name,
                                 args_json=args_json, status="pending")
        db.add(action); db.commit(); db.refresh(action)
        return action.id


def test_approve_grant_always_rejected_for_irrevocable(tmp_path):
    """re #019 blocker：empty_trash 审批带 grant_always → 400（不可豁免），
    不创建 grant、审批保持 pending；去掉 grant_always 的常规批准照常放行。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        from zhishi.domain.models import AIPendingAction, AIToolGrant
        action_id = _seed_pending_action(c, "empty_trash")

        r = c.post(f"/ai/actions/{action_id}/approve", json={"grant_always": True})
        assert r.status_code == 400
        assert "不可豁免" in r.json()["detail"]
        with c.app.state.session_factory() as db:
            assert db.query(AIToolGrant).count() == 0, "不可豁免工具不得落任何 grant"
            assert db.get(AIPendingAction, action_id).status == "pending"

        r2 = c.post(f"/ai/actions/{action_id}/approve")   # 一次性确认不受影响
        assert r2.status_code == 200
        with c.app.state.session_factory() as db:
            assert db.get(AIPendingAction, action_id).status == "confirmed"


def test_grant_always_still_works_for_revocable(tmp_path):
    """普通 confirm 工具的 grant_always 行为不受 blocker 修复影响。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        from zhishi.domain.models import AIToolGrant
        action_id = _seed_pending_action(c, "delete_task", args_json='{"task_id": 9}')
        r = c.post(f"/ai/actions/{action_id}/approve", json={"grant_always": True})
        assert r.status_code == 200
        with c.app.state.session_factory() as db:
            rows = db.query(AIToolGrant).all()
            assert len(rows) == 1 and rows[0].tool_name == "delete_task"
            assert rows[0].arg_pattern == '{"task_id": 9}'   # 原子参数模式


def test_approval_event_grant_available_false_for_irrevocable(tmp_path):
    """re #019：empty_trash 审批事件 grant_available=false（前端须隐藏「始终允许」）；
    同流中普通工具 delete_task 的审批事件 grant_available=true。"""
    _CALLS = {"n": 0}

    async def stream_empty_trash(messages, info):
        def has_result() -> bool:
            for msg in reversed(messages):
                if isinstance(msg, ModelRequest):
                    return any(getattr(p, "tool_name", None) in ("empty_trash", "delete_task")
                               for p in msg.parts)
            return False
        if not has_result():
            _CALLS["n"] += 1
            yield {0: DeltaToolCall(name="empty_trash", json_args="{}",
                                    tool_call_id=f"tc{_CALLS['n']}"),
                   1: DeltaToolCall(name="delete_task", json_args='{"task_id": 1}',
                                    tool_call_id=f"td{_CALLS['n']}")}
        else:
            yield "审批已处理。"

    with TestClient(create_app(data_dir=tmp_path)) as c:
        import zhishi.server.routes.ai as ai_route
        ai_route.build_model = lambda cfg, api_key=None: FunctionModel(
            stream_function=stream_empty_trash)
        from zhishi.domain.models import AIConfig
        with c.app.state.session_factory() as db:
            db.add(AIConfig(name="t", provider_kind="openai_compat", model="t",
                            base_url="http://x", enabled=True)); db.commit()
        events = parse_sse(c.post("/ai/chat/stream", json={"message": "清空回收站并删任务"}).text)
        approvals = [e for e in events if e["type"] == "tool_approval_requested"]
        by_tool = {e["tool"]: e for e in approvals}
        assert by_tool["empty_trash"]["grant_available"] is False
        assert by_tool["delete_task"]["grant_available"] is True


def _set_autonomy(c, level: str) -> None:
    from zhishi.domain import settingsvc
    with c.app.state.session_factory() as db:
        settingsvc.set_setting(db, "agent_autonomy", level)
        db.commit()


def _enable_test_model(c, stream_fn) -> None:
    import zhishi.server.routes.ai as ai_route
    from pydantic_ai.models.function import FunctionModel
    ai_route.build_model = lambda cfg, api_key=None: FunctionModel(stream_function=stream_fn)
    from zhishi.domain.models import AIConfig
    with c.app.state.session_factory() as db:
        db.add(AIConfig(name="t", provider_kind="openai_compat", model="t",
                        base_url="http://x", enabled=True))
        db.commit()


def _result_seen(messages, call_id: str) -> bool:
    """该 tool_call_id 是否已有结果部件（ToolReturn/RetryPrompt，位于 ModelRequest）。"""
    from pydantic_ai.messages import ModelRequest
    for msg in messages:
        if isinstance(msg, ModelRequest):
            if any(getattr(p, "tool_call_id", None) == call_id for p in msg.parts):
                return True
    return False


def test_same_turn_multi_approvals_resume(tmp_path):
    """re #020 k3 major：同轮 ≥2 个 confirm 级调用的 resume 回填。
    ① FunctionModel 同轮发 2 个 create_event（careful 档均 confirm 级）→ 2 张审批卡；
    ② 只批 1 张 → resume 返回 400，typed 响应体列出未决 action_id 清单；
    ③ 两张都批 → resume 成功且两个日程都落库（expand 断言）。
    re #023 建议③：approve 响应带 ready_to_resume——同批仍有 pending 时 false，
    全部结案后才 true，前端只在 ready 后开 resume 流。"""
    from pydantic_ai.models.function import DeltaToolCall

    async def stream_two_events(messages, info):
        if not _result_seen(messages, "tc1"):
            yield {0: DeltaToolCall(name="create_event",
                                    json_args='{"title": "高数", "day": "2026-09-07"}',
                                    tool_call_id="tc1"),
                   1: DeltaToolCall(name="create_event",
                                    json_args='{"title": "英语", "day": "2026-09-08"}',
                                    tool_call_id="tc2")}
        else:
            yield "两个日程都已按审批结果处理。"

    with TestClient(create_app(data_dir=tmp_path)) as c:
        _set_autonomy(c, "careful")
        _enable_test_model(c, stream_two_events)

        events = parse_sse(c.post("/ai/chat/stream", json={"message": "建两个日程"}).text)
        approvals = [e for e in events if e["type"] == "tool_approval_requested"]
        assert len(approvals) == 2, f"同轮两个 confirm 调用应落 2 张审批卡: {approvals}"
        conv_id = events[0]["conversation_id"]
        id1, id2 = approvals[0]["action_id"], approvals[1]["action_id"]

        # ② 只批第一张 → ready_to_resume=false；resume 拒绝：400 + 未决清单（typed schema）
        r1 = c.post(f"/ai/actions/{id1}/approve")
        assert r1.status_code == 200
        assert r1.json()["ready_to_resume"] is False, "同批仍有未决卡时不得 ready"
        r = c.post(f"/ai/conversations/{conv_id}/resume/stream")
        assert r.status_code == 400, f"有未决审批时 resume 应 400: {r.status_code}"
        pending = r.json().get("pending", [])
        assert [p["action_id"] for p in pending] == [id2]
        assert pending[0]["tool_name"] == "create_event"

        # ③ 第二张也批 → ready_to_resume=true → resume 成功，两个日程都落库
        r3 = c.post(f"/ai/actions/{id2}/approve")
        assert r3.status_code == 200
        assert r3.json()["ready_to_resume"] is True, "同批全部结案后应 ready"
        r2 = c.post(f"/ai/conversations/{conv_id}/resume/stream")
        assert r2.status_code == 200
        events2 = parse_sse(r2.text)
        types2 = [e["type"] for e in events2]
        assert "run_error" not in types2, f"resume 不应再崩: {events2}"
        from datetime import date
        from zhishi.domain.schedule import service as ss
        with c.app.state.session_factory() as db:
            expanded = ss.expand_events_between(db, date(2026, 9, 7), date(2026, 9, 8))
        assert {e["title"] for e in expanded} == {"高数", "英语"}


def test_resume_not_poisoned_by_earlier_turn_actions(tmp_path):
    """re #020 k3 major 报告场景复现：上一轮已执行完结案（confirmed）的审批不得回填进
    本轮 resume——旧实现把全会话已结案 action 一股脑回填，命中 pydantic-ai
    「Expected 1, got 2」UserError，run 落 error。"""
    from pydantic_ai.models.function import DeltaToolCall

    async def stream_two_rounds(messages, info):
        if not _result_seen(messages, "tc1"):
            yield {0: DeltaToolCall(name="delete_task", json_args='{"task_id": 1}',
                                    tool_call_id="tc1")}
        elif not _result_seen(messages, "tc2"):
            yield {0: DeltaToolCall(name="delete_task", json_args='{"task_id": 2}',
                                    tool_call_id="tc2")}
        else:
            yield "两轮删除都已处理。"

    with TestClient(create_app(data_dir=tmp_path)) as c:
        _enable_test_model(c, stream_two_rounds)
        from zhishi.domain.models import Task

        with c.app.state.session_factory() as db:
            db.add(Task(id=1, title="任务一")); db.add(Task(id=2, title="任务二")); db.commit()

        events = parse_sse(c.post("/ai/chat/stream", json={"message": "删任务1"}).text)
        conv_id = events[0]["conversation_id"]
        a1 = next(e for e in events if e["type"] == "tool_approval_requested")["action_id"]
        assert c.post(f"/ai/actions/{a1}/approve").status_code == 200
        events_r1 = parse_sse(c.post(f"/ai/conversations/{conv_id}/resume/stream").text)
        assert "run_error" not in [e["type"] for e in events_r1]
        from zhishi.domain.models import AIPendingAction
        with c.app.state.session_factory() as db:
            assert db.get(AIPendingAction, a1).status == "executed", (
                "re #023④：resume 消费后该批 confirmed 应转 executed")

        # 第二轮：模型再发 delete_task → 新审批卡；批准后 resume 不得被 a1 的历史结案污染
        a2 = next(e for e in events_r1 if e["type"] == "tool_approval_requested")["action_id"]
        assert c.post(f"/ai/actions/{a2}/approve").status_code == 200
        events_r2 = parse_sse(c.post(f"/ai/conversations/{conv_id}/resume/stream").text)
        types = [e["type"] for e in events_r2]
        assert "run_error" not in types, f"第二轮 resume 被 stale action 毒化: {events_r2}"
        with c.app.state.session_factory() as db:
            assert db.get(Task, 1).deleted_at is not None
            assert db.get(Task, 2).deleted_at is not None
            assert db.get(AIPendingAction, a2).status == "executed"


def test_approval_gate_reapplies_for_new_same_tool_calls_after_resume(tmp_path):
    """A3 诊断：「首轮批准后同 run 内同名工具不再落审批门」。
    无 grant 的一次性批准只对该 tool_call_id 生效——resume 后模型对同名工具的
    全新调用必须重新落审批门（新审批卡），不得静默执行。"""
    from pydantic_ai.models.function import DeltaToolCall

    async def stream_reissue(messages, info):
        if not _result_seen(messages, "tc1"):
            yield {0: DeltaToolCall(name="delete_task", json_args='{"task_id": 1}',
                                    tool_call_id="tc1")}
        elif not _result_seen(messages, "tc2"):
            yield {0: DeltaToolCall(name="delete_task", json_args='{"task_id": 2}',
                                    tool_call_id="tc2")}
        else:
            yield "完成。"

    with TestClient(create_app(data_dir=tmp_path)) as c:
        _enable_test_model(c, stream_reissue)
        from zhishi.domain.models import Task

        with c.app.state.session_factory() as db:
            db.add(Task(id=1, title="任务一")); db.add(Task(id=2, title="任务二")); db.commit()

        events = parse_sse(c.post("/ai/chat/stream", json={"message": "删任务1"}).text)
        conv_id = events[0]["conversation_id"]
        a1 = next(e for e in events if e["type"] == "tool_approval_requested")["action_id"]
        assert c.post(f"/ai/actions/{a1}/approve").status_code == 200   # 一次性批准，无 grant

        events_r = parse_sse(c.post(f"/ai/conversations/{conv_id}/resume/stream").text)
        types_r = [e["type"] for e in events_r]
        approvals = [e for e in events_r if e["type"] == "tool_approval_requested"]
        assert len(approvals) == 1, f"resume 后同名工具新调用须重新落门: {types_r}"
        assert approvals[0]["tool"] == "delete_task"
        with c.app.state.session_factory() as db:
            assert db.get(Task, 1).deleted_at is not None   # 已批准的第一次调用真实执行
            assert db.get(Task, 2) is not None and db.get(Task, 2).deleted_at is None


def test_approve_then_resume_executes_tool(tmp_path):
    """完整恢复链路：approve → resume 流 → 已批准调用直接执行（不再二次审批）。"""
    calls = {"n": 0}

    async def stream_delete(messages, info):
        def has_result() -> bool:
            for msg in reversed(messages):
                if isinstance(msg, ModelRequest):
                    return any(getattr(p, "tool_name", None) == "delete_task" for p in msg.parts)
            return False
        if not has_result():
            calls["n"] += 1
            yield {0: DeltaToolCall(name="delete_task", json_args='{"task_id": 1}',
                                    tool_call_id=f"tc{calls['n']}")}
        else:
            yield "已删除任务1。"

    with TestClient(create_app(data_dir=tmp_path)) as c:
        import zhishi.server.routes.ai as ai_route
        ai_route.build_model = lambda cfg, api_key=None: FunctionModel(stream_function=stream_delete)
        from zhishi.domain.models import AIConfig, Task
        with c.app.state.session_factory() as db:
            db.add(AIConfig(name="t", provider_kind="openai_compat", model="t",
                            base_url="http://x", enabled=True))
            db.add(Task(id=1, title="目标任务"))
            db.commit()

        r = c.post("/ai/chat/stream", json={"message": "删掉任务1"})
        events = parse_sse(r.text)
        conv_id = events[0]["conversation_id"]
        approval = next(e for e in events if e["type"] == "tool_approval_requested")

        assert c.post(f"/ai/actions/{approval['action_id']}/approve").status_code == 200
        r3 = c.post(f"/ai/conversations/{conv_id}/resume/stream")
        events3 = parse_sse(r3.text)
        types3 = [e["type"] for e in events3]
        assert "tool_call_started" in types3 and "tool_call_result" in types3
        assert "tool_approval_requested" not in types3   # 已批准调用不得二次审批
        with c.app.state.session_factory() as db:
            assert db.get(Task, 1).deleted_at is not None  # 工具真实执行


def test_resume_with_mixed_safe_and_deferred_calls(tmp_path):
    """re #028 major：同一模型响应混合「safe 直行 + confirm 待审批」调用时 resume
    不得误报「审批数据不完整」。standard 档下一轮同时发 create_event（safe 直行，
    trailing ModelRequest 已有 ToolReturnPart、不落审批表）+ delete_event（confirm
    落审批卡）：① 流暂停只出 delete_event 一张审批卡，create_event 已直行落库；
    ② 批准后 resume 成功（不再 400），delete_event 真实删除且 create_event 不重复
    执行（事件计数不变）；③ 重复 resume → 400 typed consumed + 用户可读 message。"""
    from datetime import date
    from pydantic_ai.models.function import DeltaToolCall
    from sqlalchemy import select

    async def stream_mixed(messages, info):
        if not _result_seen(messages, "tc1"):
            yield {0: DeltaToolCall(name="create_event",
                                    json_args='{"title": "周会", "day": "2026-09-07"}',
                                    tool_call_id="tc1"),
                   1: DeltaToolCall(name="delete_event", json_args='{"event_id": 1}',
                                    tool_call_id="tc2")}
        else:
            yield "日程已按审批结果处理。"

    with TestClient(create_app(data_dir=tmp_path)) as c:
        _enable_test_model(c, stream_mixed)
        from zhishi.domain.models import Event
        from zhishi.domain.schedule import service as ss

        with c.app.state.session_factory() as db:
            ss.create_event(db, title="旧日程", date=date(2026, 9, 8))

        events = parse_sse(
            c.post("/ai/chat/stream", json={"message": "建个周会并删掉旧日程"}).text)
        conv_id = events[0]["conversation_id"]
        approvals = [e for e in events if e["type"] == "tool_approval_requested"]
        # ① 仅 confirm 级 delete_event 落审批卡；safe 的 create_event standard 档直行
        assert len(approvals) == 1, f"safe 调用应直行、仅 confirm 落卡: {approvals}"
        assert approvals[0]["tool"] == "delete_event"
        with c.app.state.session_factory() as db:
            titles = set(db.scalars(select(Event.title)).all())
        assert titles == {"旧日程", "周会"}, f"create_event 应已直行落库: {titles}"

        # ② 批准 delete_event → resume 成功（修复前误 400「审批数据不完整」）
        action_id = approvals[0]["action_id"]
        r_approve = c.post(f"/ai/actions/{action_id}/approve")
        assert r_approve.status_code == 200
        assert r_approve.json()["ready_to_resume"] is True
        r = c.post(f"/ai/conversations/{conv_id}/resume/stream")
        assert r.status_code == 200, (
            f"混合批次 resume 不应被拒: {r.status_code} {r.text[:300]}")
        types = [e["type"] for e in parse_sse(r.text)]
        assert "run_error" not in types, f"resume 不应崩: {types}"
        with c.app.state.session_factory() as db:
            rows = db.scalars(select(Event)).all()
        assert {e.title for e in rows} == {"周会"}, "delete_event 应真实删除旧日程"
        assert len(rows) == 1, f"create_event 不得在 resume 中重复执行: {rows}"

        # ③ 重复 resume：幂等 400 typed consumed，响应体带用户可读 message
        r2 = c.post(f"/ai/conversations/{conv_id}/resume/stream")
        assert r2.status_code == 400
        body = r2.json()
        assert body.get("consumed") is True, f"重复 resume 应返回 typed consumed: {body}"
        assert "消费" in body.get("message", ""), f"应说明批次已消费: {body}"


def test_resume_marks_batch_executed_and_repeat_resume_idempotent(tmp_path):
    """re #023④：resume 成功启动新执行后，该批 confirmed → executed（rejected 保持
    rejected），源 AIRun.usage_json 记 resumed_by_runs 消费标记；同批重复 resume →
    400 typed（consumed=true），不重复回填、不产生新消息/新执行。"""
    from pydantic_ai.models.function import DeltaToolCall

    async def stream_two_deletes(messages, info):
        if not _result_seen(messages, "tc1"):
            yield {0: DeltaToolCall(name="delete_task", json_args='{"task_id": 1}',
                                    tool_call_id="tc1"),
                   1: DeltaToolCall(name="delete_task", json_args='{"task_id": 2}',
                                    tool_call_id="tc2")}
        else:
            yield "两个任务都已按审批结果处理。"

    with TestClient(create_app(data_dir=tmp_path)) as c:
        _set_autonomy(c, "careful")
        _enable_test_model(c, stream_two_deletes)
        from zhishi.domain.models import AIPendingAction, AIRun, AIMessage, Task

        with c.app.state.session_factory() as db:
            db.add(Task(id=1, title="任务一")); db.add(Task(id=2, title="任务二")); db.commit()

        events = parse_sse(c.post("/ai/chat/stream", json={"message": "删任务1和2"}).text)
        conv_id = events[0]["conversation_id"]
        approvals = [e for e in events if e["type"] == "tool_approval_requested"]
        assert len(approvals) == 2
        id1, id2 = approvals[0]["action_id"], approvals[1]["action_id"]

        assert c.post(f"/ai/actions/{id1}/approve").json()["ready_to_resume"] is False
        assert c.post(f"/ai/actions/{id2}/approve").json()["ready_to_resume"] is True

        r = c.post(f"/ai/conversations/{conv_id}/resume/stream")
        assert r.status_code == 200
        assert "run_error" not in [e["type"] for e in parse_sse(r.text)]

        with c.app.state.session_factory() as db:
            actions = {a.tool_call_id: a for a in db.query(AIPendingAction).all()}
            assert {a.status for a in actions.values()} == {"executed"}, (
                f"resume 消费后该批应全部 executed: {actions}")
            src_run_id = next(iter(actions.values())).run_id
            usage = json.loads(db.get(AIRun, src_run_id).usage_json)
            assert len(usage.get("resumed_by_runs", [])) == 1, (
                f"源 run 应记录恢复消费标记: {usage}")
            assert db.get(Task, 1).deleted_at is not None
            assert db.get(Task, 2).deleted_at is not None
            msg_count = db.query(AIMessage).count()

        # 重复 resume 同一批次：幂等 400 typed，不重复回填（无新消息/新执行）
        r2 = c.post(f"/ai/conversations/{conv_id}/resume/stream")
        assert r2.status_code == 400
        body = r2.json()
        assert body.get("consumed") is True, f"重复 resume 应返回 typed consumed: {body}"
        assert "消费" in body.get("message", ""), f"应说明批次已消费: {body}"
        with c.app.state.session_factory() as db:
            assert db.query(AIMessage).count() == msg_count, "重复 resume 不得新增消息"
            assert {a.status for a in db.query(AIPendingAction).all()} == {"executed"}
