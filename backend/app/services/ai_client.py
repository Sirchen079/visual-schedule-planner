from __future__ import annotations

import copy
import json
import re
import socket
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

DEFAULT_PATHS = {
    "openai_chat": "/v1/chat/completions",
    "openai_responses": "/v1/responses",
    "claude_messages": "/v1/messages",
}
MODEL_LIST_PATH = "/v1/models"
NATIVE_WEB_SEARCH_DEFAULTS: dict[str, dict[str, Any]] = {
    "openai_chat": {"web_search_options": {}},
    "openai_responses": {
        "tools": [{"type": "web_search_preview"}],
        "tool_choice": "auto",
    },
    "claude_messages": {
        "tools": [
            {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}
        ],
    },
}


@dataclass
class ProviderRequest:
    url: str
    headers: dict[str, str]
    json: dict[str, Any]
    proxy_url: str | None = None
    # 构造时已知的 provider，供 stream_provider 选择 SSE 解析器，避免按 URL 后缀误判（full_url/网关场景）
    provider: str = ""


@dataclass
class ModelsRequest:
    url: str
    headers: dict[str, str]
    proxy_url: str | None = None


def resolve_url(provider: str, base_url: str | None, full_url: str | None) -> str:
    if full_url:
        return validate_provider_url(full_url)
    if provider not in DEFAULT_PATHS:
        raise ValueError(f"不支持的 provider: {provider}")
    if not base_url:
        base_url = "https://api.openai.com" if provider.startswith("openai") else "https://api.anthropic.com"
    return validate_provider_url(f"{base_url.rstrip('/')}{DEFAULT_PATHS[provider]}")


def resolve_models_url(provider: str, base_url: str | None, full_url: str | None) -> str:
    if base_url:
        return validate_provider_url(f"{base_url.rstrip('/')}{MODEL_LIST_PATH}")
    if full_url:
        parsed = urlparse(validate_provider_url(full_url))
        path = parsed.path
        for suffix in DEFAULT_PATHS.values():
            if path.endswith(suffix):
                path = path[: -len(suffix)] + MODEL_LIST_PATH
                break
        else:
            path = MODEL_LIST_PATH
        return validate_provider_url(urlunparse(parsed._replace(path=path, params="", query="", fragment="")))
    base = "https://api.openai.com" if provider.startswith("openai") else "https://api.anthropic.com"
    return f"{base}{MODEL_LIST_PATH}"


def validate_provider_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("模型 URL 只允许 http 或 https")
    if not parsed.hostname:
        raise ValueError("模型 URL 缺少 host")
    return urlunparse(parsed)


def validate_proxy_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https", "socks5", "socks5h"}:
        raise ValueError("代理 URL 只允许 http、https、socks5 或 socks5h")
    if not parsed.hostname:
        raise ValueError("代理 URL 缺少 host")
    return urlunparse(parsed)


def assert_public_resolved_host(url: str) -> None:
    parsed = urlparse(validate_provider_url(url))
    host = parsed.hostname
    if not host:
        raise ValueError("模型 URL 缺少 host")
    try:
        socket.getaddrinfo(host, parsed.port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("模型 URL 域名无法解析") from exc


def build_models_request(
    *,
    provider: str,
    api_key: str,
    extra_headers: dict[str, str],
    base_url: str | None,
    full_url: str | None,
    proxy_url: str | None,
) -> ModelsRequest:
    if provider not in DEFAULT_PATHS:
        raise ValueError(f"不支持的 provider: {provider}")
    headers = {"Content-Type": "application/json", **(extra_headers or {})}
    if provider in {"openai_chat", "openai_responses"}:
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        headers["x-api-key"] = api_key
        headers.setdefault("anthropic-version", "2023-06-01")
    return ModelsRequest(
        url=resolve_models_url(provider, base_url, full_url),
        headers=headers,
        proxy_url=validate_proxy_url(proxy_url) if proxy_url else None,
    )


def build_provider_request(
    *,
    provider: str,
    model: str,
    api_key: str,
    messages: list[dict[str, Any]],
    system_prompt: str,
    extra_headers: dict[str, str],
    base_url: str | None,
    full_url: str | None,
    proxy_url: str | None,
    native_web_search_enabled: bool = False,
    native_web_search_options: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> ProviderRequest:
    url = resolve_url(provider, base_url, full_url)
    headers = {"Content-Type": "application/json", **(extra_headers or {})}
    if provider in {"openai_chat", "openai_responses"}:
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        headers["x-api-key"] = api_key
        headers.setdefault("anthropic-version", "2023-06-01")

    provider_messages = _provider_messages(provider, messages)

    if provider == "openai_chat":
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system_prompt}, *provider_messages],
            "temperature": 0.2,
        }
    elif provider == "openai_responses":
        payload = {
            "model": model,
            "input": [{"role": "system", "content": system_prompt}, *provider_messages],
            "temperature": 0.2,
        }
    elif provider == "claude_messages":
        payload = {
            "model": model,
            "system": system_prompt,
            "messages": provider_messages,
            "max_tokens": 2000,
            "temperature": 0.2,
        }
    else:
        raise ValueError(f"不支持的 provider: {provider}")

    # 自定义工具先注入，再合并联网搜索（D8：tools 数组追加而非覆盖）
    _apply_custom_tools(provider=provider, payload=payload, tools=tools)
    if native_web_search_enabled:
        _apply_native_web_search(
            provider=provider,
            payload=payload,
            options=native_web_search_options or {},
        )

    return ProviderRequest(
        url=url,
        headers=headers,
        json=payload,
        proxy_url=validate_proxy_url(proxy_url) if proxy_url else None,
        provider=provider,
    )


