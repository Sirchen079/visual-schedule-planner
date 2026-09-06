# tests/server/test_plan_mode.py
"""计划模式：plan_mode 下模型只挂只读工具 + propose_plan；
propose_plan 触发 plan_card 事件；批准后以普通模式注入执行。"""
import json
from types import SimpleNamespace
from fastapi.testclient import TestClient
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from zhishi.server.app import create_app
from tests.server.test_ai_routes import parse_sse

_STEPS = [{"action": "读取课表", "tool": "import_document", "reason": "先看内容"}]


def _patch_model(monkeypatch, seen=None, tail_text="计划已提交，等待用户审阅"):
    """脚本化模型：首轮发 propose_plan 调用（可捕获工具清单），次轮收尾文本。"""
    step = {"n": 0}

    async def scripted(messages, info):
        step["n"] += 1
        if step["n"] == 1:
            if seen is not None:
                seen["names"] = {t.name for t in info.function_tools}
            yield {0: DeltaToolCall(
                name="propose_plan",
                json_args=json.dumps({"title": "导入课表计划", "steps": _STEPS},
                                     ensure_ascii=False),
                tool_call_id="p1")}
        else:
            yield tail_text

    import zhishi.server.routes.ai as ai_route
    monkeypatch.setattr(ai_route, "build_model",
                        lambda cfg, api_key=None: FunctionModel(stream_function=scripted))


def _seed_config(c):
    from zhishi.domain.models import AIConfig
    with c.app.state.session_factory() as db:
        db.add(AIConfig(name="t", provider_kind="openai_compat", model="t",
                        base_url="http://x", enabled=True)); db.commit()


def test_plan_mode_emits_plan_card_and_approve_executes(tmp_path, monkeypatch):
    seen = {}
    with TestClient(create_app(data_dir=tmp_path)) as c:
        _patch_model(monkeypatch, seen=seen)
        _seed_config(c)

        r = c.post("/ai/chat/stream", json={"message": "把课表导进去", "plan_mode": True})
        events = parse_sse(r.text)
        card = next(e for e in events if e["type"] == "plan_card")
        assert card["title"] == "导入课表计划" and card["steps"]
        assert card["steps"][0]["tool"] == "import_document"
        # 计划模式工具门：只读工具 + propose_plan 可用，confirm/safe 写类不注册
        assert "propose_plan" in seen["names"] and "list_tasks" in seen["names"]
        assert "import_timetable" not in seen["names"] and "delete_task" not in seen["names"]

        cid = next(e for e in events if e["type"] == "run_started")["conversation_id"]
        r2 = c.post(f"/ai/conversations/{cid}/plans/{card['plan_id']}/approve", json={})
        assert r2.status_code == 200
        # 批准后：计划内容作为指令注入，切回普通模式执行（批准即收 200 + run 启动事件）
        events2 = parse_sse(r2.text)
        assert events2[0]["type"] == "run_started"
        # 批准的执行消息落在同一会话
        from zhishi.domain.models import AIMessage
        with c.app.state.session_factory() as db:
            msgs = db.query(AIMessage).filter_by(role="user").order_by(AIMessage.id).all()
            texts = [json.loads(m.display_json)["text"] for m in msgs]
        assert any("按以下计划执行" in t and "读取课表" in t for t in texts)


def test_plan_reject_marks_rejected(tmp_path, monkeypatch):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        _patch_model(monkeypatch, tail_text="计划已提交")
        _seed_config(c)

        r = c.post("/ai/chat/stream", json={"message": "把课表导进去", "plan_mode": True})
        events = parse_sse(r.text)
        card = next(e for e in events if e["type"] == "plan_card")
        cid = next(e for e in events if e["type"] == "run_started")["conversation_id"]
        r2 = c.post(f"/ai/conversations/{cid}/plans/{card['plan_id']}/reject")
        assert r2.status_code == 200 and r2.json()["ok"] is True
        from zhishi.domain.models import AIConversation
        with c.app.state.session_factory() as db:
            conv = db.get(AIConversation, cid)
            plans = json.loads(conv.meta_json)["plans"]
        assert plans[0]["status"] == "rejected"


def _propose_then(c, monkeypatch):
    _patch_model(monkeypatch)
    _seed_config(c)
    r = c.post("/ai/chat/stream", json={"message": "把课表导进去", "plan_mode": True})
    events = parse_sse(r.text)
    card = next(e for e in events if e["type"] == "plan_card")
    cid = next(e for e in events if e["type"] == "run_started")["conversation_id"]
    return cid, card["plan_id"]


def _plan_status(c, cid):
    from zhishi.domain.models import AIConversation
    with c.app.state.session_factory() as db:
        conv = db.get(AIConversation, cid)
        return json.loads(conv.meta_json)["plans"][0]["status"]


