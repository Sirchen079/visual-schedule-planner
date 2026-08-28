"""MCP（Model Context Protocol）服务器配置与调用服务。

职责：
- CRUD：管理用户配置的 MCP 服务器（stdio / http 两种传输）。
- 连接测试：建立连接 → initialize → list_tools，回写 last_status/last_error。
- 工具清单（带 60s 内存缓存）：供 Agent 循环注入 system prompt。
- 工具调用：命名空间隔离 mcp__s{服务器id}__{原名}，结果降级为纯文本。

异步桥：MCP SDK 原生 anyio/async，而现有 Agent 循环是同步代码。这里常驻一个后台
事件循环线程，所有对外同步函数经 run_coroutine_threadsafe 提交到该线程执行，
绝不碰 TestClient / FastAPI 自身的事件循环（避免「已有运行中 loop」崩溃）。

安全：env / headers 的值在响应、日志、错误信息中一律脱敏；stdio 走参数数组，
永不拼 shell 字符串。
"""
from __future__ import annotations

import asyncio
import atexit
import json
import os
import re
import threading
import time
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MCPServer
from app.schemas import (
    MCPServerCreate,
    MCPServerResponse,
    MCPServerUpdate,
    MCPTestResult,
    MCPToolInfo,
    _validate_mcp_fields,
)
from app.services.ai_config_service import mask_key

# OpenAI 函数名风格上限 64 字符；这些名字会进 prompt 并被模型原样回传，保留截断保底
MAX_TOOL_NAME_LEN = 64
INIT_TIMEOUT_SEC = 15  # 连接 initialize 硬上限（安全红线 2.6）
CALL_TIMEOUT_CAP = 120  # 单次工具调用硬上限（安全红线 2.6）
TOOL_CACHE_TTL = 60  # 工具清单缓存秒数

# region ---- 异步桥：常驻后台事件循环线程 ----

_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None
_loop_lock = threading.Lock()


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _loop, _loop_thread
    if _loop is not None:
        return _loop
    with _loop_lock:
        if _loop is None:
            loop = asyncio.new_event_loop()
            thread = threading.Thread(target=loop.run_forever, daemon=True, name="mcp-async")
            thread.start()
            _loop = loop
            _loop_thread = thread
            atexit.register(_stop_loop)
        return _loop


def _stop_loop() -> None:
    global _loop
    loop = _loop
    if loop is None:
        return
    try:
        loop.call_soon_threadsafe(loop.stop)
    except RuntimeError:
        pass


def _run_async(coro: Any, wall_timeout: float) -> Any:
    """把协程提交到后台循环同步等待结果。超时取消协程并抛 TimeoutError。

    取消 future 会让后台协程收到 CancelledError，进而触发 async with 的资源释放
    （stdio 子进程随之终止），避免超时后子进程在后台循环常驻泄漏。
    """
    loop = _ensure_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(timeout=wall_timeout)
    except TimeoutError:
        future.cancel()
        raise


# endregion


# region ---- JSON 字段（反）序列化与脱敏 ----

