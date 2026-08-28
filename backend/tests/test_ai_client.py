from app.services.ai_client import (
    _OpenAIChatStreamBuilder,
    _OpenAIResponsesStreamBuilder,
    _ClaudeStreamBuilder,
    assert_public_resolved_host,
    build_models_request,
    build_provider_request,
    extract_assistant_turn,
    extract_model_ids,
    extract_reasoning,
    extract_text,
    resolve_models_url,
    resolve_url,
)
import pytest

_TOOLS = [
    {
        "name": "create_task",
        "description": "创建任务",
        "input_schema": {"type": "object", "properties": {"title": {"type": "string"}}},
    },
    {
        "name": "list_tasks",
        "description": "列出任务",
        "input_schema": {"type": "object", "properties": {}},
    },
]


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


# ---- P2：原生 tools 注入 ----


def test_openai_chat_injects_function_tools():
    req = build_provider_request(
        provider="openai_chat",
        model="m",
        api_key="key",
        messages=[{"role": "user", "content": "hi"}],
        system_prompt="system",
        extra_headers={},
        base_url="https://api.example.com",
        full_url=None,
        proxy_url=None,
        tools=_TOOLS,
    )
    assert req.json["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "create_task",
                "description": "创建任务",
                "parameters": {"type": "object", "properties": {"title": {"type": "string"}}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_tasks",
                "description": "列出任务",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]
    assert req.json["tool_choice"] == "auto"


def test_openai_responses_injects_function_tools():
    req = build_provider_request(
        provider="openai_responses",
        model="m",
        api_key="key",
        messages=[{"role": "user", "content": "hi"}],
        system_prompt="system",
        extra_headers={},
        base_url="https://api.example.com",
        full_url=None,
        proxy_url=None,
        tools=_TOOLS,
    )
    assert req.json["tools"][0] == {
        "type": "function",
        "name": "create_task",
        "description": "创建任务",
        "parameters": {"type": "object", "properties": {"title": {"type": "string"}}},
    }
    assert req.json["tool_choice"] == "auto"


def test_claude_injects_function_tools():
    req = build_provider_request(
        provider="claude_messages",
        model="m",
        api_key="key",
        messages=[{"role": "user", "content": "hi"}],
        system_prompt="system",
        extra_headers={},
        base_url="https://api.anthropic.com",
        full_url=None,
        proxy_url=None,
        tools=_TOOLS,
    )
    assert req.json["tools"][0] == {
        "name": "create_task",
        "description": "创建任务",
        "input_schema": {"type": "object", "properties": {"title": {"type": "string"}}},
    }
    assert req.json["tool_choice"] == {"type": "auto"}


def test_tools_and_native_web_search_coexist_for_responses():
    """D8：自定义工具与联网搜索同开时，两者都在 tools 数组里。"""
    req = build_provider_request(
        provider="openai_responses",
        model="m",
        api_key="key",
        messages=[{"role": "user", "content": "hi"}],
        system_prompt="system",
        extra_headers={},
        base_url="https://api.example.com",
        full_url=None,
        proxy_url=None,
        native_web_search_enabled=True,
        native_web_search_options={},
        tools=_TOOLS,
    )
    tool_names = [t.get("name") or t.get("type") for t in req.json["tools"]]
    assert "create_task" in tool_names
    assert "web_search_preview" in tool_names
    assert req.json["tool_choice"] == "auto"


def test_tools_and_native_web_search_coexist_for_claude():
    req = build_provider_request(
        provider="claude_messages",
        model="m",
        api_key="key",
        messages=[{"role": "user", "content": "hi"}],
        system_prompt="system",
        extra_headers={},
        base_url="https://api.anthropic.com",
        full_url=None,
        proxy_url=None,
        native_web_search_enabled=True,
        native_web_search_options={},
        tools=_TOOLS,
    )
    names = [t.get("name") for t in req.json["tools"]]
    assert "create_task" in names
    assert "web_search" in names


# ---- P2：extract_assistant_turn ----


def test_extract_openai_chat_tool_calls():
    payload = {
        "choices": [
            {
                "message": {
                    "content": "我先查看任务",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "create_task",
                                "arguments": '{"title":"论文"}',
                            },
                        }
                    ],
                }
            }
        ]
    }
    turn = extract_assistant_turn("openai_chat", payload)
    assert turn["text"] == "我先查看任务"
    assert turn["tool_calls"] == [
        {"id": "call_1", "name": "create_task", "arguments": {"title": "论文"}, "arguments_error": None}
    ]


