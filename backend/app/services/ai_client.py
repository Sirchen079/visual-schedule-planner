from __future__ import annotations

import copy
import json
import re
import socket
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
    )


def _apply_native_web_search(
    *,
    provider: str,
    payload: dict[str, Any],
    options: dict[str, Any],
) -> None:
    additions = copy.deepcopy(NATIVE_WEB_SEARCH_DEFAULTS.get(provider, {}))
    _merge_request_options(additions, options)
    payload.update(additions)


def _merge_request_options(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    for key, value in (source or {}).items():
        if isinstance(target.get(key), dict) and isinstance(value, dict):
            _merge_request_options(target[key], value)
        else:
            target[key] = value
    return target


def _provider_messages(provider: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "role": message.get("role", "user"),
            "content": _provider_content(
                provider,
                str(message.get("content", "")),
                message.get("attachments") or [],
            ),
        }
        for message in messages
    ]


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


def parse_assistant_plan(text: str) -> dict[str, Any]:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    candidates = [match.group(1)] if match else _extract_json_objects(text)
    data = None
    for raw in candidates:
        try:
            candidate = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and (
            {"reply", "tools", "dangerous_actions"} & set(candidate.keys())
        ):
            data = candidate
            break
    if data is None:
        return {"reply": text, "tools": [], "dangerous_actions": []}
    return {
        "reply": str(data.get("reply", "")),
        "tools": data.get("tools", []) if isinstance(data.get("tools", []), list) else [],
        "dangerous_actions": (
            data.get("dangerous_actions", [])
            if isinstance(data.get("dangerous_actions", []), list)
            else []
        ),
    }


def _extract_json_objects(text: str) -> list[str]:
    decoder = json.JSONDecoder()
    objects = []
    for match in re.finditer(r"\{", text):
        try:
            _, end = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        objects.append(text[match.start() : match.start() + end])
    return objects
