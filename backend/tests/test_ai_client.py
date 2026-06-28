from app.services.ai_client import (
    assert_public_resolved_host,
    build_models_request,
    build_provider_request,
    extract_model_ids,
    parse_assistant_plan,
    resolve_models_url,
    resolve_url,
)
import pytest


def test_resolve_url_uses_full_url():
    assert (
        resolve_url("openai_chat", "https://base", "https://full.example/chat")
        == "https://full.example/chat"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8080/v1/chat/completions",
        "http://localhost:8080/v1/chat/completions",
        "http://10.0.0.1/v1/chat/completions",
        "http://172.16.0.10/v1/chat/completions",
        "http://192.168.1.2/v1/chat/completions",
        "http://100.64.0.1/v1/chat/completions",
        "https://198.18.1.88/v1/chat/completions",
    ],
)
def test_resolve_url_allows_user_configured_local_private_and_proxy_targets(url):
    assert resolve_url("openai_chat", None, url) == url


def test_resolve_url_rejects_non_http_targets():
    with pytest.raises(ValueError):
        resolve_url("openai_chat", None, "file:///C:/Windows/win.ini")


def test_resolve_url_rejects_base_url_without_http_scheme():
    with pytest.raises(ValueError):
        resolve_url("openai_chat", "example.com", None)


def test_resolve_url_allows_plain_http_public_target():
    assert (
        resolve_url("openai_chat", "http://api.example.com", None)
        == "http://api.example.com/v1/chat/completions"
    )


