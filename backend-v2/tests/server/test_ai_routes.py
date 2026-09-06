# tests/server/test_ai_routes.py
import json
from fastapi.testclient import TestClient
from zhishi.server.app import create_app


def parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def test_chat_stream_full_flow(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        # 无 AI 配置时应给出可操作错误
        r = c.post("/ai/chat/stream", json={"message": "你好"})
        assert r.status_code == 400
        assert "配置" in r.json()["detail"]

        # 注入测试配置：直接落库 + monkeypatch build_model → TestModel
        from zhishi.infra.database import make_engine  # noqa: F401
        import zhishi.server.routes.ai as ai_route
        from pydantic_ai.models.test import TestModel
        orig = ai_route.build_model
        ai_route.build_model = lambda cfg, api_key=None: TestModel(call_tools=[])
        try:
            from zhishi.domain.models import AIConfig
            with c.app.state.session_factory() as db:
                db.add(AIConfig(name="t", provider_kind="openai_compat", model="t",
                                base_url="http://x", enabled=True)); db.commit()
            r = c.post("/ai/chat/stream", json={"message": "你好"})
            assert r.status_code == 200
            events = parse_sse(r.text)
            types = [e["type"] for e in events]
            assert types[0] == "run_started" and types[-1] == "done"
        finally:
            ai_route.build_model = orig


def test_conversations_crud(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        assert c.get("/ai/conversations").status_code == 200


def test_delete_conversation_cascades_runs_and_actions(tmp_path):
    """M3 回归：删会话须级联清理 AIRun/AIPendingAction（FK 开启下曾 IntegrityError）。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        from zhishi.domain.models import AIConversation, AIPendingAction, AIRun
        with c.app.state.session_factory() as db:
            conv = AIConversation(title="待删会话")
            db.add(conv); db.commit(); db.refresh(conv)
            db.add(AIRun(run_id="run-1", conversation_id=conv.id, status="completed"))
            db.add(AIPendingAction(conversation_id=conv.id, run_id="run-1",
                                   tool_call_id="tc1", tool_name="delete_task",
                                   args_json="{}", status="pending"))
            db.commit()
            cid = conv.id
        r = c.delete(f"/ai/conversations/{cid}")
        assert r.status_code == 204
        with c.app.state.session_factory() as db:
            assert db.get(AIConversation, cid) is None
            assert db.query(AIRun).filter_by(conversation_id=cid).count() == 0
            assert db.query(AIPendingAction).filter_by(conversation_id=cid).count() == 0


def test_skills_crud(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        assert c.post("/ai/skills", json={"name": "我的规则", "content": "回复用中文"}).status_code == 201
        rows = c.get("/ai/skills").json()
        assert any(r["name"] == "我的规则" for r in rows)


def test_grants_list_and_revoke(tmp_path):
    """re #019：「始终允许」规则必须可审计（列表）可撤销（删除）。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        from zhishi.domain.models import AIToolGrant
        with c.app.state.session_factory() as db:
            db.add(AIToolGrant(tool_name="update_task", arg_pattern='{"task_id": 1}'))
            db.add(AIToolGrant(tool_name="delete_task", arg_pattern=""))
            db.commit()
        rows = c.get("/ai/grants").json()
        assert {(x["tool_name"], x["arg_pattern"]) for x in rows} == {
            ("update_task", '{"task_id": 1}'), ("delete_task", "")}
        assert all(set(x) >= {"id", "tool_name", "arg_pattern", "created_at"} for x in rows)

        target = rows[0]["id"]
        assert c.delete(f"/ai/grants/{target}").status_code == 204
        assert c.delete(f"/ai/grants/{target}").status_code == 404   # 重复删除
        remaining = c.get("/ai/grants").json()
        assert len(remaining) == 1 and target not in {x["id"] for x in remaining}


def test_cancel_unknown_run(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        r = c.post("/ai/runs/whatever/cancel")
        assert r.status_code == 200 and r.json()["ok"] is False  # 幂等：未知 run 返回 ok:false


def test_chat_stream_concurrent_409(tmp_path):
    """同会话并发锁：active_runs 已有条目时返回 409。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        import zhishi.server.routes.ai as ai_route
        from pydantic_ai.models.test import TestModel
        orig = ai_route.build_model
        ai_route.build_model = lambda cfg, api_key=None: TestModel(call_tools=[])
        try:
            from zhishi.domain.models import AIConfig
            with c.app.state.session_factory() as db:
                db.add(AIConfig(name="t", provider_kind="openai_compat", model="t",
                                base_url="http://x", enabled=True)); db.commit()
            c.app.state.active_runs[7] = "running-run-id"   # 模拟会话 7 进行中
            r = c.post("/ai/chat/stream", json={"message": "hi", "conversation_id": 7})
            assert r.status_code == 409
        finally:
            ai_route.build_model = orig


def test_chat_stream_second_turn_carries_history(tmp_path, monkeypatch):
    """M1 回归：同一会话第二次 chat 时，模型输入必须包含第一轮的
    user/assistant 内容（多轮记忆）；新会话首轮无 history。"""
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
    import zhishi.server.routes.ai as ai_route
    from pydantic_ai.models.function import FunctionModel

    calls: list[list] = []

    async def scripted(messages, info):
        calls.append(list(messages))
        yield f"回复{len(calls)}"

    monkeypatch.setattr(ai_route, "build_model",
                        lambda cfg, api_key=None: FunctionModel(stream_function=scripted))
    with TestClient(create_app(data_dir=tmp_path)) as c:
        from zhishi.domain.models import AIConfig
        with c.app.state.session_factory() as db:
            db.add(AIConfig(name="t", provider_kind="openai_compat", model="t",
                            base_url="http://x", enabled=True)); db.commit()

        r1 = c.post("/ai/chat/stream", json={"message": "第一轮问题"})
        assert r1.status_code == 200
        cid = next(e for e in parse_sse(r1.text) if e["type"] == "run_started")["conversation_id"]

        r2 = c.post("/ai/chat/stream", json={"message": "第二轮问题", "conversation_id": cid})
        assert r2.status_code == 200

    # 首轮：无 history，仅本条用户消息
    assert len(calls[0]) == 1
    # 次轮：历史 + 新消息，且包含第一轮 user/assistant 文本
    assert len(calls[1]) >= 3
    texts: list[str] = []
    for m in calls[1]:
        parts = m.parts if isinstance(m, (ModelRequest, ModelResponse)) else []
        for p in parts:
            content = getattr(p, "content", None)
            if isinstance(content, str):
                texts.append(content)
    blob = "\n".join(texts)
    assert "第一轮问题" in blob
    assert "回复1" in blob
    assert "第二轮问题" in blob
