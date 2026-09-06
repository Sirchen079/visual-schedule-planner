# tests/server/test_config_create_defaults.py
"""re k3#049 观察②：request_limit 三方不一致——ConfigBody/AIConfig 列默认 30，
但 k3 实测创建后得 0。根因：前端表单硬编码显式传 request_limit: 0（bundle 实证），
直穿 pydantic 默认落库。修复：非正值（0/负）一律回退默认 30——「不传即 30，
传非法 0 也即 30」，显式合法值（>0）原样保留。"""
from fastapi.testclient import TestClient
from zhishi.server.app import create_app


def _limits(c):
    from zhishi.domain.models import AIConfig
    with c.app.state.session_factory() as db:
        return {r.name: r.request_limit for r in db.query(AIConfig).all()}


def test_create_config_request_limit_defaults_to_30(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        assert c.post("/ai/configs", json={"name": "不传", "model": "m"}).status_code == 201
        assert c.post("/ai/configs", json={"name": "硬编码零",
                                           "model": "m",
                                           "request_limit": 0}).status_code == 201
        assert c.post("/ai/configs", json={"name": "负值",
                                           "model": "m",
                                           "request_limit": -5}).status_code == 201
        limits = _limits(c)
        assert limits["不传"] == 30
        assert limits["硬编码零"] == 30, "前端实况（显式 0）仍落 0"
        assert limits["负值"] == 30


def test_create_config_request_limit_explicit_value_kept(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        r = c.post("/ai/configs", json={"name": "显式45", "model": "m",
                                        "request_limit": 45})
        assert r.status_code == 201
        assert _limits(c)["显式45"] == 45
