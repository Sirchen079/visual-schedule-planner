"""DB-configured, bounded web providers. No provider settings come from page content.

MCP bindings only rename query/URL/limit fields; they cannot supply commands, headers,
templates or arbitrary arguments. A saved, enabled server and its existing trust and
readonly auto-approval are required on every call. Tools without readOnlyHint are
rejected even when a general MCP grant exists. Remote readers enforce their own
redirect/DNS policy; the builtin reader retains its per-hop public-URL checks.

Tavily API references (checked 2026-09-06):
https://docs.tavily.com/documentation/api-reference/endpoint/search
https://docs.tavily.com/documentation/api-reference/endpoint/extract
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy.orm import Session

from zhishi.adapters import mcp_client, web
from zhishi.domain import settingsvc
from zhishi.domain.models import AppSetting, MCPServer
from zhishi.infra import secrets

Provider = Literal["builtin", "tavily", "mcp"]
MAX_RESULTS = 10
MAX_QUERY_CHARS = 500
MAX_URL_CHARS = 2000
MAX_DESCRIPTION_CHARS = 1000
MAX_CONTENT_CHARS = 8000
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
CONFIG_KEY = "web_services_config"
KEY_REF_SETTING = "web_services_tavily_key_ref"
MCP_CONSENT_KEY = "web_services_mcp_bindings"
Name = Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[A-Za-z_][A-Za-z0-9_-]*$")]
Path = Annotated[str, Field(max_length=200, pattern=r"^(?:[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+){0,7})?$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MCPSearchBinding(StrictModel):
    server_id: int = Field(gt=0)
    tool_name: Name
    query_argument: Name = "query"
    limit_argument: Name | None = "max_results"
    results_path: Path = "results"
    title_field: Name = "title"
    url_field: Name = "url"
    description_field: Name = "content"

    @model_validator(mode="after")
    def distinct_arguments(self):
        if self.query_argument == self.limit_argument:
            raise ValueError("query_argument 与 limit_argument 不能相同")
        return self


class MCPFetchBinding(StrictModel):
    server_id: int = Field(gt=0)
    tool_name: Name
    url_argument: Name = "url"
    url_as_list: bool = False
    content_path: Path = ""  # plain text; e.g. results.0.raw_content for Tavily MCP


class WebServicesConfig(StrictModel):
    search_provider: Provider = "builtin"
    fetch_provider: Provider = "builtin"
    tavily_search_depth: Literal["basic", "advanced"] = "basic"
    tavily_extract_depth: Literal["basic", "advanced"] = "basic"
    mcp_search: MCPSearchBinding | None = None
    mcp_fetch: MCPFetchBinding | None = None

    @model_validator(mode="after")
    def selected_bindings_exist(self):
        if self.search_provider == "mcp" and self.mcp_search is None:
            raise ValueError("MCP 搜索需要 mcp_search 配置")
        if self.fetch_provider == "mcp" and self.mcp_fetch is None:
            raise ValueError("MCP 读取需要 mcp_fetch 配置")
        return self


class WebServiceError(ValueError):
    """Only locally authored, credential-free messages may use this exception."""


def get_config(db: Session) -> WebServicesConfig:
    raw = settingsvc.get_setting(db, CONFIG_KEY)
    if not raw:
        return WebServicesConfig()
    try:
        return WebServicesConfig.model_validate_json(raw)
    except ValidationError:
        raise WebServiceError("网页服务配置无效，请重新保存配置") from None


def _server(db: Session, server_id: int) -> MCPServer:
    row = db.get(MCPServer, server_id, populate_existing=True)
    if row is None or not row.enabled:
        raise WebServiceError("指定的 MCP 服务器不存在或未启用")
    if row.transport not in ("stdio", "http"):
        raise WebServiceError("MCP 传输类型不受支持")
    if row.transport == "stdio" and not row.trusted:
        raise WebServiceError("必须先在 MCP 设置中信任该 stdio 服务器")
    if not row.auto_approve_readonly:
        raise WebServiceError("必须先在 MCP 设置中允许只读工具；网页工具不能绕过审批")
    return row


def save_config(db: Session, config: WebServicesConfig) -> WebServicesConfig:
    # Check live tool readiness before persistence, without actually searching/fetching.
    # _server rejects untrusted stdio before even building an MCP client.
    fingerprints = _saved_fingerprints(db)
    if config.search_provider == "mcp":
        binding = config.mcp_search
        args = {binding.query_argument: "validation"}
        if binding.limit_argument:
            args[binding.limit_argument] = 5
        fingerprints["search"], _ = _mcp(db, binding, args, validate_only=True)
    if config.fetch_provider == "mcp":
        binding = config.mcp_fetch
        url = "https://example.com/"
        fingerprints["fetch"], _ = _mcp(
            db, binding, {binding.url_argument: [url] if binding.url_as_list else url},
            validate_only=True)
    # Config and its authorization fingerprints must change in the same transaction.
    for key, value in ((CONFIG_KEY, config.model_dump_json()),
                       (MCP_CONSENT_KEY, json.dumps(fingerprints))):
        row = db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=value))
        else:
            row.value = value
    db.commit()
    return config


def _saved_fingerprints(db: Session) -> dict:
    try:
        data = json.loads(settingsvc.get_setting(db, MCP_CONSENT_KEY) or "{}")
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _binding_fingerprint(row: MCPServer, binding) -> str:
    # Only the hash is stored. Include creation identity for SQLite row-id reuse,
    # secrets for credential rotation, and the mapping to bind the exact saved intent.
    identity = {name: getattr(row, name) for name in (
        "id", "created_at", "transport", "command", "args_json", "env_json", "url", "headers_json")}
    identity["binding"] = binding.model_dump()
    return hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()


def _tavily_key(db: Session) -> str | None:
    ref = settingsvc.get_setting(db, KEY_REF_SETTING)
    return secrets.load_api_key(ref) if ref else None


def has_tavily_key(db: Session) -> bool:
    return bool(_tavily_key(db))


def save_tavily_key(db: Session, key: str) -> None:
    if not isinstance(key, str) or not key.strip() or len(key) > 4096:
        raise WebServiceError("API key 不能为空且最多4096字符")
    old_ref = settingsvc.get_setting(db, KEY_REF_SETTING)
    new_ref = f"web-services:tavily:{uuid4().hex}"
    try:
        secrets.store_api_key(new_ref, key.strip())
        settingsvc.set_setting(db, KEY_REF_SETTING, new_ref)
    except Exception:  # noqa: BLE001 — keyring/DB errors can contain the supplied secret
        db.rollback()
        secrets.delete_api_key(new_ref)
        raise WebServiceError("无法保存凭据，请检查系统 keyring 后重试") from None
    if old_ref:
        secrets.delete_api_key(old_ref)


def delete_tavily_key(db: Session) -> None:
    ref = settingsvc.get_setting(db, KEY_REF_SETTING)
    settingsvc.set_setting(db, KEY_REF_SETTING, "")
    if ref:
        secrets.delete_api_key(ref)


def _provider(config: WebServicesConfig, operation: str, explicit: Provider | None) -> Provider:
    selected = explicit if explicit is not None else getattr(config, f"{operation}_provider")
    if selected not in ("builtin", "tavily", "mcp"):
        raise WebServiceError("provider 仅支持 builtin、tavily、mcp")
    return selected


def _public_url(url: str, *, resolve: bool) -> str:
    if not isinstance(url, str) or not url.strip() or len(url) > MAX_URL_CHARS:
        raise WebServiceError("网页地址不能为空且最多2000字符")
    url = url.strip()
    try:
        parts = urlsplit(url)
        if (parts.scheme not in ("http", "https") or not parts.hostname
                or parts.username is not None or parts.password is not None
                or any(ord(c) < 33 for c in url)):
            raise ValueError
        _ = parts.port
        # Search hits are not fetched here; resolving each would add unbounded network work.
        import ipaddress
        try:
            ip = ipaddress.ip_address(parts.hostname)
        except ValueError:
            ip = None
        if ip is not None and not ip.is_global:
            raise ValueError
        if resolve:
            web._validate_public_url(url)
    except ValueError:
        raise WebServiceError("仅支持可解析的公网 http(s) 地址，不允许内网或 URL 凭据") from None
    return url


def _redact(text: str, values: list[str]) -> str:
    for value in sorted(set(values), key=len, reverse=True):
        if value:
            text = text.replace(value, "***")
    return text


def _text(value, cap: int, sensitive: list[str]) -> str:
    return _redact(value, sensitive).strip()[:cap] if isinstance(value, str) else ""


def _normalize_search(rows, limit: int, *, title: str = "title", url: str = "url",
                      description: str = "description", sensitive: list[str] | None = None) -> list[dict]:
    if not isinstance(rows, list):
        raise WebServiceError("搜索服务返回格式无效，请检查 MCP 结果字段映射")
    found, seen = [], set()
    for row in rows[:100]:
        if not isinstance(row, dict):
            continue
        if row.get("error"):
            raise WebServiceError("搜索服务返回错误，请检查服务配置或稍后重试")
        try:
            link = _public_url(row.get(url), resolve=False)
        except WebServiceError:
            continue
        # Do not turn a credential-bearing URL into a different, apparently valid citation.
        if _redact(link, sensitive or []) != link or link in seen:
            continue
        seen.add(link)
        found.append({"title": _text(row.get(title), 300, sensitive or []), "url": link,
                      "description": _text(row.get(description), MAX_DESCRIPTION_CHARS,
                                           sensitive or [])})
        if len(found) == limit:
            break
    if rows and not found:
        raise WebServiceError("搜索服务未返回有效网页链接，请检查结果字段映射")
    return found


def _tavily(db: Session, endpoint: str, payload: dict,
            client: httpx.Client | None) -> tuple[dict, list[str]]:
    key = _tavily_key(db)
    if not key:
        raise WebServiceError("请先在网页服务设置中保存 Tavily API key")
    owned = client is None
    c = client if client is not None else httpx.Client(timeout=30)
    try:
        with c.stream("POST", f"https://api.tavily.com/{endpoint}", json=payload,
                      headers={"Authorization": f"Bearer {key}"}, timeout=30,
                      follow_redirects=False) as response:
            if response.status_code != 200:
                raise WebServiceError(f"Tavily 请求失败（HTTP {response.status_code}），请检查凭据或配额")
            chunks, total = [], 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise WebServiceError("网页服务响应超过2MB，请缩小请求范围")
                chunks.append(chunk)
        data = json.loads(b"".join(chunks))
        if not isinstance(data, dict):
            raise WebServiceError("Tavily 返回格式无效")
        return data, [key]
    except WebServiceError:
        raise
    except Exception:  # noqa: BLE001 — external response/transport details are untrusted
        raise WebServiceError("Tavily 请求失败，请检查网络或稍后重试") from None
    finally:
        if owned:
            c.close()


def _path(value, path: str):
    # Literal dict keys / list indices only. No templates, evaluation, wildcards or attributes.
    try:
        for part in path.split(".") if path else []:
            value = value[int(part)] if isinstance(value, list) and part.isdigit() else value[part]
        return value
    except (KeyError, IndexError, TypeError, ValueError):
        raise WebServiceError("MCP 返回格式与保存的结果字段路径不一致") from None


def _decode_mcp(value):
    # MCPToolset returns structured dicts, text, or a list of text/media parts.
    for _ in range(4):
        if isinstance(value, str):
            if len(value.encode("utf-8")) > MAX_RESPONSE_BYTES:
                raise WebServiceError("MCP 响应超过2MB")
            try:
                value = json.loads(value)
            except ValueError:
                return value
        elif isinstance(value, dict) and ("isError" in value or "structuredContent" in value):
            if value.get("isError"):
                raise WebServiceError("MCP 工具返回错误")
            value = value.get("structuredContent") or value.get("content")
        elif isinstance(value, list) and value and all(isinstance(x, str) for x in value):
            value = "\n".join(value)
        elif (isinstance(value, list) and value
              and all(isinstance(x, dict) and x.get("type") == "text" for x in value)):
            value = "\n".join(x.get("text", "") for x in value)
        else:
            return value
    return value


def _check_arguments(schema: dict, args: dict) -> None:
    """Fail closed for fields the configured simple mapping cannot safely populate."""
    properties = schema.get("properties", {})
    if schema.get("type") != "object" or not isinstance(properties, dict):
        raise WebServiceError("MCP 工具参数必须是具有明确字段的 object schema")
    if any(name not in args for name in schema.get("required", [])):
        raise WebServiceError("MCP 工具还有未映射的必填参数，请选择兼容的只读工具")
    for name, value in args.items():
        field = properties.get(name, {})
        expected = "array" if isinstance(value, list) else "integer" if type(value) is int else "string"
        if field.get("type") != expected:
            raise WebServiceError("MCP 参数映射与工具 schema 类型不一致")
        if expected == "array" and field.get("items", {}).get("type") != "string":
            raise WebServiceError("MCP URL 列表参数必须为 string 数组")


def _mcp(db: Session, binding, args: dict, *, validate_only: bool = False):
    row = _server(db, binding.server_id)
    fingerprint = _binding_fingerprint(row, binding)
    operation = "search" if isinstance(binding, MCPSearchBinding) else "fetch"
    if not validate_only and _saved_fingerprints(db).get(operation) != fingerprint:
        raise WebServiceError("MCP 服务器或映射已变更，请重新保存网页服务配置后使用")
    timeout = min(60, max(1, row.timeout_sec or 30))

    async def invoke():
        # Fresh toolset and a single session: no stale readonly metadata or pre-parse truncation.
        async with asyncio.timeout(timeout):
            async with mcp_client.build_toolset(row, timeout) as toolset:
                records = [mcp_client.tool_to_record(t) for t in await toolset.list_tools()]
                record = next((t for t in records if t["name"] == binding.tool_name), None)
                if record is None or not record["read_only"]:
                    raise WebServiceError("指定 MCP 工具不存在或未声明只读，不能通过网页工具调用")
                _check_arguments(record["input_schema"], args)
                if validate_only:
                    return fingerprint
                result = await toolset.direct_call_tool(binding.tool_name, args)
                if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > MAX_RESPONSE_BYTES:
                    raise WebServiceError("MCP 响应超过2MB")
                return _decode_mcp(result)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise WebServiceError("同步网页接口须在线程中调用，异步调用方请使用 asyncio.to_thread")
    try:
        result = asyncio.run(invoke())
        # Unlike generic MCP error sanitation, redact even short credential values in results.
        sensitive = []
        for raw in (row.env_json, row.headers_json):
            values = json.loads(raw or "{}")
            for value in values.values():
                if value:
                    text = str(value)
                    sensitive.append(text)
                    # Authorization errors commonly echo only the token, without its scheme.
                    scheme, _, token = text.partition(" ")
                    if scheme.lower() in ("bearer", "basic") and token:
                        sensitive.append(token)
        return result, sensitive
    except WebServiceError:
        raise
    except Exception:  # noqa: BLE001 — never expose arbitrary MCP/transport exceptions
        raise WebServiceError("MCP 网页服务调用失败，请检查连接、工具及参数映射") from None


def search(db: Session, query: str, limit: int = 5, *, provider: Provider | None = None,
           client: httpx.Client | None = None) -> list[dict]:
    """At most 10 {title,url,description} rows; errors are a single {error} row.

    Explicit provider overrides the saved default for this request only. Never falls
    back to another provider on an error. MCP IDs, names and mappings stay in settings.
    """
    try:
        if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_CHARS:
            raise WebServiceError("搜索词不能为空且最多500字符")
        if type(limit) is not int:
            raise WebServiceError("max_results 必须为整数")
        limit = min(MAX_RESULTS, max(1, limit))
        config = get_config(db)
        selected = _provider(config, "search", provider)
        if selected == "builtin":
            rows = web.search(query.strip(), limit=limit, **({"client": client} if client else {}))
            return _normalize_search(rows, limit)
        if selected == "tavily":
            data, sensitive = _tavily(db, "search", {
                "query": query.strip(), "max_results": limit,
                "search_depth": config.tavily_search_depth, "topic": "general",
                "auto_parameters": False, "include_answer": False,
                "include_raw_content": False, "include_images": False}, client)
            return _normalize_search(data.get("results"), limit, description="content",
                                     sensitive=sensitive)
        binding = config.mcp_search
        if binding is None:
            raise WebServiceError("请先配置指定的 MCP 搜索工具")
        args = {binding.query_argument: query.strip()}
        if binding.limit_argument:
            args[binding.limit_argument] = limit
        data, sensitive = _mcp(db, binding, args)
        return _normalize_search(_path(data, binding.results_path), limit,
            title=binding.title_field, url=binding.url_field,
            description=binding.description_field, sensitive=sensitive)
    except WebServiceError as exc:
        return [{"error": str(exc)}]
    except Exception:  # noqa: BLE001 — public tool errors must stay bounded and nonsecret
        return [{"error": "搜索失败，请检查网页服务配置或稍后重试"}]


def fetch(db: Session, url: str, *, provider: Provider | None = None,
          client: httpx.Client | None = None) -> str:
    """Return <=8000 text characters; raise sanitized WebServiceError on failure."""
    return _fetch(db, url, provider=provider, client=client, document=False)


def fetch_document(db: Session, url: str, *, provider: Provider | None = None,
                   client: httpx.Client | None = None) -> web.WebDocument:
    """Archive the configured provider's bounded body without expanding model context."""
    return _fetch(db, url, provider=provider, client=client, document=True)