def _apply_custom_tools(
    *,
    provider: str,
    payload: dict[str, Any],
    tools: list[dict[str, Any]] | None,
) -> None:
    """按 provider 形态注入 function-calling 工具数组（provider 无关输入）。"""
    if not tools:
        return
    if provider == "openai_chat":
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema") or {},
                },
            }
            for t in tools
        ]
        payload["tool_choice"] = "auto"
    elif provider == "openai_responses":
        payload["tools"] = [
            {
                "type": "function",
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema") or {},
            }
            for t in tools
        ]
        payload["tool_choice"] = "auto"
    elif provider == "claude_messages":
        payload["tools"] = [
            {
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t.get("input_schema") or {},
            }
            for t in tools
        ]
        payload["tool_choice"] = {"type": "auto"}


def _apply_native_web_search(
    *,
    provider: str,
    payload: dict[str, Any],
    options: dict[str, Any],
) -> None:
    additions = copy.deepcopy(NATIVE_WEB_SEARCH_DEFAULTS.get(provider, {}))
    _merge_request_options(additions, options)
    for key, value in additions.items():
        if (
            key == "tools"
            and isinstance(value, list)
            and isinstance(payload.get("tools"), list)
        ):
            # 自定义工具已占用 tools 键：追加联网搜索工具，不覆盖
            payload["tools"] = [*payload["tools"], *value]
        elif key == "tool_choice" and "tool_choice" in payload:
            # 自定义工具已设 tool_choice（同为 auto），保留不覆盖
            continue
        else:
            payload[key] = value


def _merge_request_options(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    for key, value in (source or {}).items():
        if isinstance(target.get(key), dict) and isinstance(value, dict):
            _merge_request_options(target[key], value)
        else:
            target[key] = value
    return target


def _provider_messages(provider: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if provider == "openai_chat":
        return _to_openai_chat_messages(provider, messages)
    if provider == "openai_responses":
        return _to_openai_responses_input(provider, messages)
    if provider == "claude_messages":
        return _to_claude_messages(provider, messages)
    raise ValueError(f"不支持的 provider: {provider}")


def _is_text_message(message: dict[str, Any]) -> bool:
    """普通文本/附件消息（无 tool_calls，非 tool 结果）。"""
    return not message.get("tool_calls") and message.get("role") != "tool"


def _to_openai_chat_messages(provider: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for message in messages:
        if message.get("role") == "tool":
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": str(message.get("tool_call_id", "")),
                    "content": str(message.get("content", "")),
                }
            )
            continue
        if message.get("tool_calls"):
            out.append(
                {
                    "role": "assistant",
                    "content": message.get("content") or None,
                    "tool_calls": [
                        {
                            "id": str(tc.get("id", "")),
                            "type": "function",
                            "function": {
                                "name": str(tc.get("name", "")),
                                "arguments": json.dumps(
                                    tc.get("arguments") or {}, ensure_ascii=False
                                ),
                            },
                        }
                        for tc in message["tool_calls"]
                    ],
                }
            )
            continue
        out.append(_text_message(provider, message))
    return out


def _to_openai_responses_input(provider: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """openai_responses 的 input 数组：消息项 + function_call/function_call_output 项。"""
    out: list[dict[str, Any]] = []
    for message in messages:
        if message.get("role") == "tool":
            out.append(
                {
                    "type": "function_call_output",
                    "call_id": str(message.get("tool_call_id", "")),
                    "output": str(message.get("content", "")),
                }
            )
            continue
        if message.get("tool_calls"):
            text = message.get("content")
            if text:
                out.append(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": str(text)}],
                    }
                )
            for tc in message["tool_calls"]:
                out.append(
                    {
                        "type": "function_call",
                        "call_id": str(tc.get("id", "")),
                        "name": str(tc.get("name", "")),
                        "arguments": json.dumps(tc.get("arguments") or {}, ensure_ascii=False),
                    }
                )
            continue
        out.append(_text_message(provider, message))
    return out


def _to_claude_messages(provider: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """claude_messages：连续 tool 结果合并进一条 user 消息（Anthropic 协议要求）。"""
    out: list[dict[str, Any]] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        if message.get("role") == "tool":
            results: list[dict[str, Any]] = []
            while index < len(messages) and messages[index].get("role") == "tool":
                tool_msg = messages[index]
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": str(tool_msg.get("tool_call_id", "")),
                        "content": str(tool_msg.get("content", "")),
                    }
                )
                index += 1
            out.append({"role": "user", "content": results})
            continue
        if message.get("tool_calls"):
            blocks: list[dict[str, Any]] = []
            text = message.get("content")
            if text:
                blocks.append({"type": "text", "text": str(text)})
            for tc in message["tool_calls"]:
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": str(tc.get("id", "")),
                        "name": str(tc.get("name", "")),
                        "input": tc.get("arguments") or {},
                    }
                )
            out.append({"role": "assistant", "content": blocks})
            index += 1
            continue
        out.append(_text_message(provider, message))
        index += 1
    return out