def test_approve_409_compensates_back_to_proposed(tmp_path, monkeypatch):
    """re #013 major：批准时同会话已有 active run（409）→ 计划状态须回滚 proposed 可重试。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        cid, plan_id = _propose_then(c, monkeypatch)
        c.app.state.active_runs[cid] = "running-other"          # 模拟并发 run
        r = c.post(f"/ai/conversations/{cid}/plans/{plan_id}/approve", json={})
        assert r.status_code == 409
        assert _plan_status(c, cid) == "proposed", "409 后计划被卡在 approved，不可重试"
        c.app.state.active_runs.pop(cid, None)                  # 并发解除后重试应成功
        r2 = c.post(f"/ai/conversations/{cid}/plans/{plan_id}/approve", json={})
        assert r2.status_code == 200


def test_approve_model_failure_compensates_back_to_proposed(tmp_path, monkeypatch):
    """re #013 major：批准后启动链异常（模型初始化失败）→ 计划回滚 proposed。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        cid, plan_id = _propose_then(c, monkeypatch)
        import zhishi.server.routes.ai as ai_route

        def boom(cfg, api_key=None):
            raise RuntimeError("模型初始化失败")

        monkeypatch.setattr(ai_route, "build_model", boom)
        r = c.post(f"/ai/conversations/{cid}/plans/{plan_id}/approve", json={})
        assert r.status_code in (500, 502)
        assert _plan_status(c, cid) == "proposed", "启动失败后计划被卡在 approved"
        assert cid not in c.app.state.active_runs, "初始化失败后并发锁泄漏（re #016）"
        # 注意：不能用 monkeypatch.undo()——它会把 build_model 漏出到真实实现
        # （测试配置无 API key，必然 500；全量跑能过只因前置测试泄漏了 stub）。
        # 这里显式重挂脚本化模型，保证测试自封闭、单独跑也成立。
        _patch_model(monkeypatch, tail_text="按计划执行完毕")
        r2 = c.post(f"/ai/conversations/{cid}/plans/{plan_id}/approve", json={})
        assert r2.status_code == 200


def test_plan_lookup_scoped_by_conversation(tmp_path, monkeypatch):
    """M2 回归：plan_id 在会话内自增，跨会话必然撞号——批准/拒绝必须按
    (conversation_id, plan_id) 定位，批准 A 的计划不得误动 B 的同名号计划。"""
    from zhishi.domain.models import AIConversation
    from zhishi.agent.tools import macro
    with TestClient(create_app(data_dir=tmp_path)) as c:
        _seed_config(c)
        with c.app.state.session_factory() as db:
            conv_a = AIConversation(title="A"); conv_b = AIConversation(title="B")
            db.add_all([conv_a, conv_b]); db.commit(); db.refresh(conv_a); db.refresh(conv_b)
            ctx_a = SimpleNamespace(deps=SimpleNamespace(conversation_id=conv_a.id, emit=None))
            ctx_b = SimpleNamespace(deps=SimpleNamespace(conversation_id=conv_b.id, emit=None))
            macro.propose_plan(db, ctx_a, title="会话A的计划", steps=[{"action": "x"}])
            macro.propose_plan(db, ctx_b, title="会话B的计划", steps=[{"action": "y"}])
        aid, bid = conv_a.id, conv_b.id
        # 两个会话各有一个 plan_id=1：旧实现全库按 ID 找会撞车

        # 不存在的组合 → 404（计划号不存在 / 会话不存在），不产生副作用
        assert c.post(f"/ai/conversations/{aid}/plans/99/approve", json={}).status_code == 404
        assert c.post(f"/ai/conversations/9999/plans/1/reject").status_code == 404
        with c.app.state.session_factory() as db:
            assert json.loads(db.get(AIConversation, aid).meta_json)["plans"][0]["status"] == "proposed"

        # 批准 A 的 plan 1：只结案 A 的计划，B 的 plan 1 不受影响
        _patch_model(monkeypatch, tail_text="按计划执行完毕")
        r2 = c.post(f"/ai/conversations/{aid}/plans/1/approve", json={})
        assert r2.status_code == 200
        with c.app.state.session_factory() as db:
            meta_a = json.loads(db.get(AIConversation, aid).meta_json)
            meta_b = json.loads(db.get(AIConversation, bid).meta_json)
        assert meta_a["plans"][0]["status"] == "approved"
        assert meta_b["plans"][0]["status"] == "proposed"   # B 不受影响

        # reject 同样限定作用域
        r3 = c.post(f"/ai/conversations/{bid}/plans/1/reject")
        assert r3.status_code == 200 and r3.json()["ok"] is True
        with c.app.state.session_factory() as db:
            meta_a = json.loads(db.get(AIConversation, aid).meta_json)
            meta_b = json.loads(db.get(AIConversation, bid).meta_json)
        assert meta_a["plans"][0]["status"] == "approved"   # A 已批准的不被改判
        assert meta_b["plans"][0]["status"] == "rejected"


def test_propose_plan_persists_to_conversation_meta(db):
    """直调 propose_plan：计划落会话 meta（v1 不建新表），plan_id 自增。
    上下文经 per-run deps 注入（stub ctx 取代旧 macro.bind 全局绑定）。"""
    from types import SimpleNamespace
    from zhishi.domain.models import AIConversation
    from zhishi.agent.tools import macro
    conv = AIConversation(title="t"); db.add(conv); db.commit(); db.refresh(conv)
    ctx = SimpleNamespace(deps=SimpleNamespace(conversation_id=conv.id, emit=None))
    out = json.loads(macro.propose_plan(db, ctx, title="计划A", steps=[{"action": "x"}]))
    assert out["plan_id"] == 1
    out2 = json.loads(macro.propose_plan(db, ctx, title="计划B", steps=[]))
    assert out2["plan_id"] == 2      # 自增
    db.expire(conv)
    plans = json.loads(db.get(AIConversation, conv.id).meta_json)["plans"]
    assert [p["title"] for p in plans] == ["计划A", "计划B"]