def _args_from_json(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _args_to_json(args: list[str] | None) -> str:
    return json.dumps([str(item) for item in (args or [])], ensure_ascii=False)


def _dict_from_json(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(k): str(v) for k, v in parsed.items()}


def _dict_to_json(value: dict[str, str] | None) -> str:
    return json.dumps({str(k): str(v) for k, v in (value or {}).items()}, ensure_ascii=False)


def _mask_dict(value: dict[str, str]) -> dict[str, str]:
    """响应脱敏：每个 value 用 mask_key（前3后4，过短全掩）。"""
    return {name: mask_key(str(v)) for name, v in value.items()}


def _merge_masked_dict(current: dict[str, str], incoming: dict[str, str] | None) -> dict[str, str]:
    """更新合并：incoming 中等于「现值脱敏形态」的视为未改，保留现值（留空=不变语义）。"""
    merged: dict[str, str] = {}
    for name, value in (incoming or {}).items():
        stored = current.get(name)
        if stored is not None and value == mask_key(stored):
            merged[name] = stored
        else:
            merged[name] = value
    return merged


def _safe_error(server: MCPServer, exc: BaseException) -> str:
    """错误文本脱敏：剔除本服务器 env/headers 的明文值，截断到 300 字符。"""
    text = str(exc) or exc.__class__.__name__
    secrets: list[str] = []
    secrets.extend(_dict_from_json(server.env).values())
    secrets.extend(_dict_from_json(server.headers).values())
    for value in secrets:
        if value and len(value) >= 4 and value in text:
            text = text.replace(value, "***")
    text = re.sub(
        r"((?:api[_-]?key|token|secret|password|authorization)[\"']?\s*[:=]\s*[\"']?)[^\"',\s}]+",
        r"\1[已隐藏]",
        text,
        flags=re.I,
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300] if text else exc.__class__.__name__


# endregion


# region ---- 命名空间 ----

def namespaced_name(server_id: int, original_name: str) -> str:
    return f"mcp__s{server_id}__{original_name}"


def parse_namespaced(name: str) -> tuple[int, str] | None:
    """解析 mcp__s{id}__{原名}，失败返回 None。"""
    prefix = "mcp__s"
    if not name.startswith(prefix):
        return None
    rest = name[len(prefix):]
    sep = rest.find("__")
    if sep <= 0:
        return None
    try:
        server_id = int(rest[:sep])
    except ValueError:
        return None
    return server_id, rest[sep + 2:]


def _truncate_tool_name(server_id: int, original_name: str) -> str:
    """超长工具名截断 + 6 位 hash 保唯一，贴近 OpenAI 函数名 64 字符上限。"""
    full = namespaced_name(server_id, original_name)
    if len(full) <= MAX_TOOL_NAME_LEN:
        return full
    digest = f"{abs(hash(full)) % 0xFFFFFF:06x}"
    budget = MAX_TOOL_NAME_LEN - len(f"mcp__s{server_id}__") - len(digest) - 1
    trimmed = original_name[: max(budget, 8)]
    return f"mcp__s{server_id}__{trimmed}_{digest}"


# endregion


# region ---- 连接（async） ----

@asynccontextmanager
async def _session_for(server: MCPServer):
    """按 transport 建立 ClientSession 并完成 initialize，统一资源释放。"""
    call_timeout = min(max(server.timeout_sec, 5), CALL_TIMEOUT_CAP)
    read_timeout = timedelta(seconds=call_timeout)
    if server.transport == "stdio":
        if not server.command:
            raise ValueError("stdio 服务器缺少 command")
        # 在最小系统环境上合并用户配置（继承 PATH/SystemRoot 等，保证子进程能跑）
        env = dict(os.environ)
        env.update(_dict_from_json(server.env))
        from mcp.client.stdio import StdioServerParameters, stdio_client

        params = StdioServerParameters(
            command=server.command,
            args=list(_args_from_json(server.args)),
            env=env,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=read_timeout) as session:  # type: ignore[name-defined]
                await asyncio.wait_for(session.initialize(), timeout=INIT_TIMEOUT_SEC)
                yield session
    elif server.transport == "http":
        if not server.url:
            raise ValueError("http 服务器缺少 url")
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(
            url=server.url,
            headers=_dict_from_json(server.headers) or None,
            timeout=call_timeout,
        ) as (read, write, _get_session_id):
            async with ClientSession(read, write, read_timeout_seconds=read_timeout) as session:  # type: ignore[name-defined]
                await asyncio.wait_for(session.initialize(), timeout=INIT_TIMEOUT_SEC)
                yield session
    else:
        raise ValueError(f"不支持的传输类型: {server.transport}")


def _tool_read_only(tool: Any) -> bool:
    annotations = getattr(tool, "annotations", None)
    return bool(getattr(annotations, "readOnlyHint", False))


async def _do_list_tools(server: MCPServer) -> list[dict[str, Any]]:
    """返回原始工具描述列表：name/description/input_schema/read_only。"""
    async with _session_for(server) as session:
        result = await session.list_tools()
    tools = []
    for tool in result.tools:
        tools.append(
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema or {},
                "read_only": _tool_read_only(tool),
            }
        )
    return tools