def _text_message(provider: str, message: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": message.get("role", "user"),
        "content": _provider_content(
            provider,
            str(message.get("content", "")),
            message.get("attachments") or [],
        ),
    }


def _provider_content(provider: str, text: str, attachments: list[dict[str, Any]]) -> Any:
    if not attachments:
        return text
    if provider == "openai_chat":
        blocks = [{"type": "text", "text": text or "请分析附件。"}]
        for attachment in attachments:
            blocks.extend(_openai_chat_attachment_blocks(attachment))
        return blocks
    if provider == "openai_responses":
        blocks = [{"type": "input_text", "text": text or "请分析附件。"}]
        for attachment in attachments:
            blocks.extend(_openai_responses_attachment_blocks(attachment))
        return blocks
    if provider == "claude_messages":
        blocks = [{"type": "text", "text": text or "请分析附件。"}]
        for attachment in attachments:
            blocks.extend(_claude_attachment_blocks(attachment))
        return blocks
    return text


def _openai_chat_attachment_blocks(attachment: dict[str, Any]) -> list[dict[str, Any]]:
    if attachment.get("kind") == "image":
        return [
            {"type": "text", "text": _attachment_meta_text(attachment)},
            {
                "type": "image_url",
                "image_url": {"url": _data_url(attachment)},
            },
        ]
    return [{"type": "text", "text": _document_text(attachment)}]


def _openai_responses_attachment_blocks(attachment: dict[str, Any]) -> list[dict[str, Any]]:
    if attachment.get("kind") == "image":
        return [
            {"type": "input_text", "text": _attachment_meta_text(attachment)},
            {"type": "input_image", "image_url": _data_url(attachment)},
        ]
    return [{"type": "input_text", "text": _document_text(attachment)}]


def _claude_attachment_blocks(attachment: dict[str, Any]) -> list[dict[str, Any]]:
    if attachment.get("kind") == "image":
        return [
            {"type": "text", "text": _attachment_meta_text(attachment)},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": attachment.get("mime_type") or "application/octet-stream",
                    "data": attachment.get("data") or "",
                },
            },
        ]
    return [{"type": "text", "text": _document_text(attachment)}]


def _document_text(attachment: dict[str, Any]) -> str:
    return (
        f"文档附件: {attachment.get('filename')}\n"
        f"附件 ID: {attachment.get('id')}\n"
        f"类型: {attachment.get('mime_type') or '未知'}\n"
        f"大小: {attachment.get('size') or 0} bytes\n"
        f"正文:\n{attachment.get('text') or '未提取到正文'}"
    )


def _attachment_meta_text(attachment: dict[str, Any]) -> str:
    return (
        f"图片附件: {attachment.get('filename')}\n"
        f"附件 ID: {attachment.get('id')}\n"
        f"类型: {attachment.get('mime_type') or '未知'}\n"
        f"大小: {attachment.get('size') or 0} bytes"
    )


def _data_url(attachment: dict[str, Any]) -> str:
    return f"data:{attachment.get('mime_type') or 'application/octet-stream'};base64,{attachment.get('data') or ''}"