def _fetch(db: Session, url: str, *, provider: Provider | None,
           client: httpx.Client | None, document: bool):
    try:
        config = get_config(db)
        selected = _provider(config, "fetch", provider)
        # Builtin fetch already checks DNS and every redirect. Remote services
        # need the initial public-address check here before handing them the URL.
        url = _public_url(url, resolve=selected != "builtin")
        sensitive = []
        if selected == "builtin":
            if document:
                result = web.fetch_document(url, **({"client": client} if client else {}))
                if not result.text.strip():
                    raise WebServiceError("网页未返回可读正文，请更换公开链接")
                return result
            content = web.fetch(url, **({"client": client} if client else {}))
        elif selected == "tavily":
            data, sensitive = _tavily(db, "extract", {
                "urls": [url], "extract_depth": config.tavily_extract_depth,
                "format": "text", "include_images": False}, client)
            results = data.get("results")
            if not isinstance(results, list) or not results or not isinstance(results[0], dict):
                raise WebServiceError("Tavily 无法读取该网页，请更换公开链接或稍后重试")
            if results[0].get("url") != url:
                raise WebServiceError("Tavily 返回了不同网页的正文，未采纳该结果")
            content = results[0].get("raw_content")
        else:
            binding = config.mcp_fetch
            if binding is None:
                raise WebServiceError("请先配置指定的 MCP 读取工具")
            args = {binding.url_argument: [url] if binding.url_as_list else url}
            data, sensitive = _mcp(db, binding, args)
            content = _path(data, binding.content_path)
        if not isinstance(content, str):
            raise WebServiceError("网页服务正文格式无效，请检查结果字段映射")
        content = _redact(content, sensitive).strip()
        if not content:
            raise WebServiceError("网页未返回可读正文，请更换公开链接")
        if document:
            truncated = len(content) > web.MAX_DOCUMENT_CHARS
            warnings = [f'正文由 {selected} 服务提供，无法确认该服务是否省略了页面内容；仅引用实际保存的片段。']
            if truncated:
                warnings.append(f'返回正文超过 {web.MAX_DOCUMENT_CHARS} 字符，后续内容尚未保存。')
            return web.WebDocument(content[:web.MAX_DOCUMENT_CHARS], True, warnings)
        return content[:MAX_CONTENT_CHARS]
    except WebServiceError:
        raise
    except Exception:  # noqa: BLE001 — public tool errors must stay bounded and nonsecret
        raise WebServiceError("网页读取失败，请检查网页服务配置或稍后重试") from None