def test_extract_openai_chat_malformed_arguments():
    payload = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {"id": "c", "type": "function", "function": {"name": "x", "arguments": "{bad"}}
                    ]
                }
            }
        ]
    }
    turn = extract_assistant_turn("openai_chat", payload)
    assert turn["tool_calls"][0]["arguments"] is None
    assert "解析失败" in turn["tool_calls"][0]["arguments_error"]


def test_extract_openai_responses_tool_calls():
    payload = {
        "output_text": "已安排",
        "output": [
            {"type": "function_call", "call_id": "r1", "name": "list_tasks", "arguments": "{}"},
        ],
    }
    turn = extract_assistant_turn("openai_responses", payload)
    assert turn["text"] == "已安排"
    assert turn["tool_calls"] == [
        {"id": "r1", "name": "list_tasks", "arguments": {}, "arguments_error": None}
    ]


def test_extract_claude_tool_calls():
    payload = {
        "stop_reason": "tool_use",
        "content": [
            {"type": "text", "text": "我帮你建任务"},
            {"type": "tool_use", "id": "tu_1", "name": "create_task", "input": {"title": "论文"}},
        ],
    }
    turn = extract_assistant_turn("claude_messages", payload)
    assert turn["text"] == "我帮你建任务"
    assert turn["stop_reason"] == "tool_use"
    assert turn["tool_calls"] == [
        {"id": "tu_1", "name": "create_task", "arguments": {"title": "论文"}, "arguments_error": None}
    ]


def test_extract_no_tool_calls_returns_empty():
    turn = extract_assistant_turn("openai_chat", {"choices": [{"message": {"content": "纯文本"}}]})
    assert turn["tool_calls"] == []
    assert turn["text"] == "纯文本"


# ---- P2：tool 消息序列化 ----


def _tool_messages():
    return [
        {"role": "user", "content": "帮我建任务"},
        {"role": "assistant", "content": "好的", "tool_calls": [
            {"id": "call_1", "name": "create_task", "arguments": {"title": "论文"}},
        ]},
        {"role": "tool", "tool_call_id": "call_1", "name": "create_task", "content": '{"ok":true}'},
    ]


def test_openai_chat_serializes_tool_messages():
    req = build_provider_request(
        provider="openai_chat",
        model="m",
        api_key="key",
        messages=_tool_messages(),
        system_prompt="system",
        extra_headers={},
        base_url="https://api.example.com",
        full_url=None,
        proxy_url=None,
    )
    msgs = req.json["messages"][1:]  # 去掉 system
    assert msgs[0] == {"role": "user", "content": "帮我建任务"}
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == "好的"
    assert msgs[1]["tool_calls"][0] == {
        "id": "call_1",
        "type": "function",
        "function": {"name": "create_task", "arguments": '{"title": "论文"}'},
    }
    assert msgs[2] == {"role": "tool", "tool_call_id": "call_1", "content": '{"ok":true}'}


def test_openai_responses_serializes_tool_messages():
    req = build_provider_request(
        provider="openai_responses",
        model="m",
        api_key="key",
        messages=_tool_messages(),
        system_prompt="system",
        extra_headers={},
        base_url="https://api.example.com",
        full_url=None,
        proxy_url=None,
    )
    items = req.json["input"][1:]  # 去掉 system
    assert items[0] == {"role": "user", "content": "帮我建任务"}
    assert items[1] == {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": "好的"}],
    }
    assert items[2] == {
        "type": "function_call",
        "call_id": "call_1",
        "name": "create_task",
        "arguments": '{"title": "论文"}',
    }
    assert items[3] == {"type": "function_call_output", "call_id": "call_1", "output": '{"ok":true}'}


def test_claude_serializes_tool_messages_and_merges_consecutive_results():
    messages = [
        {"role": "user", "content": "帮我建两个任务"},
        {"role": "assistant", "content": "好的", "tool_calls": [
            {"id": "tu_1", "name": "create_task", "arguments": {"title": "A"}},
            {"id": "tu_2", "name": "create_task", "arguments": {"title": "B"}},
        ]},
        {"role": "tool", "tool_call_id": "tu_1", "name": "create_task", "content": "ok1"},
        {"role": "tool", "tool_call_id": "tu_2", "name": "create_task", "content": "ok2"},
    ]
    req = build_provider_request(
        provider="claude_messages",
        model="m",
        api_key="key",
        messages=messages,
        system_prompt="system",
        extra_headers={},
        base_url="https://api.anthropic.com",
        full_url=None,
        proxy_url=None,
    )
    msgs = req.json["messages"]
    assert msgs[0] == {"role": "user", "content": "帮我建两个任务"}
    assert msgs[1] == {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "好的"},
            {"type": "tool_use", "id": "tu_1", "name": "create_task", "input": {"title": "A"}},
            {"type": "tool_use", "id": "tu_2", "name": "create_task", "input": {"title": "B"}},
        ],
    }
    # 两条 tool 结果合并进一条 user 消息
    assert len(msgs) == 3
    assert msgs[2]["role"] == "user"
    assert msgs[2]["content"] == [
        {"type": "tool_result", "tool_use_id": "tu_1", "content": "ok1"},
        {"type": "tool_result", "tool_use_id": "tu_2", "content": "ok2"},
    ]