async def call_provider(request: ProviderRequest) -> dict[str, Any]:
    assert_public_resolved_host(request.url)
    async with httpx.AsyncClient(
        timeout=60, follow_redirects=False, proxy=request.proxy_url
    ) as client:
        resp = await client.post(request.url, headers=request.headers, json=request.json)
        resp.raise_for_status()
        return resp.json()


async def stream_provider(request: ProviderRequest) -> AsyncIterator[dict[str, Any]]:
    """流式调用 provider：yield 增量事件帧，末帧 yield 组装完整响应供 extract_assistant_turn 复用。

    事件帧类型：
      {"type": "text_delta", "delta": str}            —— 文本增量（可多次）
      {"type": "tool_call_delta", "index": int, ...}  —— 工具调用参数碎片（可多次，仅 openai_chat）
      {"type": "tool_call_start", ...}                 —— 工具调用组装完整（claude/openai_responses 的块边界）
      {"type": "turn", "raw": dict}                    —— 末帧：组装出与非流式同构的完整 payload

    provider 不支持 stream（HTTP 400 含 'stream'）时，降级为 call_provider 单次请求，
    包装成单 turn 帧（无增量），保证上游 agent 循环逻辑不变。
    """
    assert_public_resolved_host(request.url)
    provider = request.provider or _provider_of(request)
    payload = copy.deepcopy(request.json)
    payload["stream"] = True
    if provider == "openai_chat":
        # 请求流式末帧携带 usage，供 log_usage 统计真实 token 用量（默认不返回）
        stream_options = payload.get("stream_options")
        if not isinstance(stream_options, dict):
            stream_options = {}
            payload["stream_options"] = stream_options
        stream_options.setdefault("include_usage", True)
    stream_request = ProviderRequest(
        url=request.url, headers=request.headers, json=payload,
        proxy_url=request.proxy_url, provider=provider,
    )
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, read=300.0),
            follow_redirects=False,
            proxy=request.proxy_url,
        ) as client:
            async with client.stream(
                "POST", stream_request.url, headers=stream_request.headers, json=stream_request.json
            ) as resp:
                if resp.status_code == 400:
                    body = await resp.aread()
                    text = body.decode("utf-8", errors="ignore")
                    if "stream" in text.lower():
                        # 降级：provider 不支持 stream，回退非流式
                        async for frame in _fallback_non_stream(request):
                            yield frame
                        return
                    raise httpx.HTTPStatusError(
                        f"provider 400: {text}", request=resp.request, response=resp
                    )
                resp.raise_for_status()
                async for frame in _consume_sse(provider, resp):
                    yield frame
    except httpx.HTTPStatusError:
        raise
    except Exception as exc:
        # 流式建立失败（连接/超时等）——尝试降级一次，避免兼容服务商断流
        if _is_stream_unsupported(exc):
            async for frame in _fallback_non_stream(request):
                yield frame
            return
        raise


def _provider_of(request: ProviderRequest) -> str:
    """从 ProviderRequest.url 反推 provider（DEFAULT_PATHS 匹配），用于选择 SSE 解析器。"""
    path = urlparse(request.url).path
    for name, suffix in DEFAULT_PATHS.items():
        if path.endswith(suffix):
            return name
    return "openai_chat"


def _is_stream_unsupported(exc: Exception) -> bool:
    text = str(exc).lower()
    return "stream" in text or "not support" in text


async def _fallback_non_stream(request: ProviderRequest) -> AsyncIterator[dict[str, Any]]:
    """降级：单次 call_provider 包装成单 turn 帧（无增量）。"""
    raw = await call_provider(request)
    yield {"type": "turn", "raw": raw}


