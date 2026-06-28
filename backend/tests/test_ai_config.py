import json

from sqlalchemy import inspect

from app.models import AIConfig


def test_ai_tables_exist(client):
    from app.database import engine

    tables = set(inspect(engine).get_table_names())
    assert "ai_configs" in tables
    assert "ai_skills" in tables
    assert "ai_conversations" in tables
    assert "ai_messages" in tables
    assert "ai_pending_actions" in tables


def test_create_ai_config_masks_api_key(client):
    resp = client.post(
        "/ai/configs",
        json={
            "name": "OpenAI",
            "assistant_name": "知时助手",
            "persona": "用简洁、冷静的方式协助用户。",
            "provider": "openai_chat",
            "model": "gpt-test",
            "api_key": "sk-secret-value",
            "base_url": "https://api.example.com",
            "full_url": None,
            "proxy_url": "http://127.0.0.1:7890",
            "extra_headers": {},
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["api_key_masked"] == "sk-***alue"
    assert body["persona"] == "用简洁、冷静的方式协助用户。"
    assert body["proxy_url"] == "http://127.0.0.1:7890"
    assert "api_key" not in body


def test_create_ai_config_saves_native_web_search_options(client, db_session):
    resp = client.post(
        "/ai/configs",
        json={
            "name": "Kimi",
            "provider": "claude_messages",
            "model": "kimi-for-coding",
            "api_key": "sk-secret-value",
            "native_web_search_enabled": True,
            "native_web_search_options": {
                "tools": [
                    {
                        "type": "web_search_20250305",
                        "name": "web_search",
                        "max_uses": 2,
                    }
                ],
                "tool_choice": {"type": "auto"},
            },
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["native_web_search_enabled"] is True
    assert body["native_web_search_options"]["tools"][0]["max_uses"] == 2

    stored = db_session.get(AIConfig, body["id"])
    assert stored.native_web_search_enabled is True
    assert json.loads(stored.native_web_search_options)["tool_choice"] == {"type": "auto"}


def test_create_ai_config_saves_search_enhancement_switch(client, db_session):
    resp = client.post(
        "/ai/configs",
        json={
            "name": "Kimi Search",
            "provider": "claude_messages",
            "model": "kimi-for-coding",
            "api_key": "sk-secret-value",
            "search_enhancement_enabled": True,
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["search_enhancement_enabled"] is True

    stored = db_session.get(AIConfig, body["id"])
    assert stored.search_enhancement_enabled is True


def test_ai_config_masks_sensitive_extra_headers_and_preserves_on_update(
    client, db_session
):
    resp = client.post(
        "/ai/configs",
        json={
            "name": "Proxy",
            "assistant_name": "知时助手",
            "provider": "openai_chat",
            "model": "gpt-test",
            "api_key": "sk-secret-value",
            "proxy_url": "http://127.0.0.1:7890",
            "extra_headers": {
                "Authorization": "Bearer proxy-secret",
                "x-api-key": "header-key",
                "X-Trace": "trace-id",
            },
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["extra_headers"]["Authorization"] == "***"
    assert body["extra_headers"]["x-api-key"] == "***"
    assert body["extra_headers"]["X-Trace"] == "trace-id"

    update = client.put(
        f"/ai/configs/{body['id']}",
        json={"name": "Proxy Updated", "extra_headers": body["extra_headers"]},
    )
    assert update.status_code == 200
    db_session.expire_all()
    stored = db_session.get(AIConfig, body["id"])
    headers = json.loads(stored.extra_headers)
    assert headers["Authorization"] == "Bearer proxy-secret"
    assert headers["x-api-key"] == "header-key"
    assert headers["X-Trace"] == "trace-id"
    assert stored.proxy_url == "http://127.0.0.1:7890"


def test_enable_ai_config_disables_other_configs(client):
    first = client.post(
        "/ai/configs",
        json={
            "name": "A",
            "provider": "openai_chat",
            "model": "m1",
            "api_key": "key-a",
        },
    ).json()
    second = client.post(
        "/ai/configs",
        json={
            "name": "B",
            "provider": "claude_messages",
            "model": "m2",
            "api_key": "key-b",
        },
    ).json()

    assert client.post(f"/ai/configs/{first['id']}/enable").status_code == 200
    assert client.post(f"/ai/configs/{second['id']}/enable").status_code == 200
    configs = client.get("/ai/configs").json()
    enabled = [c for c in configs if c["enabled"]]
    assert [c["id"] for c in enabled] == [second["id"]]


def test_list_models_from_preview_config(client, monkeypatch):
    from app.services import ai_client

    captured = {}

    async def fake_call_models(request):
        captured["url"] = request.url
        captured["headers"] = request.headers
        return {"data": [{"id": "model-a"}, {"id": "model-b"}]}

    monkeypatch.setattr(ai_client, "call_models", fake_call_models)

    resp = client.post(
        "/ai/models",
        json={
            "provider": "openai_chat",
            "api_key": "sk-preview",
            "base_url": "https://api.example.com",
            "extra_headers": {"X-Test": "1"},
        },
    )

    assert resp.status_code == 200
    assert resp.json()["models"] == ["model-a", "model-b"]
    assert captured["url"] == "https://api.example.com/v1/models"
    assert captured["headers"]["Authorization"] == "Bearer sk-preview"
    assert captured["headers"]["X-Test"] == "1"


def test_list_models_uses_saved_sensitive_headers_when_preview_is_masked(
    client, monkeypatch
):
    from app.services import ai_client

    captured = {}

    async def fake_call_models(request):
        captured["headers"] = request.headers
        return {"data": [{"id": "kimi-for-coding"}]}

    monkeypatch.setattr(ai_client, "call_models", fake_call_models)
    config = client.post(
        "/ai/configs",
        json={
            "name": "Kimi",
            "provider": "claude_messages",
            "model": "kimi-for-coding",
            "api_key": "sk-secret-value",
            "base_url": "https://api.moonshot.cn/anthropic",
            "extra_headers": {
                "Authorization": "Bearer real-kimi-key",
                "X-Trace": "trace-id",
            },
        },
    ).json()

    resp = client.post(
        "/ai/models",
        json={
            "config_id": config["id"],
            "provider": "claude_messages",
            "api_key": "sk-secret-value",
            "base_url": "https://api.moonshot.cn/anthropic",
            "extra_headers": {
                "Authorization": "***",
                "X-Trace": "trace-id",
            },
        },
    )

    assert resp.status_code == 200
    assert resp.json()["models"] == ["kimi-for-coding"]
    assert captured["headers"]["Authorization"] == "Bearer real-kimi-key"
    assert captured["headers"]["X-Trace"] == "trace-id"


def test_ai_provider_errors_do_not_leak_secrets(client, monkeypatch):
    from app.services import ai_client

    config = client.post(
        "/ai/configs",
        json={
            "name": "Kimi",
            "provider": "claude_messages",
            "model": "kimi-for-coding",
            "api_key": "sk-secret-value",
        },
    ).json()

    async def fake_call_provider(_request):
        raise RuntimeError("upstream rejected Authorization: Bearer sk-secret-value")

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)

    resp = client.post(f"/ai/configs/{config['id']}/test")

    assert resp.status_code == 502
    assert "模型连接失败" in resp.json()["detail"]
    assert "sk-secret-value" not in resp.json()["detail"]


def test_ai_provider_errors_keep_sanitized_diagnostic_detail(client, monkeypatch):
    from app.services import ai_client

    config = client.post(
        "/ai/configs",
        json={
            "name": "Kimi",
            "provider": "claude_messages",
            "model": "kimi-for-coding",
            "api_key": "sk-secret-value",
        },
    ).json()

    async def fake_call_provider(_request):
        raise RuntimeError("ConnectError: All connection attempts failed")

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)

    resp = client.post(f"/ai/configs/{config['id']}/test")

    assert resp.status_code == 502
    assert resp.json()["detail"] == "模型连接失败: ConnectError: All connection attempts failed"


def test_ai_config_test_success_uses_fixed_message(client, monkeypatch):
    from app.services import ai_client

    config = client.post(
        "/ai/configs",
        json={
            "name": "Kimi",
            "provider": "claude_messages",
            "model": "kimi-for-coding",
            "api_key": "sk-secret-value",
        },
    ).json()

    async def fake_call_provider(_request):
        return {
            "content": [
                {
                    "type": "text",
                    "text": "连接成功，但代理错误地回显了 Authorization: Bearer sk-secret-value",
                }
            ]
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)

    resp = client.post(f"/ai/configs/{config['id']}/test")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "message": "模型连接测试成功"}