def test_text_messages_remain_byte_identical_after_refactor():
    """守门员：纯文本/附件消息序列化与重构前逐字节一致。"""
    plain = build_provider_request(
        provider="openai_chat",
        model="m",
        api_key="key",
        messages=[{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}],
        system_prompt="system",
        extra_headers={},
        base_url="https://api.example.com",
        full_url=None,
        proxy_url=None,
    )
    assert plain.json["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]


# ---- SSE 流式聚合单元测试（阶段 4）----


def _feed(builder, chunks):
    """喂入一组 SSE chunk dict，收集中间帧（不含末帧 turn）。"""
    frames = []
    for chunk, event in chunks:
        frames.extend(builder.feed(chunk, event))
    return frames


def test_openai_chat_stream_builder_merges_tool_call_fragments():
    """OpenAI chat/completions 的 arguments 碎片按 index 归并，最终组装出与非流式同构的 message。"""
    b = _OpenAIChatStreamBuilder()
    chunks = [
        ({"choices": [{"delta": {"content": "你好"}}]}, None),
        (
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_1",
                                    "function": {"name": "create_task", "arguments": '{"title":"A"'},
                                }
                            ]
                        }
                    }
                ]
            },
            None,
        ),
        (
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {"index": 0, "function": {"arguments": ',"due":"today"}'}}
                            ]
                        }
                    }
                ]
            },
            None,
        ),
        ({"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}, None),
    ]
    frames = _feed(b, chunks)
    raw = b.finalize()
    # 文本增量被发射
    assert any(f["type"] == "text_delta" and f["delta"] == "你好" for f in frames)
    # tool_call_start 在 name+id 完整时发射（仅一次）
    starts = [f for f in frames if f["type"] == "tool_call_start"]
    assert len(starts) == 1
    assert starts[0]["name"] == "create_task"
    # 组装 message：content 拼接 + tool_calls.arguments 完整
    msg = raw["choices"][0]["message"]
    assert msg["content"] == "你好"
    assert msg["tool_calls"][0]["function"]["arguments"] == '{"title":"A","due":"today"}'
    assert raw["choices"][0]["finish_reason"] == "tool_calls"
    # 与 extract_assistant_turn 解析一致
    turn = extract_assistant_turn("openai_chat", raw)
    assert turn["text"] == "你好"
    assert turn["tool_calls"][0]["name"] == "create_task"
    assert turn["tool_calls"][0]["arguments"] == {"title": "A", "due": "today"}


def test_openai_chat_stream_builder_multiple_tool_calls():
    """多 index 的 tool_calls 各自归并，组装后顺序按 index。"""
    b = _OpenAIChatStreamBuilder()
    chunks = [
        (
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {"index": 0, "id": "c1", "function": {"name": "list_tasks", "arguments": "{}"}},
                                {"index": 1, "id": "c2", "function": {"name": "create_task", "arguments": '{"title":"X"}'}},
                            ]
                        }
                    }
                ]
            },
            None,
        ),
        ({"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}, None),
    ]
    _feed(b, chunks)
    raw = b.finalize()
    turn = extract_assistant_turn("openai_chat", raw)
    assert [c["name"] for c in turn["tool_calls"]] == ["list_tasks", "create_task"]


def test_openai_responses_stream_builder_assembles_from_events():
    """openai_responses 通过 typed events 聚合，无 response.completed 时回退组装。"""
    b = _OpenAIResponsesStreamBuilder()
    chunks = [
        ({"type": "response.output_text.delta", "delta": "我先"}, None),
        ({"type": "response.output_text.delta", "delta": "查看"}, None),
        (
            {
                "type": "response.output_item.added",
                "item": {"type": "function_call", "id": "fc_1", "call_id": "call_x", "name": "list_tasks"},
            },
            None,
        ),
        ({"type": "response.function_call_arguments.delta", "item_id": "fc_1", "delta": "{}"}, None),
    ]
    frames = _feed(b, chunks)
    raw = b.finalize()
    # text_delta 被发射
    deltas = [f["delta"] for f in frames if f["type"] == "text_delta"]
    assert "".join(deltas) == "我先查看"
    # tool_call_start 在 name+call_id 完整时发射
    assert any(f["type"] == "tool_call_start" and f["name"] == "list_tasks" for f in frames)
    # 回退组装（无 completed）：output_text + output[].function_call
    assert raw["output_text"] == "我先查看"
    fc = next(item for item in raw["output"] if item.get("type") == "function_call")
    assert fc["call_id"] == "call_x"
    assert fc["name"] == "list_tasks"
    turn = extract_assistant_turn("openai_responses", raw)
    assert turn["tool_calls"][0]["arguments"] == {}


def test_openai_responses_stream_builder_uses_completed_payload():
    """有 response.completed 时优先用其权威 payload，避免回退组装差异。"""
    b = _OpenAIResponsesStreamBuilder()
    completed = {
        "id": "resp_1",
        "status": "completed",
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": "权威结果"}]},
            {"type": "function_call", "id": "fc_1", "call_id": "c1", "name": "create_task", "arguments": '{"title":"权威"}'},
        ],
        "output_text": "权威结果",
    }
    _feed(
        b,
        [
            ({"type": "response.output_text.delta", "delta": "权威结果"}, None),
            ({"type": "response.completed", "response": completed}, None),
        ],
    )
    raw = b.finalize()
    assert raw is completed