async def _consume_sse(provider: str, resp: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    """解析 SSE 字节流：按空行分帧，逐行 `data:` 取 payload，调用 provider 专属组装器。

    支持 OpenAI `[DONE]` 哨兵与 Anthropic 事件类型前缀（event: xxx）；ping/comment 帧忽略。
    """
    if provider == "openai_chat":
        builder = _OpenAIChatStreamBuilder()
    elif provider == "openai_responses":
        builder = _OpenAIResponsesStreamBuilder()
    else:
        builder = _ClaudeStreamBuilder()

    event_type: str | None = None
    async for raw_line in resp.aiter_lines():
        line = (raw_line or "").strip()
        if not line:
            event_type = None
            continue
        if line.startswith(":"):
            continue  # comment / ping
        if line.startswith("event:"):
            event_type = line[len("event:"):].strip()
            continue
        if not line.startswith("data:"):
            continue
        data_str = line[len("data:"):].strip()
        if data_str == "[DONE]":
            break
        try:
            chunk = json.loads(data_str)
        except json.JSONDecodeError:
            continue
        for frame in builder.feed(chunk, event_type):
            yield frame
    raw = builder.finalize()
    yield {"type": "turn", "raw": raw}


async def call_models(request: ModelsRequest) -> dict[str, Any]:
    assert_public_resolved_host(request.url)
    async with httpx.AsyncClient(
        timeout=30, follow_redirects=False, proxy=request.proxy_url
    ) as client:
        resp = await client.get(request.url, headers=request.headers)
        resp.raise_for_status()
        return resp.json()


def extract_model_ids(payload: dict[str, Any]) -> list[str]:
    ids = []
    for item in payload.get("data", []):
        if isinstance(item, dict) and item.get("id"):
            ids.append(str(item["id"]))
    return sorted(set(ids))


class _OpenAIChatStreamBuilder:
    """聚合 OpenAI chat/completions 流式 chunks，最终组装出与非流式同构的 payload。

    每帧 chunk 形如 {"choices":[{"delta":{"content":"...","tool_calls":[{"index":0,
    "id":"...","function":{"name":"...","arguments":"..."}}]}}]}。
    tool_calls 按 index 归并：首帧带 id+name 标记一个 tool_call_start，后续 arguments 增量累积。
    """

    def __init__(self) -> None:
        self.content_parts: list[str] = []
        # index → {"id","name","arguments","arguments_error"}
        self.tool_calls: dict[int, dict[str, Any]] = {}
        self.finish_reason: str | None = None
        self.emitted_call_indexes: set[int] = set()
        self.usage: dict[str, Any] | None = None
        # 阶段 3：推理链（DeepSeek/通义/智谱等 OpenAI 兼容服务用 reasoning_content 字段）
        self.reasoning_parts: list[str] = []

    def feed(self, chunk: dict[str, Any], _event_type: str | None) -> list[dict[str, Any]]:
        frames: list[dict[str, Any]] = []
        # OpenAI 流式 usage 在末帧顶层（需 stream_options.include_usage=True）
        if isinstance(chunk.get("usage"), dict):
            self.usage = chunk["usage"]
        choices = chunk.get("choices") or []
        if not choices:
            return frames
        choice = choices[0] or {}
        delta = choice.get("delta") or {}
        text = delta.get("content")
        if text:
            self.content_parts.append(text)
            frames.append({"type": "text_delta", "delta": text})
        # reasoning_content（DeepSeek-R1 类）：与正文分缓冲，发 reasoning_delta 帧
        reasoning = delta.get("reasoning_content") or delta.get("reasoning")
        if reasoning:
            self.reasoning_parts.append(reasoning)
            frames.append({"type": "reasoning_delta", "delta": reasoning})
        for call in delta.get("tool_calls") or []:
            idx = call.get("index", 0)
            entry = self.tool_calls.setdefault(
                idx, {"id": "", "name": "", "arguments": "", "arguments_error": None}
            )
            if call.get("id"):
                entry["id"] = str(call["id"])
            function = call.get("function") or {}
            if function.get("name"):
                entry["name"] = str(function["name"])
            arg_delta = function.get("arguments")
            if isinstance(arg_delta, str) and arg_delta:
                entry["arguments"] = entry.get("arguments", "") + arg_delta
        fr = choice.get("finish_reason")
        if fr:
            self.finish_reason = fr
        # 在 finish 时或检测到 name 完整时发射 tool_call_start（按 index 一次）
        for idx, entry in self.tool_calls.items():
            if idx in self.emitted_call_indexes:
                continue
            if entry.get("name") and entry.get("id"):
                self.emitted_call_indexes.add(idx)
                frames.append(
                    {
                        "type": "tool_call_start",
                        "index": idx,
                        "call_id": entry["id"],
                        "name": entry["name"],
                    }
                )
        return frames

    def finalize(self) -> dict[str, Any]:
        # 组装与非流式同构的 choices[0].message
        message: dict[str, Any] = {"content": "".join(self.content_parts)}
        # 阶段 3：保留 reasoning_content 供非流式提取（与正文分字段，不混排）
        if self.reasoning_parts:
            message["reasoning_content"] = "".join(self.reasoning_parts)
        calls = []
        for idx in sorted(self.tool_calls.keys()):
            entry = self.tool_calls[idx]
            arguments_str = entry.get("arguments", "")
            calls.append(
                {
                    "id": entry.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": entry.get("name", ""),
                        "arguments": arguments_str,
                    },
                }
            )
        if calls:
            message["tool_calls"] = calls
        return {
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": self.finish_reason or "stop",
                }
            ],
            "usage": self.usage or {},
        }


