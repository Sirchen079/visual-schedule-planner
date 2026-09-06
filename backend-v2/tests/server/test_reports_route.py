"""报告路由：生成（TestModel 离线）/失败 422/列表/详情/删除/晨报幂等与规则降级。"""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

from zhishi.server.app import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        yield c


@pytest.fixture(autouse=True)
def _no_background_jobs(monkeypatch):
    """掐掉后台调度器在本文件所有用例中的补写（晨报/自动档首拍竞态一族根治）。"""
    from zhishi.domain import reports as reports_mod
    monkeypatch.setattr(reports_mod, "run_briefing_job", lambda *a, **k: None)
    monkeypatch.setattr(reports_mod, "should_run_briefing_now", lambda db, now=None: False)
    import zhishi.domain.autopilot as autopilot_mod
    monkeypatch.setattr(autopilot_mod, "run_autopilot", lambda *a, **k: None)


def add_enabled_config(client):
    from zhishi.domain.models import AIConfig
    with client.app.state.session_factory() as db:
        db.add(AIConfig(name="t", provider_kind="openai_compat", model="test-model",
                        base_url="http://x", enabled=True))
        db.commit()


def patch_domain_model(monkeypatch):
    import zhishi.domain.reports as reports_mod
    monkeypatch.setattr(reports_mod, "build_model",
                        lambda cfg, api_key=None: TestModel(call_tools=[]))


def test_create_daily_report_200(client, monkeypatch):
    add_enabled_config(client)
    patch_domain_model(monkeypatch)
    r = client.post("/ai/reports/daily", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["report_type"] == "daily"
    assert body["content"].strip() != ""
    assert body["model_name"] == "test-model"
    assert body["period_start"] == date.today().isoformat()


def test_create_report_without_config_400(client):
    r = client.post("/ai/reports/daily", json={})
    assert r.status_code == 400
    assert "配置" in r.json()["detail"]


def test_create_report_model_failure_422(client, monkeypatch):
    add_enabled_config(client)
    import zhishi.domain.reports as reports_mod

    def boom(cfg, api_key=None):
        raise RuntimeError("网关超时")

    monkeypatch.setattr(reports_mod, "build_model", boom)
    r = client.post("/ai/reports/daily", json={})
    assert r.status_code == 422
    assert "网关超时" in r.json()["detail"]


def test_create_report_unknown_type_422(client, monkeypatch):
    add_enabled_config(client)
    patch_domain_model(monkeypatch)
    r = client.post("/ai/reports/monthly", json={})
    assert r.status_code == 422


def test_reports_list_detail_delete(client, monkeypatch):
    add_enabled_config(client)
    patch_domain_model(monkeypatch)
    created = client.post("/ai/reports/daily", json={}).json()

    rows = client.get("/ai/reports", params={"report_type": "daily"}).json()
    assert [r["id"] for r in rows] == [created["id"]]
    assert client.get("/ai/reports", params={"report_type": "weekly"}).json() == []

    detail = client.get(f"/ai/reports/{created['id']}")
    assert detail.status_code == 200 and detail.json()["content"] == created["content"]
    assert client.get("/ai/reports/99999").status_code == 404

    assert client.delete(f"/ai/reports/{created['id']}").status_code == 204
    assert client.get(f"/ai/reports/{created['id']}").status_code == 404
    assert client.delete(f"/ai/reports/{created['id']}").status_code == 404


def test_briefing_today_rule_fallback_without_config(client):
    r = client.get("/ai/briefing/today")
    assert r.status_code == 200
    assert r.json()["model_name"] == "rule"
    assert r.json()["content"].strip() != ""


def test_briefing_today_idempotent_with_config(client, monkeypatch):
    # 启动调度器在 07:00 后可能已用规则文案生成今日晨报（符合规格的产品行为）——
    # 先清掉并禁用调度判定，保证本测试任何时刻运行都走「配置+模型」路径。
    from sqlalchemy import delete as sa_delete
    from zhishi.domain import reports as reports_mod
    from zhishi.domain.models import AIReport
    with client.app.state.session_factory() as db:
        db.execute(sa_delete(AIReport).where(AIReport.report_type == "briefing"))
        db.commit()
    monkeypatch.setattr(reports_mod, "should_run_briefing_now", lambda db, now=None: False)
    # 调度器启动首拍可能在任意异步让点补写晨报——直接把 job 本体置空，杜绝后台写入
    monkeypatch.setattr(reports_mod, "run_briefing_job", lambda *a, **k: None)

    add_enabled_config(client)
    patch_domain_model(monkeypatch)
    first = client.get("/ai/briefing/today").json()
    second = client.get("/ai/briefing/today").json()
    assert first["id"] == second["id"]
    assert first["model_name"] == "test-model"


def test_briefing_ai_failure_still_200_rule(client, monkeypatch):
    add_enabled_config(client)
    import zhishi.domain.reports as reports_mod

    def boom(cfg, api_key=None):
        raise RuntimeError("限流")

    monkeypatch.setattr(reports_mod, "build_model", boom)
    r = client.get("/ai/briefing/today")
    assert r.status_code == 200
    assert r.json()["model_name"] == "rule"
