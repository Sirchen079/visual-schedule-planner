"""长期记忆 REST：列表/手动添加/PATCH/DELETE + enabled 开关读写。"""
from fastapi.testclient import TestClient

from zhishi.server.app import create_app


def test_memories_crud(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        # 空列表
        assert c.get("/api/memories").json() == []

        # 手动添加：source 固定 user
        r = c.post("/api/memories", json={"kind": "preference", "content": "回复尽量简短",
                                          "keywords": "回复 风格"})
        assert r.status_code == 201
        row = r.json()
        assert row["source"] == "user" and row["kind"] == "preference"
        assert row["source_conversation_id"] is None

        # 校验拒绝：kind 非法 / 空内容 / 超长
        assert c.post("/api/memories", json={"kind": "diary", "content": "x"}).status_code == 400
        assert c.post("/api/memories", json={"kind": "fact", "content": "  "}).status_code == 400
        assert c.post("/api/memories", json={"kind": "fact", "content": "长" * 301}).status_code == 400

        # PATCH：改 content/kind/keywords；404
        r = c.patch(f"/api/memories/{row['id']}", json={"content": "回复要简短并且直接", "kind": "fact"})
        assert r.status_code == 200
        assert r.json()["content"] == "回复要简短并且直接" and r.json()["kind"] == "fact"
        assert c.patch("/api/memories/999", json={"content": "无"}).status_code == 404

        # 列表按 updated_at 倒序
        c.post("/api/memories", json={"kind": "fact", "content": "第二条"})
        rows = c.get("/api/memories").json()
        assert [r["content"] for r in rows] == ["第二条", "回复要简短并且直接"]

        # DELETE：成功后 404
        assert c.delete(f"/api/memories/{row['id']}").json() == {"ok": True}
        assert c.delete(f"/api/memories/{row['id']}").status_code == 404
        assert len(c.get("/api/memories").json()) == 1


def test_memories_enabled_roundtrip(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        # 默认开（缺失视为开，settingsvc.DEFAULTS 兜底）
        assert c.get("/api/memories/enabled").json() == {"enabled": True}
        assert c.put("/api/memories/enabled", json={"enabled": False}).json() == {"enabled": False}
        assert c.get("/api/memories/enabled").json() == {"enabled": False}
        # 关闭状态落到通用设置端点，AI 侧与设置页读到同一份
        assert c.get("/api/settings").json()["feature_memory_enabled"] == "false"
        assert c.put("/api/memories/enabled", json={"enabled": True}).json() == {"enabled": True}
        assert c.get("/api/memories/enabled").json() == {"enabled": True}


def test_ai_memories_visible_in_list(tmp_path):
    """AI 工具写入的记忆同样出现在列表（用户可审可改）。"""
    from zhishi.agent.tools.memory_tools import save_memory
    with TestClient(create_app(data_dir=tmp_path)) as c:
        with c.app.state.session_factory() as db:
            save_memory(db, "fact", "AI 记下的一条长期事实")
        rows = c.get("/api/memories").json()
        assert len(rows) == 1 and rows[0]["source"] == "ai" and rows[0]["content"].startswith("AI")