class _OpenAIResponsesStreamBuilder:
    """聚合 OpenAI /v1/responses 流式事件，组装出与非流式同构的 payload。

    Responses API 使用 typed events：response.output_text.delta（文本增量）、
    response.function_call_arguments.delta（工具参数碎片，item id 关联）、
    response.output_item.added（新 item，含 id/name/type=function_call）。
    末帧通常有 response.completed 携带完整 payload——若 provider 未发 completed 则自行组装。
    """

    def __init__(self) -> None:
        self.content_parts: list[str] = []
        # item_id → {"call_id","name","arguments"}
        self.calls: dict[str, dict[str, Any]] = {}
        self.emitted_item_ids: set[str] = set()
        self.completed: dict[str, Any] | None = None
        # 阶段 3：推理摘要（Responses API 用 response.reasoning_summary_text.delta）
        self.reasoning_parts: list[str] = []

    def feed(self, chunk: dict[str, Any], event_type: str | None) -> list[dict[str, Any]]:
        frames: list[dict[str, Any]] = []
        etype = chunk.get("type") or event_type or ""
        if etype == "response.output_text.delta":
            delta = chunk.get("delta") or ""
            if delta:
                self.content_parts.append(delta)
                frames.append({"type": "text_delta", "delta": delta})
        elif etype in {"response.reasoning_summary_text.delta", "response.reasoning.delta"}:
            # 阶段 3：推理摘要增量，与正文分缓冲
            delta = chunk.get("delta") or ""
            if delta:
                self.reasoning_parts.append(delta)
                frames.append({"type": "reasoning_delta", "delta": delta})
        elif etype == "response.output_item.added":
            item = chunk.get("item") or {}
            if item.get("type") == "function_call":
                item_id = str(item.get("id", ""))
                entry = self.calls.setdefault(
                    item_id, {"call_id": "", "name": "", "arguments": ""}
                )
                entry["call_id"] = str(item.get("call_id", entry.get("call_id", "")))
                entry["name"] = str(item.get("name", entry.get("name", "")))
        elif etype == "response.function_call_arguments.delta":
            item_id = str(chunk.get("item_id", ""))
            entry = self.calls.setdefault(
                item_id, {"call_id": "", "name": "", "arguments": ""}
            )
            entry["arguments"] += str(chunk.get("delta", "") or "")
        elif etype == "response.function_call_arguments.done":
            item_id = str(chunk.get("item_id", ""))
            entry = self.calls.setdefault(
                item_id, {"call_id": "", "name": "", "arguments": ""}
            )
            if chunk.get("arguments"):
                entry["arguments"] = str(chunk["arguments"])
        elif etype in {"response.completed", "response.incomplete"}:
            resp = chunk.get("response") or {}
            self.completed = resp
        # 发射 tool_call_start（item 一旦有 name+call_id）
        for item_id, entry in self.calls.items():
            if item_id in self.emitted_item_ids:
                continue
            if entry.get("name") and entry.get("call_id"):
                self.emitted_item_ids.add(item_id)
                frames.append(
                    {
                        "type": "tool_call_start",
                        "item_id": item_id,
                        "call_id": entry["call_id"],
                        "name": entry["name"],
                    }
                )
        return frames

    def finalize(self) -> dict[str, Any]:
        if self.completed is not None:
            # 权威完整 payload，直接用
            return self.completed
        # 回退组装
        output = []
        if self.content_parts:
            output.append(
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "".join(self.content_parts)}],
                }
            )
        for item_id in self.calls:
            entry = self.calls[item_id]
            output.append(
                {
                    "type": "function_call",
                    "id": item_id,
                    "call_id": entry.get("call_id", ""),
                    "name": entry.get("name", ""),
                    "arguments": entry.get("arguments", ""),
                }
            )
        text = "".join(self.content_parts)
        return {"output": output, "output_text": text, "status": "completed"}