def test_resolved_fake_ip_from_proxy_does_not_block_domain(monkeypatch):
    import socket

    def fake_getaddrinfo(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.1.88", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    assert_public_resolved_host("https://api.kimi.com/coding/v1/messages")


def test_resolve_models_url_uses_base_url():
    assert (
        resolve_models_url("openai_chat", "https://api.example.com/", None)
        == "https://api.example.com/v1/models"
    )


def test_resolve_models_url_derives_from_full_url():
    assert (
        resolve_models_url(
            "openai_chat",
            None,
            "https://api.example.com/custom/v1/chat/completions",
        )
        == "https://api.example.com/custom/v1/models"
    )


def test_build_openai_models_request_shape():
    req = build_models_request(
        provider="openai_responses",
        api_key="key",
        extra_headers={"X-Test": "1"},
        base_url="https://api.example.com",
        full_url=None,
        proxy_url=None,
    )
    assert req.url == "https://api.example.com/v1/models"
    assert req.headers["Authorization"] == "Bearer key"
    assert req.headers["X-Test"] == "1"


def test_build_claude_models_request_shape():
    req = build_models_request(
        provider="claude_messages",
        api_key="key",
        extra_headers={},
        base_url="https://api.anthropic.com",
        full_url=None,
        proxy_url="http://127.0.0.1:7890",
    )
    assert req.url == "https://api.anthropic.com/v1/models"
    assert req.headers["x-api-key"] == "key"
    assert req.headers["anthropic-version"] == "2023-06-01"
    assert req.proxy_url == "http://127.0.0.1:7890"


def test_extract_model_ids_from_openai_and_claude_shapes():
    assert extract_model_ids({"data": [{"id": "gpt-a"}, {"id": "gpt-b"}]}) == [
        "gpt-a",
        "gpt-b",
    ]
    assert extract_model_ids({"data": [{"id": "claude-a"}], "has_more": False}) == [
        "claude-a"
    ]


def test_parse_assistant_plan_extracts_json_from_mixed_text():
    text = """
我是知时助手，可以帮你整理日程。
{"reply":"可以，我先列出当前任务。","tools":[{"name":"list_tasks","args":{}}],"dangerous_actions":[]}
后续说明不要进入回复。
"""
    plan = parse_assistant_plan(text)
    assert plan["reply"] == "可以，我先列出当前任务。"
    assert plan["tools"] == [{"name": "list_tasks", "args": {}}]


def test_parse_assistant_plan_skips_non_plan_json_before_plan():
    text = """
调试信息：{"status":"ok"}
{"reply":"这是计划回复","tools":[],"dangerous_actions":[]}
"""
    plan = parse_assistant_plan(text)
    assert plan["reply"] == "这是计划回复"


def test_resolve_url_appends_openai_chat_path():
    assert (
        resolve_url("openai_chat", "https://api.example.com/", None)
        == "https://api.example.com/v1/chat/completions"
    )


def test_resolve_url_appends_responses_path():
    assert (
        resolve_url("openai_responses", "https://api.example.com", None)
        == "https://api.example.com/v1/responses"
    )


def test_resolve_url_appends_claude_path():
    assert (
        resolve_url("claude_messages", "https://api.example.com", None)
        == "https://api.example.com/v1/messages"
    )


def test_openai_chat_request_shape():
    req = build_provider_request(
        provider="openai_chat",
        model="model-a",
        api_key="key",
        messages=[{"role": "user", "content": "hello"}],
        system_prompt="system",
        extra_headers={},
        base_url="https://api.example.com",
        full_url=None,
        proxy_url=None,
    )
    assert req.url.endswith("/v1/chat/completions")
    assert req.json["model"] == "model-a"
    assert req.json["messages"][0]["role"] == "system"
    assert req.headers["Authorization"] == "Bearer key"


def test_openai_responses_request_shape():
    req = build_provider_request(
        provider="openai_responses",
        model="model-r",
        api_key="key",
        messages=[{"role": "user", "content": "hello"}],
        system_prompt="system",
        extra_headers={"X-Test": "1"},
        base_url="https://api.example.com",
        full_url=None,
        proxy_url="http://127.0.0.1:7890",
    )
    assert req.url.endswith("/v1/responses")
    assert req.json["input"][0]["role"] == "system"
    assert req.headers["Authorization"] == "Bearer key"
    assert req.headers["X-Test"] == "1"
    assert req.proxy_url == "http://127.0.0.1:7890"


def test_claude_request_shape():
    req = build_provider_request(
        provider="claude_messages",
        model="claude-test",
        api_key="key",
        messages=[{"role": "user", "content": "hello"}],
        system_prompt="system",
        extra_headers={},
        base_url="https://api.example.com",
        full_url=None,
        proxy_url=None,
    )
    assert req.url.endswith("/v1/messages")
    assert req.json["system"] == "system"
    assert req.headers["x-api-key"] == "key"
    assert req.headers["anthropic-version"] == "2023-06-01"


def test_openai_responses_request_adds_native_web_search_tool():
    req = build_provider_request(
        provider="openai_responses",
        model="model-r",
        api_key="key",
        messages=[{"role": "user", "content": "hello"}],
        system_prompt="system",
        extra_headers={},
        base_url="https://api.example.com",
        full_url=None,
        proxy_url=None,
        native_web_search_enabled=True,
        native_web_search_options={},
    )

    assert req.json["tools"] == [{"type": "web_search_preview"}]
    assert req.json["tool_choice"] == "auto"


def test_openai_chat_request_adds_native_web_search_options():
    req = build_provider_request(
        provider="openai_chat",
        model="model-a",
        api_key="key",
        messages=[{"role": "user", "content": "hello"}],
        system_prompt="system",
        extra_headers={},
        base_url="https://api.example.com",
        full_url=None,
        proxy_url=None,
        native_web_search_enabled=True,
        native_web_search_options={"web_search_options": {"search_context_size": "low"}},
    )

    assert req.json["web_search_options"] == {"search_context_size": "low"}


def test_claude_request_adds_native_web_search_tool():
    req = build_provider_request(
        provider="claude_messages",
        model="claude-test",
        api_key="key",
        messages=[{"role": "user", "content": "hello"}],
        system_prompt="system",
        extra_headers={},
        base_url="https://api.example.com",
        full_url=None,
        proxy_url=None,
        native_web_search_enabled=True,
        native_web_search_options={},
    )

    assert req.json["tools"] == [
        {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}
    ]


def test_native_web_search_options_can_override_provider_defaults():
    req = build_provider_request(
        provider="claude_messages",
        model="claude-test",
        api_key="key",
        messages=[{"role": "user", "content": "hello"}],
        system_prompt="system",
        extra_headers={},
        base_url="https://api.example.com",
        full_url=None,
        proxy_url=None,
        native_web_search_enabled=True,
        native_web_search_options={
            "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
            "tool_choice": {"type": "auto"},
        },
    )

    assert req.json["tools"] == [
        {"type": "web_search_20250305", "name": "web_search", "max_uses": 2}
    ]
    assert req.json["tool_choice"] == {"type": "auto"}