def _flatten_call_result(result: Any) -> str:
    """把 MCP call_tool 的 content 块拼成纯文本；非文本块降级为占位说明。"""
    parts: list[str] = []
    for block in getattr(result, "content", None) or []:
        btype = getattr(block, "type", None)
        if btype == "text":
            parts.append(str(getattr(block, "text", "")))
        elif btype == "resource":
            resource = getattr(block, "resource", None)
            parts.append(
                f"[资源内容: {getattr(resource, 'uri', '未知')}]"
                + (f" {getattr(resource, 'text', '')}" if getattr(resource, "text", None) else "")
            )
        else:
            parts.append(f"[{btype or '二进制'}内容已省略]")
    text = "\n".join(part for part in parts if part is not None).strip()
    if getattr(result, "isError", False):
        return f"MCP 工具返回错误：{text or '（无文本说明）'}"
    return text or "(工具未返回文本内容)"


async def _do_call_tool(server: MCPServer, tool_name: str, arguments: dict[str, Any]) -> str:
    call_timeout = min(max(server.timeout_sec, 5), CALL_TIMEOUT_CAP)
    async with _session_for(server) as session:
        result = await asyncio.wait_for(
            session.call_tool(tool_name, arguments or {}, read_timeout_seconds=timedelta(seconds=call_timeout)),
            timeout=call_timeout + 5,
        )
    return _flatten_call_result(result)


# 为类型提示延迟引入 ClientSession（避免模块加载期硬依赖 mcp，便于无 SDK 环境收集）
try:
    from mcp.client.session import ClientSession  # type: ignore
except Exception:  # pragma: no cover - SDK 缺失时仍可加载本模块，调用时再报错
    ClientSession = None  # type: ignore[assignment]


# endregion


# region ---- 工具清单缓存 ----

# server_id -> (timestamp, tools_or_None, error_or_None)
_tool_cache: dict[int, tuple[float, list[dict[str, Any]] | None, str | None]] = {}
_cache_lock = threading.Lock()


def _cache_get(server_id: int) -> tuple[list[dict[str, Any]] | None, str | None] | None:
    now = time.time()
    with _cache_lock:
        entry = _tool_cache.get(server_id)
        if entry and now - entry[0] < TOOL_CACHE_TTL:
            return entry[1], entry[2]
    return None


def _cache_put(server_id: int, tools: list[dict[str, Any]] | None, error: str | None) -> None:
    with _cache_lock:
        _tool_cache[server_id] = (time.time(), tools, error)


def invalidate_cache(server_id: int) -> None:
    with _cache_lock:
        _tool_cache.pop(server_id, None)


# endregion


# region ---- 对外：CRUD ----