class _ClaudeStreamBuilder:
    """聚合 Anthropic /v1/messages SSE，组装出与非流式同构的 payload。

    事件序列：message_start（携带 message 骨架）→ content_block_start（块 id+type）→
    content_block_delta（text_delta/input_json_delta）→ content_block_stop → message_delta（stop_reason）→ message_stop。
    """

    def __init__(self) -> None:
        self.blocks: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None
        self.stop_reason: str | None = None
        self.message_skeleton: dict[str, Any] = {}
        self.emitted_block_ids: set[str] = set()
        self.final_usage: dict[str, Any] | None = None  # message_delta 携带的累计 usage

    def feed(self, chunk: dict[str, Any], event_type: str | None) -> list[dict[str, Any]]:
        frames: list[dict[str, Any]] = []
        etype = chunk.get("type") or event_type or ""
        if etype == "message_start":
            self.message_skeleton = dict(chunk.get("message") or {})
        elif etype == "content_block_start":
            block = chunk.get("content_block") or {}
            btype = block.get("type", "text")
            block_id = str(block.get("id") or chunk.get("index", len(self.blocks)))
            self.current = {
                "type": btype,
                "id": block_id,
                "text": "",
                "input_json": "",
                "name": block.get("name", ""),
                "call_id": block_id,
            }
        elif etype == "content_block_delta":
            delta = chunk.get("delta") or {}
            dtype = delta.get("type")
            if self.current is None:
                return frames
            if dtype == "text_delta":
                piece = delta.get("text", "") or ""
                self.current["text"] += piece
                frames.append({"type": "text_delta", "delta": piece})
            elif dtype == "thinking_delta":
                # 阶段 3：Claude 思维链增量（thinking 块），与正文分缓冲
                piece = delta.get("thinking", "") or ""
                self.current["text"] += piece
                frames.append({"type": "reasoning_delta", "delta": piece})
            elif dtype == "input_json_delta":
                self.current["input_json"] += str(delta.get("partial_json", "") or "")
        elif etype == "content_block_stop":
            if self.current is not None:
                self.blocks.append(self.current)
                if self.current.get("type") == "tool_use" and self.current.get("name"):
                    if self.current["id"] not in self.emitted_block_ids:
                        self.emitted_block_ids.add(self.current["id"])
                        frames.append(
                            {
                                "type": "tool_call_start",
                                "block_id": self.current["id"],
                                "call_id": self.current["call_id"],
                                "name": self.current["name"],
                            }
                        )
                self.current = None
        elif etype == "message_delta":
            delta = chunk.get("delta") or {}
            if delta.get("stop_reason"):
                self.stop_reason = delta["stop_reason"]
            usage = chunk.get("usage")
            if isinstance(usage, dict):
                self.final_usage = usage
        elif etype == "message_stop":
            pass
        return frames

    def finalize(self) -> dict[str, Any]:
        content: list[dict[str, Any]] = []
        for block in self.blocks:
            if block.get("type") == "thinking":
                # 阶段 3：保留 thinking 块供非流式提取（signature 等元数据忽略）
                content.append({"type": "thinking", "thinking": block.get("text", "")})
            elif block.get("type") == "text":
                content.append({"type": "text", "text": block.get("text", "")})
            elif block.get("type") == "tool_use":
                raw_input = block.get("input_json", "")
                try:
                    parsed_input = json.loads(raw_input) if raw_input else {}
                except json.JSONDecodeError:
                    parsed_input = raw_input  # 保留原文，extract_assistant_turn 会标 arguments_error
                content.append(
                    {
                        "type": "tool_use",
                        "id": block.get("id", ""),
                        "name": block.get("name", ""),
                        "input": parsed_input,
                    }
                )
        result: dict[str, Any] = {"content": content}
        if self.stop_reason:
            result["stop_reason"] = self.stop_reason
        elif self.message_skeleton.get("stop_reason"):
            result["stop_reason"] = self.message_skeleton["stop_reason"]
        skeleton_usage = (self.message_skeleton or {}).get("usage")
        if isinstance(skeleton_usage, dict):
            result["usage"] = dict(skeleton_usage)
        if isinstance(self.final_usage, dict):
            # message_delta 的累计值（真实 output_tokens）覆盖骨架里的初始值
            merged = dict(result.get("usage") or {})
            merged.update(self.final_usage)
            result["usage"] = merged
        return result


def extract_text(provider: str, payload: dict[str, Any]) -> str:
    if provider == "openai_chat":
        return payload.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
    if provider == "openai_responses":
        if "output_text" in payload:
            return payload["output_text"] or ""
        parts = []
        for item in payload.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"}:
                    parts.append(content.get("text", ""))
        return "\n".join(p for p in parts if p)
    if provider == "claude_messages":
        return "\n".join(
            block.get("text", "")
            for block in payload.get("content", [])
            if block.get("type") == "text"
        )
    return ""


