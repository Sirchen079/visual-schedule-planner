"""MCP 客户端适配器，使用 MCPToolset 管理 stdio 与 HTTP 连接。

工具列表和调用由 SDK 管理连接生命周期；错误文本脱敏并限制长度。"""
from __future__ import annotations

import json
from time import monotonic

from zhishi.domain.models import MCPServer

RESULT_MAX_CHARS = 4000
ERROR_MAX_CHARS = 300
TOOLS_CACHE_TTL_SECONDS = 60

# 工具清单缓存 {server_id: (expires_at, tools)}：runtime 每次 run 装配与
# GET /ai/mcp/servers/{sid}/tools 都会真实连接，慢服务器拖启动。
_tools_cache: dict[int, tuple[float, list[dict]]] = {}

# 缓存世代号：list_tools 在 miss 后要 await 网络，若等待期间
# 发生 invalidate（PUT/DELETE 失效钩子），旧结果无条件写回会把已删除/已改配的
# 服务器工具（含 readOnlyHint，参与免审分类）污染回缓存 60s。进入时捕获世代，
# 网络返回后世代未变才写回；变了则丢弃，下次查询真连。
_cache_generation: int = 0


def invalidate(server_id: int) -> None:
    """清除某服务器的工具清单缓存并递增世代（路由层在行更新/enable 切换/DELETE 时调用）。
    世代递增使「invalidate 前已进入 list_tools 的在途查询」返回后不再回填旧结果。"""
    global _cache_generation
    _tools_cache.pop(server_id, None)
    _cache_generation += 1


class MCPClientError(RuntimeError):
    """MCP 连接/调用失败（文本已脱敏截断，可直接展示/落库）。"""


def build_client(server_row: MCPServer) -> tuple[object, dict]:
    """按 server 行构造 MCPToolset 的 client 入参与附加 kwargs。
    返回 (client, kwargs)：stdio → (StdioTransport, {})；http → (url, {"headers": ...})。
    测试可 monkeypatch 本函数注入 in-process 服务器（MCPToolset 直接接受实例）。"""
    from fastmcp.client.transports import StdioTransport
    if server_row.transport == "stdio":
        env = _load_json(server_row.env_json, {})
        transport = StdioTransport(
            command=server_row.command,
            args=_load_json(server_row.args_json, []),
            env=env or None)
        return transport, {}
    if server_row.transport == "http":
        headers = _load_json(server_row.headers_json, {})
        return server_row.url, ({"headers": headers} if headers else {})
    raise MCPClientError(f"未知 MCP 传输类型：{server_row.transport}")


def build_toolset(server_row: MCPServer, timeout: float | None = None):
    """构造裸 MCPToolset（无权限门；管理端点 list/call 用）。"""
    from pydantic_ai.mcp import MCPToolset
    client, kwargs = build_client(server_row)
    t = float(timeout if timeout is not None else (server_row.timeout_sec or 30))
    return MCPToolset(client, init_timeout=t, read_timeout=t, **kwargs)


def secrets_of(server_row: MCPServer) -> list[str]:
    """env/headers 的值（≥4 字符者视为敏感，参与错误脱敏）。"""
    vals = list(_load_json(server_row.env_json, {}).values())
    vals += list(_load_json(server_row.headers_json, {}).values())
    return [str(v) for v in vals if v and len(str(v)) >= 4]


def tool_to_record(t) -> dict:
    """mcp Tool 对象 → 缓存记录（与 list_tools 返回项同构，/tools 端点可直接序列化）。"""
    ann = getattr(t, "annotations", None)
    schema = getattr(t, "input_schema", None)
    return {"name": t.name, "description": t.description or "",
            "input_schema": schema if isinstance(schema, dict) else {},
            "read_only": bool(ann is not None and ann.read_only_hint)}


def tool_from_record(rec: dict):
    """缓存记录 → mcp Tool 对象（runtime GatedToolset 命中缓存时还原装配所需字段：
    name/description/input_schema/annotations.read_only_hint；meta/execution 置空，
    与「本实现不消费 server instructions/task 路径」的现状一致）。"""
    import mcp.types as mcp_types
    return mcp_types.Tool(
        name=rec["name"],
        description=rec["description"] or None,
        input_schema=rec.get("input_schema") or {"type": "object", "properties": {}},
        annotations=mcp_types.ToolAnnotations(read_only_hint=True) if rec.get("read_only") else None)


def sanitize(text: str, server_row: MCPServer) -> str:
    for secret in secrets_of(server_row):
        text = text.replace(secret, "***")
    return text[:ERROR_MAX_CHARS]


async def list_tools(server_row: MCPServer, timeout: float | None = None, *,
                     use_cache: bool = True) -> list[dict]:
    """连接服务器并列出工具：[{name, description, input_schema, read_only}]。
    60s TTL 模块级缓存（按 server_id）：命中且未过期直接返回。
    use_cache=False（/test 连通性测试）强制真连——不读也不写缓存。
    写回前校验缓存世代：网络等待期间发生过 invalidate 则丢弃
    本次结果，防止旧服务器工具（含 readOnlyHint）回填污染。"""
    global _cache_generation
    key = server_row.id
    gen = _cache_generation                          # 进入时捕获
    if use_cache and key is not None:
        hit = _tools_cache.get(key)
        if hit is not None and monotonic() < hit[0]:
            return list(hit[1])
    toolset = build_toolset(server_row, timeout)
    try:
        tools = await toolset.list_tools()
    except Exception as exc:
        raise MCPClientError(sanitize(str(exc), server_row)) from exc
    out = [tool_to_record(t) for t in tools]
    if use_cache and key is not None and gen == _cache_generation:
        _tools_cache[key] = (monotonic() + TOOLS_CACHE_TTL_SECONDS, out)
    return out


async def call_tool(server_row: MCPServer, tool_name: str, args: dict,
                    timeout: float | None = None) -> str:
    """调用远端工具并把 content 展平为文本（截 4000 字符）。"""
    toolset = build_toolset(server_row, timeout)
    try:
        result = await toolset.direct_call_tool(tool_name, args)
    except Exception as exc:
        raise MCPClientError(sanitize(str(exc), server_row)) from exc
    return _flatten(result)[:RESULT_MAX_CHARS]


def _load_json(raw: str | None, default):
    try:
        parsed = json.loads(raw or "")
        return parsed if parsed else default
    except ValueError:
        return default


def _flatten(result) -> str:
    """MCP 返回值（str/dict/list/BinaryContent…）→ 模型可读文本。"""
    if isinstance(result, str):
        return result
    if isinstance(result, bytes):
        return f"[二进制内容 {len(result)} 字节]"
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(result)