def test_claude_stream_builder_assembles_text_and_tool_use():
    """Anthropic content_block_* 事件组装出 content[]（text + tool_use）。"""
    b = _ClaudeStreamBuilder()
    chunks = [
        ({"type": "message_start", "message": {"id": "msg_1"}}, None),
        ({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "id": "tb_1"}}, None),
        ({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "好的"}}, None),
        ({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "，我处理"}}, None),
        ({"type": "content_block_stop", "index": 0}, None),
        (
            {
                "type": "content_block_start",
                "index": 1,
                "content_block": {"type": "tool_use", "id": "tu_1", "name": "create_task"},
            },
            None,
        ),
        (
            {
                "type": "content_block_delta",
                "index": 1,
                "delta": {"type": "input_json_delta", "partial_json": '{"title":"Y"}'},
            },
            None,
        ),
        ({"type": "content_block_stop", "index": 1}, None),
        ({"type": "message_delta", "delta": {"stop_reason": "tool_use"}}, None),
        ({"type": "message_stop"}, None),
    ]
    frames = _feed(b, chunks)
    raw = b.finalize()
    # text_delta 发射
    deltas = [f["delta"] for f in frames if f["type"] == "text_delta"]
    assert "".join(deltas) == "好的，我处理"
    # tool_call_start 在 block_stop 且 tool_use 时发射
    assert any(f["type"] == "tool_call_start" and f["name"] == "create_task" for f in frames)
    # 组装 content
    assert raw["stop_reason"] == "tool_use"
    text_block = next(b2 for b2 in raw["content"] if b2["type"] == "text")
    assert text_block["text"] == "好的，我处理"
    tool_block = next(b2 for b2 in raw["content"] if b2["type"] == "tool_use")
    assert tool_block["input"] == {"title": "Y"}
    # 与 extract_assistant_turn 一致
    turn = extract_assistant_turn("claude_messages", raw)
    assert turn["tool_calls"][0]["arguments"] == {"title": "Y"}