def extract_reasoning(provider: str, payload: dict[str, Any]) -> str:
    """提取 provider 已给出的推理/思维链文本（阶段 3，不主动请求 thinking）。

    - openai_chat: message.reasoning_content（DeepSeek/通义/智谱等兼容服务）
    - openai_responses: output 中 reasoning item 的 summary 文本
    - claude_messages: content 中 thinking 块的 thinking 文本
    provider 不支持时返回空串。
    """
    if provider == "openai_chat":
        message = (payload.get("choices", [{}])[0] if payload.get("choices") else {}).get("message", {}) or {}
        return str(message.get("reasoning_content") or message.get("reasoning") or "")
    if provider == "openai_responses":
        parts = []
        for item in payload.get("output", []) or []:
            if item.get("type") in {"reasoning", "reasoning_summary"}:
                for content in item.get("summary", []) or []:
                    if content.get("type") in {"summary_text", "output_text", "text"}:
                        parts.append(content.get("text", ""))
                if item.get("content"):
                    for content in item.get("content", []) or []:
                        parts.append(content.get("text", ""))
        return "\n".join(p for p in parts if p)
    if provider == "claude_messages":
        parts = []
        for block in payload.get("content", []) or []:
            if block.get("type") == "thinking":
                parts.append(block.get("thinking", "") or block.get("text", ""))
        return "\n".join(p for p in parts if p)
    return ""


def extract_assistant_turn(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    """解析原生 function-calling 响应。

    返回 {"text": str, "tool_calls": [{"id","name","arguments","arguments_error"}],
          "stop_reason": str | None, "reasoning": str}。
    arguments 为 None 表示 JSON 畸形/缺省，arguments_error 给出原因（不抛异常）。
    reasoning 为 provider 已给出的推理文本（无则空串，阶段 3）。
    """
    text = extract_text(provider, payload)
    reasoning = extract_reasoning(provider, payload)
    tool_calls: list[dict[str, Any]] = []
    stop_reason: str | None = None
    if provider == "openai_chat":
        choice = payload.get("choices", [{}])[0] if payload.get("choices") else {}
        stop_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
        message = (choice or {}).get("message", {}) or {}
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            arguments, error = _parse_tool_arguments(function.get("arguments"))
            tool_calls.append(
                {
                    "id": str(call.get("id", "")),
                    "name": str(function.get("name", "")),
                    "arguments": arguments,
                    "arguments_error": error,
                }
            )
    elif provider == "openai_responses":
        # status=incomplete 表示输出被 max_output_tokens 等截断；取 incomplete_details.reason
        # 作为 stop_reason（如 "max_output_tokens"），_is_truncated 据此识别。
        status = payload.get("status")
        if status == "incomplete":
            reason = (payload.get("incomplete_details") or {}).get("reason")
            stop_reason = reason or "incomplete"
        elif status:
            stop_reason = status
        for item in payload.get("output", []) or []:
            if item.get("type") != "function_call":
                continue
            arguments, error = _parse_tool_arguments(item.get("arguments"))
            tool_calls.append(
                {
                    "id": str(item.get("call_id", "")),
                    "name": str(item.get("name", "")),
                    "arguments": arguments,
                    "arguments_error": error,
                }
            )
    elif provider == "claude_messages":
        stop_reason = payload.get("stop_reason")
        for block in payload.get("content", []) or []:
            if block.get("type") != "tool_use":
                continue
            raw_input = block.get("input")
            if isinstance(raw_input, dict):
                arguments, error = raw_input, None
            else:
                arguments, error = _parse_tool_arguments(raw_input)
            tool_calls.append(
                {
                    "id": str(block.get("id", "")),
                    "name": str(block.get("name", "")),
                    "arguments": arguments,
                    "arguments_error": error,
                }
            )
    return {"text": text, "tool_calls": tool_calls, "stop_reason": stop_reason, "reasoning": reasoning}


def _parse_tool_arguments(raw: Any) -> tuple[dict[str, Any] | None, str | None]:
    """解析工具参数：dict 直接用；JSON 字符串解析；畸形返回 (None, 错误信息)。"""
    if isinstance(raw, dict):
        return raw, None
    if raw is None or raw == "":
        return None, None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        return None, f"参数 JSON 解析失败: {exc}"
    if isinstance(parsed, dict):
        return parsed, None
    return None, "参数 JSON 不是对象"


def _extract_json_objects(text: str) -> list[str]:
    """从文本中宽松提取所有顶层 JSON 对象字面量（供 onesot JSON 生成回退解析使用）。"""
    decoder = json.JSONDecoder()
    objects = []
    for match in re.finditer(r"\{", text):
        try:
            _, end = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        objects.append(text[match.start() : match.start() + end])
    return objects
