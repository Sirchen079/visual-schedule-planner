"""AI token 用量：三种接口格式的 usage 解析 + 对话流程落库 + 用量统计端点。"""
import pytest

from app.models import AIUsageLog
from app.services import ai_usage_service


# ---- extract_usage 解析 ----

def test_extract_usage_openai_chat():
    payload = {"usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}}
    assert ai_usage_service.extract_usage("openai_chat", payload) == {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
    }


def test_extract_usage_openai_responses():
    payload = {"usage": {"input_tokens": 80, "output_tokens": 20, "total_tokens": 100}}
    assert ai_usage_service.extract_usage("openai_responses", payload) == {
        "prompt_tokens": 80,
        "completion_tokens": 20,
        "total_tokens": 100,
    }


def test_extract_usage_claude_messages():
    payload = {"usage": {"input_tokens": 60, "output_tokens": 10}}
    result = ai_usage_service.extract_usage("claude_messages", payload)
    assert result == {"prompt_tokens": 60, "completion_tokens": 10, "total_tokens": 70}


def test_extract_usage_missing_usage_returns_zero():
    assert ai_usage_service.extract_usage("openai_chat", {}) == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    assert ai_usage_service.extract_usage("openai_chat", {"usage": "bad"})["total_tokens"] == 0


def test_log_usage_never_raises(db_session):
    ai_usage_service.log_usage(db_session, config=None, kind="chat", payload={"usage": None})
    ai_usage_service.log_usage(db_session, config=None, kind="chat", payload={})
    rows = db_session.query(AIUsageLog).all()
    assert len(rows) == 2  # 字段缺失也照常落库（记 0），用于 untracked 统计


# ---- 对话流程：agent loop 每轮调用都记录 ----

@pytest.mark.anyio
async def test_chat_logs_token_usage(client, monkeypatch, db_session):
    from app.services import ai_client

    config = client.post(
        "/ai/configs",
        json={
            "name": "usage-test",
            "provider": "openai_responses",
            "model": "fake-model",
            "api_key": "test-key",
        },
    ).json()
    client.post(f"/ai/configs/{config['id']}/enable")

    async def fake_call_provider(_request):
        return {
            "output_text": (
                "```json\n"
                '{"reply":"好的","tools":[],"dangerous_actions":[]}'
                "\n```"
            ),
            "usage": {"input_tokens": 120, "output_tokens": 30, "total_tokens": 150},
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    resp = client.post("/ai/chat", json={"message": "你好"})
    assert resp.status_code == 200

    logs = db_session.query(AIUsageLog).all()
    assert len(logs) >= 1
    entry = logs[0]
    assert entry.kind == "chat"
    assert entry.provider == "openai_responses"
    assert entry.model == "fake-model"
    assert entry.prompt_tokens == 120
    assert entry.completion_tokens == 30
    assert entry.total_tokens == 150
    assert entry.conversation_id == resp.json()["conversation_id"]


# ---- 用量统计端点 ----

def test_token_usage_endpoint_aggregates(client, db_session):
    from datetime import datetime

    config = client.post(
        "/ai/configs",
        json={
            "name": "priced",
            "provider": "openai_chat",
            "model": "gpt-x",
            "api_key": "k",
            "price_input": 10.0,
            "price_output": 30.0,
        },
    ).json()
    db_session.add(
        AIUsageLog(
            config_id=config["id"], kind="chat", provider="openai_chat", model="gpt-x",
            prompt_tokens=1_000_000, completion_tokens=100_000, total_tokens=1_100_000,
            created_at=datetime.now(),
        )
    )
    db_session.add(
        AIUsageLog(
            config_id=None, kind="report", provider="openai_chat", model="gpt-x",
            prompt_tokens=0, completion_tokens=0, total_tokens=0,
            created_at=datetime.now(),
        )
    )
    db_session.commit()

    resp = client.get("/stats/token-usage?days=7")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["days"]) == 7
    assert body["total_prompt_tokens"] == 1_000_000
    assert body["total_tokens"] == 1_100_000
    assert body["untracked_calls"] == 1
    model = next(m for m in body["models"] if m["model"] == "gpt-x")
    assert model["call_count"] == 2
    # 成本 = 1M×10 + 0.1M×30 = 13
    assert model["estimated_cost"] == 13.0
    assert body["total_estimated_cost"] == 13.0


def test_token_usage_empty(client):
    body = client.get("/stats/token-usage?days=5").json()
    assert body["total_tokens"] == 0
    assert body["models"] == []
    assert len(body["days"]) == 5
    assert body["total_estimated_cost"] is None
