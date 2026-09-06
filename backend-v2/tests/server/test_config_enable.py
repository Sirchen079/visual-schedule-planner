"""enable 无效 ID 不得清空既有启用配置。
回归锁定：①不存在 ID → 404 且原 enabled 保持；②有效 ID 切换后恰有一条 enabled。"""
from fastapi.testclient import TestClient
from zhishi.server.app import create_app


def _add_config(c, name):
    with c.app.state.session_factory() as db:
        from zhishi.domain.models import AIConfig
        row = AIConfig(name=name, provider_kind="openai_compat", model="m",
                       base_url="http://x", enabled=False)
        db.add(row); db.commit(); db.refresh(row)
        return row.id


def _enabled_ids(c):
    with c.app.state.session_factory() as db:
        from zhishi.domain.models import AIConfig
        return [row.id for row in db.query(AIConfig).all() if row.enabled]


def test_enable_unknown_id_404_keeps_existing(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        a = _add_config(c, "A")
        assert c.post(f"/ai/configs/{a}/enable").json()["ok"] is True
        r = c.post("/ai/configs/99999/enable")
        assert r.status_code == 404
        assert _enabled_ids(c) == [a], "无效 ID 清空了原启用配置"


def test_enable_switches_exactly_one(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        a = _add_config(c, "A")
        b = _add_config(c, "B")
        assert c.post(f"/ai/configs/{a}/enable").status_code == 200
        assert c.post(f"/ai/configs/{b}/enable").status_code == 200
        assert _enabled_ids(c) == [b]
