"""steer 端点：活跃 run 才受理（无 run 409 → 前端回退常规发送）；请求体校验；
释放槽位时插话队列一并清理；会话详情把插话行归位到对应助手行之前。"""
import asyncio
import json

from fastapi.testclient import TestClient

from zhishi.server.app import create_app
from zhishi.server.routes.ai import _release_run_slot


def test_steer_requires_active_run(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        r = c.post("/ai/conversations/1/steer", json={"text": "插话", "token": "t1"})
        assert r.status_code == 409
        assert "没有进行中的任务" in r.json()["detail"]


def test_steer_body_validation(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        assert c.post("/ai/conversations/1/steer",
                      json={"text": "", "token": "t1"}).status_code == 422
        assert c.post("/ai/conversations/1/steer",
                      json={"text": "x" * 20001, "token": "t1"}).status_code == 422
        assert c.post("/ai/conversations/1/steer",
                      json={"text": "ok"}).status_code == 422   # token 必填


def test_steer_enqueues_and_release_cleans_queue(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        c.app.state.active_runs[7] = "run-x"
        c.app.state.steer_queues[7] = asyncio.Queue()
        r = c.post("/ai/conversations/7/steer", json={"text": "先看周末的", "token": "tok-1"})
        assert r.status_code == 200
        assert r.json() == {"run_id": "run-x", "accepted": True}
        text, token = c.app.state.steer_queues[7].get_nowait()
        assert (text, token) == ("先看周末的", "tok-1")

        # 流结束释放槽位：队列随 active_runs 一并清理，端点回到 409
        _release_run_slot(c.app, "run-x", 7)
        assert 7 not in c.app.state.steer_queues and 7 not in c.app.state.active_runs
        assert c.post("/ai/conversations/7/steer",
                      json={"text": "晚了", "token": "tok-2"}).status_code == 409


def test_conversation_detail_orders_steered_before_assistant(tmp_path):
    """插话行落库时间晚于该轮助手行，路由按 run_id 归位到助手行之前——
    与模型实际消化顺序（插话 → 助手续答）一致；下一轮消息保持原序。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        from zhishi.domain.models import AIConversation, AIMessage
        with c.app.state.session_factory() as db:
            conv = AIConversation(title="归位")
            db.add(conv); db.commit(); db.refresh(conv)
            cid = conv.id
            rows = [
                AIMessage(conversation_id=cid, role="user", history_json="[]",
                          display_json=json.dumps({"text": "第一问", "run_id": "r1"})),
                AIMessage(conversation_id=cid, role="assistant", history_json="[]",
                          display_json=json.dumps({"text": "回答", "run_id": "r1"})),
                AIMessage(conversation_id=cid, role="user", history_json="[]",
                          display_json=json.dumps({"text": "插话", "steered": True, "run_id": "r1"})),
                AIMessage(conversation_id=cid, role="user", history_json="[]",
                          display_json=json.dumps({"text": "第二问", "run_id": "r2"})),
            ]
            db.add_all(rows); db.commit()
        got = [(r["role"], r["display"].get("text"))
               for r in c.get(f"/ai/conversations/{cid}").json()]
        assert got == [("user", "第一问"), ("user", "插话"),
                       ("assistant", "回答"), ("user", "第二问")]
