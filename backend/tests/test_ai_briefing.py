"""每日晨报：幂等、AI 生成、规则降级、用量记录。"""
import pytest

from app.models import AIReport, AIUsageLog


def _seed_today_tasks(client):
    from datetime import datetime, timedelta

    now = datetime.now()
    client.post("/tasks", json={"title": "今日必办", "due_date": now.isoformat()})
    client.post(
        "/tasks",
        json={"title": "逾期旧账", "due_date": (now - timedelta(days=2)).isoformat()},
    )


def test_briefing_without_config_returns_rule_text(client):
    _seed_today_tasks(client)
    resp = client.get("/ai/briefing/today")
    assert resp.status_code == 200
    body = resp.json()
    assert body["report_type"] == "briefing"
    assert body["model_name"] == "规则模板"
    assert "晨报" in body["content"]
    assert "今日必办" in body["content"]
    assert "逾期旧账" in body["content"]


def test_briefing_idempotent_same_day(client):
    first = client.get("/ai/briefing/today").json()
    second = client.get("/ai/briefing/today").json()
    assert first["id"] == second["id"]
    count = client.get("/ai/reports?report_type=briefing").json()
    assert len(count) == 1


@pytest.mark.anyio
async def test_briefing_with_config_uses_model_and_logs_usage(
    client, monkeypatch, db_session
):
    from app.services import ai_client

    config = client.post(
        "/ai/configs",
        json={
            "name": "briefing",
            "provider": "openai_responses",
            "model": "fake-model",
            "api_key": "k",
        },
    ).json()
    client.post(f"/ai/configs/{config['id']}/enable")

    async def fake_call_provider(_request):
        return {
            "output_text": "早上好，今天先收掉「今日必办」。",
            "usage": {"input_tokens": 50, "output_tokens": 20, "total_tokens": 70},
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    _seed_today_tasks(client)
    resp = client.get("/ai/briefing/today")
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == "早上好，今天先收掉「今日必办」。"
    assert body["model_name"] == "fake-model"

    logs = db_session.query(AIUsageLog).filter(AIUsageLog.kind == "briefing").all()
    assert len(logs) == 1
    assert logs[0].total_tokens == 70


@pytest.mark.anyio
async def test_briefing_falls_back_to_rule_text_on_provider_error(
    client, monkeypatch
):
    from app.services import ai_client

    config = client.post(
        "/ai/configs",
        json={
            "name": "broken",
            "provider": "openai_chat",
            "model": "m",
            "api_key": "k",
        },
    ).json()
    client.post(f"/ai/configs/{config['id']}/enable")

    async def broken_provider(_request):
        raise RuntimeError("网络不可达")

    monkeypatch.setattr(ai_client, "call_provider", broken_provider)
    _seed_today_tasks(client)
    resp = client.get("/ai/briefing/today")
    assert resp.status_code == 200  # 静默降级，绝不打扰
    assert resp.json()["model_name"] == "规则模板"
    assert "今日必办" in resp.json()["content"]


def test_briefing_does_not_pollute_daily_report_list(client):
    client.get("/ai/briefing/today")
    daily = client.get("/ai/reports?report_type=daily").json()
    assert all(r["report_type"] == "daily" for r in daily)
    briefings = client.get("/ai/reports?report_type=briefing").json()
    assert len(briefings) == 1