def _to_response(server: MCPServer) -> MCPServerResponse:
    return MCPServerResponse(
        id=server.id,
        name=server.name,
        transport=server.transport,
        command=server.command,
        args=_args_from_json(server.args),
        env=_mask_dict(_dict_from_json(server.env)),
        url=server.url,
        headers=_mask_dict(_dict_from_json(server.headers)),
        timeout_sec=server.timeout_sec,
        enabled=server.enabled,
        auto_approve_readonly=server.auto_approve_readonly,
        last_status=server.last_status,
        last_error=server.last_error,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


def list_servers(db: Session) -> list[MCPServerResponse]:
    rows = db.execute(select(MCPServer).order_by(MCPServer.created_at.desc())).scalars().all()
    return [_to_response(row) for row in rows]


def get_server(db: Session, server_id: int) -> MCPServerResponse | None:
    server = db.get(MCPServer, server_id)
    return _to_response(server) if server else None


def create_server(db: Session, payload: MCPServerCreate) -> MCPServerResponse:
    data = payload.model_dump()
    data["args"] = _args_to_json(data.pop("args", []))
    data["env"] = _dict_to_json(data.pop("env", {}))
    data["headers"] = _dict_to_json(data.pop("headers", {}))
    server = MCPServer(**data)
    db.add(server)
    db.commit()
    db.refresh(server)
    return _to_response(server)


def update_server(db: Session, server_id: int, payload: MCPServerUpdate) -> MCPServerResponse | None:
    server = db.get(MCPServer, server_id)
    if server is None:
        return None
    data = payload.model_dump(exclude_unset=True)
    if "args" in data:
        data["args"] = _args_to_json(data["args"])
    if "env" in data:
        data["env"] = _dict_to_json(
            _merge_masked_dict(_dict_from_json(server.env), data["env"])
        )
    if "headers" in data:
        data["headers"] = _dict_to_json(
            _merge_masked_dict(_dict_from_json(server.headers), data["headers"])
        )
    # transport 相关字段部分更新：按合并后的完整值重新校验
    transport = data.get("transport", server.transport)
    command = data.get("command", server.command)
    url = data.get("url", server.url)
    args_list = _args_from_json(data.get("args", server.args))
    _validate_mcp_fields(transport, command, args_list, url)
    config_changed = any(
        key in data for key in ("transport", "command", "args", "env", "url", "headers", "timeout_sec")
    )
    for field, value in data.items():
        setattr(server, field, value)
    if config_changed:
        # 配置变更后旧状态失效，下次测试/调用重新探测
        server.last_status = "unknown"
        server.last_error = None
        invalidate_cache(server_id)
    db.commit()
    db.refresh(server)
    return _to_response(server)


def delete_server(db: Session, server_id: int) -> bool:
    server = db.get(MCPServer, server_id)
    if server is None:
        return False
    db.delete(server)
    db.commit()
    invalidate_cache(server_id)
    return True


def enable_server(db: Session, server_id: int, *, enabled: bool) -> MCPServerResponse | None:
    server = db.get(MCPServer, server_id)
    if server is None:
        return None
    server.enabled = enabled
    invalidate_cache(server_id)
    db.commit()
    db.refresh(server)
    return _to_response(server)


# endregion


# region ---- 对外：连接测试 / 工具清单 / 调用 ----

def _to_tool_info(server: MCPServer, tool: dict[str, Any]) -> MCPToolInfo:
    return MCPToolInfo(
        name=_truncate_tool_name(server.id, tool["name"]),
        original_name=tool["name"],
        server_id=server.id,
        server_name=server.name,
        description=tool.get("description", ""),
        input_schema=tool.get("input_schema") or {},
        read_only=bool(tool.get("read_only")),
    )


def test_connection(db: Session, server_id: int) -> MCPTestResult | None:
    server = db.get(MCPServer, server_id)
    if server is None:
        return None
    try:
        tools = _run_async(_do_list_tools(server), wall_timeout=server.timeout_sec + INIT_TIMEOUT_SEC + 5)
        server.last_status = "ok"
        server.last_error = None
        _cache_put(server_id, tools, None)
        db.commit()
        return MCPTestResult(
            ok=True,
            message=f"连接成功，发现 {len(tools)} 个工具",
            tools=[_to_tool_info(server, t) for t in tools],
        )
    except Exception as exc:  # TimeoutError / 子进程错误 / SDK 异常（不吞 KeyboardInterrupt/SystemExit/CancelledError）
        message = _safe_error(server, exc)
        server.last_status = "error"
        server.last_error = message
        _cache_put(server_id, [], message)
        db.commit()
        return MCPTestResult(ok=False, message=message, tools=[])


def server_tools(db: Session, server_id: int, *, use_cache: bool = True) -> MCPTestResult | None:
    """拉取单服务器工具清单（走缓存），返回与 test_connection 同构结果但不写 last_status。"""
    server = db.get(MCPServer, server_id)
    if server is None:
        return None
    cached = _cache_get(server_id) if use_cache else None
    if cached is not None:
        tools, error = cached
        if error:
            return MCPTestResult(ok=False, message=error, tools=[])
        return MCPTestResult(
            ok=True,
            message=f"发现 {len(tools or [])} 个工具（缓存）",
            tools=[_to_tool_info(server, t) for t in (tools or [])],
        )
    try:
        tools = _run_async(_do_list_tools(server), wall_timeout=server.timeout_sec + INIT_TIMEOUT_SEC + 5)
        _cache_put(server_id, tools, None)
        return MCPTestResult(
            ok=True,
            message=f"发现 {len(tools)} 个工具",
            tools=[_to_tool_info(server, t) for t in tools],
        )
    except Exception as exc:
        message = _safe_error(server, exc)
        _cache_put(server_id, [], message)
        return MCPTestResult(ok=False, message=message, tools=[])


def call_tool(db: Session, server_id: int, tool_name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    """同步调用入口（供 execute_tool / 危险动作执行复用）。"""
    server = db.get(MCPServer, server_id)
    if server is None:
        return {"ok": False, "error": "MCP 服务器不存在"}
    call_timeout = min(max(server.timeout_sec, 5), CALL_TIMEOUT_CAP)
    try:
        text = _run_async(
            _do_call_tool(server, tool_name, arguments or {}),
            wall_timeout=call_timeout + INIT_TIMEOUT_SEC + 10,
        )
        return {"ok": True, "text": text}
    except Exception as exc:
        return {"ok": False, "error": _safe_error(server, exc)}


# endregion


# region ---- 对外：Agent 集成（prompt 注入 + 路由判定） ----

def list_enabled_tools_for_agent(db: Session) -> list[dict[str, Any]]:
    """收集所有启用服务器的工具（走缓存，单服务器失败不阻塞）。

    返回 [{server_id, server_name, auto_approve_readonly, tool: {name,description,input_schema,read_only}}]。
    """
    servers = (
        db.execute(select(MCPServer).where(MCPServer.enabled.is_(True)))
        .scalars()
        .all()
    )
    entries: list[dict[str, Any]] = []
    for server in servers:
        result = server_tools(db, server.id, use_cache=True)
        if result is None or not result.ok:
            # 单服务器失败不阻塞对话，仅记录（last_status 已在测试时回写）
            continue
        for tool_info in result.tools:
            entries.append(
                {
                    "server_id": server.id,
                    "server_name": server.name,
                    "auto_approve_readonly": server.auto_approve_readonly,
                    "read_only": tool_info.read_only,
                    "name": tool_info.original_name,
                    "namespaced": tool_info.name,
                    "description": tool_info.description,
                    "input_schema": tool_info.input_schema,
                }
            )
    return entries


def is_auto_approved(db: Session, server_id: int, called_name: str) -> bool:
    """判定某 MCP 工具是否可免确认直接执行。

    called_name 为模型回传的命名空间名（可能被 _truncate_tool_name 截断），按 namespaced
    形态匹配工具清单，避免截断后原名失配。服务器未启用时一律不免确认。
    """
    server = db.get(MCPServer, server_id)
    if server is None or not server.enabled or not server.auto_approve_readonly:
        return False
    result = server_tools(db, server_id, use_cache=True)
    if result is None or not result.ok:
        return False
    return any(t.name == called_name and t.read_only for t in result.tools)


def resolve_tool_name(db: Session, server_id: int, called_name: str) -> str | None:
    """把模型回传的（可能截断的）命名空间工具名还原为服务器原始工具名。

    工具清单里 MCPToolInfo.name 已是 namespaced（可能截断）形态，与之匹配即可拿到
    original_name。缓存未命中或工具不存在时返回 None。
    """
    result = server_tools(db, server_id, use_cache=True)
    if result is None or not result.ok:
        return None
    for t in result.tools:
        if t.name == called_name:
            return t.original_name
    return None


# endregion
