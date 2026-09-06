# tests/server/test_skills_disable_active.py
"""re k3#049 观察①：新增 POST /ai/skills/disable-active——一键停用当前激活的
用户技能（内置技能不动）；instructions 组装按 enabled 过滤（prompts._skill_text），
停用后内容自然退出系统提示。无激活技能时幂等 ok。"""
from fastapi.testclient import TestClient
from zhishi.server.app import create_app


def _skills(c):
    return {s["name"]: s for s in c.get("/ai/skills").json()}


def test_disable_active_deactivates_user_skill_keeps_builtin(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        sk = c.post("/ai/skills", json={"name": "我的写作", "description": "自建",
                                        "content": "写作时请用短句。"}).json()
        assert c.post(f"/ai/skills/{sk['id']}/enable").json() == {"ok": True}
        before = _skills(c)
        builtin = [s for s in before.values() if s["is_builtin"]]
        assert builtin and all(s["enabled"] for s in builtin)   # 内置启动即激活
        assert before["我的写作"]["enabled"] is True

        r = c.post("/ai/skills/disable-active")
        assert r.status_code == 200
        assert r.json() == {"ok": True}   # EnableOut exclude_none，实形 {ok:true}
        after = _skills(c)
        assert after["我的写作"]["enabled"] is False
        assert all(s["enabled"] for s in after.values() if s["is_builtin"]), "内置被误停用"
        assert not [s for s in after.values()
                    if not s["is_builtin"] and s["enabled"]], "仍有用户技能激活"


def test_disable_active_removes_content_from_instructions_and_idempotent(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        from zhishi.agent.prompts import build_instructions
        sk = c.post("/ai/skills", json={"name": "短句", "content": "写作时请用短句。"}).json()
        c.post(f"/ai/skills/{sk['id']}/enable")
        with c.app.state.session_factory() as db:
            assert "写作时请用短句。" in build_instructions(db)

        assert c.post("/ai/skills/disable-active").json() == {"ok": True}
        with c.app.state.session_factory() as db:
            text = build_instructions(db)
        assert "写作时请用短句。" not in text
        assert "【技能：短句】" not in text

        # 幂等：已无激活技能再停用仍 ok:true，状态不变
        assert c.post("/ai/skills/disable-active").json() == {"ok": True}
        assert not [s for s in _skills(c).values()
                    if not s["is_builtin"] and s["enabled"]]