def test_claude_stream_builder_handles_malformed_input_json():
    """input_json_delta 累积为非法 JSON 时，保留原文让 extract 标 arguments_error。"""
    b = _ClaudeStreamBuilder()
    chunks = [
        ({"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "id": "tu_1", "name": "create_task"}}, None),
        ({"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": "{broken"}}, None),
        ({"type": "content_block_stop", "index": 0}, None),
        ({"type": "message_delta", "delta": {"stop_reason": "tool_use"}}, None),
    ]
    _feed(b, chunks)
    raw = b.finalize()
    turn = extract_assistant_turn("claude_messages", raw)
    assert turn["tool_calls"][0]["arguments"] is None
    assert turn["tool_calls"][0]["arguments_error"] is not None


# ---- 阶段 3：思维链（reasoning）解析 ----


def test_openai_chat_stream_reasoning_delta():
    """DeepSeek/通义/智谱等 OpenAI 兼容服务用 delta.reasoning_content 流式输出推理链。"""
    b = _OpenAIChatStreamBuilder()
    chunks = [
        ({"choices": [{"delta": {"reasoning_content": "先思考"}}]}, None),
        ({"choices": [{"delta": {"reasoning_content": "一下"}}]}, None),
        ({"choices": [{"delta": {"content": "答案是"}}]}, None),
        ({"choices": [{"delta": {"content": "42"}, "finish_reason": "stop"}]}, None),
    ]
    frames = _feed(b, chunks)
    # reasoning_delta 与 text_delta 分流，不混排
    reasoning = "".join(f["delta"] for f in frames if f["type"] == "reasoning_delta")
    text = "".join(f["delta"] for f in frames if f["type"] == "text_delta")
    assert reasoning == "先思考一下"
    assert text == "答案是42"
    # finalize 把 reasoning 写进 message.reasoning_content，供非流式提取
    raw = b.finalize()
    assert raw["choices"][0]["message"]["reasoning_content"] == "先思考一下"
    assert raw["choices"][0]["message"]["content"] == "答案是42"


def test_claude_stream_builder_captures_message_delta_usage():
    b = _ClaudeStreamBuilder()
    for chunk, event in [
        ({"type": "message_start", "message": {"id": "msg_1", "usage": {"input_tokens": 100, "output_tokens": 1}}}, None),
        ({"type": "content_block_start", "content_block": {"type": "text", "id": "b1"}, "index": 0}, None),
        ({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "你好"}, "index": 0}, None),
        ({"type": "content_block_stop", "index": 0}, None),
        ({"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 58}}, None),
        ({"type": "message_stop"}, None),
    ]:
        b.feed(chunk, event)

    payload = b.finalize()

    assert payload["usage"]["input_tokens"] == 100
    assert payload["usage"]["output_tokens"] == 58  # 真实累计值，不是骨架里的初始 1


def test_claude_stream_thinking_delta():
    """Claude thinking 块的 thinking_delta 应产出 reasoning_delta，正文 text_delta 不受影响。"""
    b = _ClaudeStreamBuilder()
    chunks = [
        ({"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "id": "th_1"}}, None),
        ({"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "推理"}}, None),
        ({"type": "content_block_stop", "index": 0}, None),
        ({"type": "content_block_start", "index": 1, "content_block": {"type": "text", "id": "tx_1"}}, None),
        ({"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "正文"}}, None),
        ({"type": "content_block_stop", "index": 1}, None),
        ({"type": "message_delta", "delta": {"stop_reason": "end_turn"}}, None),
    ]
    frames = _feed(b, chunks)
    reasoning = "".join(f["delta"] for f in frames if f["type"] == "reasoning_delta")
    text = "".join(f["delta"] for f in frames if f["type"] == "text_delta")
    assert reasoning == "推理"
    assert text == "正文"
    raw = b.finalize()
    # thinking 块保留在 content 中，extract_reasoning 能取出
    assert extract_reasoning("claude_messages", raw) == "推理"
    assert extract_text("claude_messages", raw) == "正文"


def test_responses_stream_reasoning_summary_delta():
    """OpenAI Responses API 的 response.reasoning_summary_text.delta 应产出 reasoning_delta。"""
    b = _OpenAIResponsesStreamBuilder()
    chunks = [
        ({"type": "response.reasoning_summary_text.delta", "delta": "摘要"}, None),
        ({"type": "response.output_text.delta", "delta": "正文"}, None),
    ]
    frames = _feed(b, chunks)
    reasoning = "".join(f["delta"] for f in frames if f["type"] == "reasoning_delta")
    text = "".join(f["delta"] for f in frames if f["type"] == "text_delta")
    assert reasoning == "摘要"
    assert text == "正文"


def test_extract_reasoning_non_stream_openai_chat():
    """非流式 openai_chat：message.reasoning_content 被提取，正文不混入。"""
    payload = {
        "choices": [
            {"message": {"content": "正文", "reasoning_content": "推理过程"}}
        ]
    }
    assert extract_reasoning("openai_chat", payload) == "推理过程"
    turn = extract_assistant_turn("openai_chat", payload)
    assert turn["reasoning"] == "推理过程"
    assert turn["text"] == "正文"


def test_extract_reasoning_empty_when_unsupported():
    """provider 不带 reasoning 字段时返回空串（UI 自然不显示）。"""
    payload = {"choices": [{"message": {"content": "只有正文"}}]}
    assert extract_reasoning("openai_chat", payload) == ""
    assert extract_assistant_turn("openai_chat", payload)["reasoning"] == ""
