"""Agent-side MCP server configuration behind the existing confirm gate."""
from __future__ import annotations

import json
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from zhishi.agent.mutations import execute_mutation
from zhishi.agent.tools.registry import ToolSpec, register
from zhishi.domain.models import MCPServer


def _load_json_object(value: str, label: str) -> dict[str, str]:
    try:
        parsed = json.loads(value or '{}')
    except json.JSONDecodeError as exc:
        raise ValueError(f'{label} 必须是合法的 JSON 对象。') from exc
    if not isinstance(parsed, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                               for k, v in parsed.items()):
        raise ValueError(f'{label} 必须是字符串到字符串的 JSON 对象（如 {{"Authorization": "Bearer ..."}}）。')
    return parsed


def _load_args(value: str) -> list[str]:
    try:
        parsed = json.loads(value or '[]')
    except json.JSONDecodeError as exc:
        raise ValueError('args_json 必须是合法的 JSON 字符串数组。') from exc
    if not isinstance(parsed, list) or not all(isinstance(v, str) for v in parsed):
        raise ValueError('args_json 必须是字符串数组。')
    return parsed


async def configure_mcp_server(db: Session, name: str, transport: str = 'http',
                               url: str | None = None, command: str = '',
                               args_json: str = '[]', env_json: str = '{}',
                               headers_json: str = '{}', timeout_sec: int = 30,
                               ctx=None, request_key: str | None = None) -> str:
    """保存用户提供的 MCP 服务器并试连。http 传 url，鉴权放 headers_json；
    stdio 传 command/args_json/env_json。http 保存后立即连接并列出工具回报清单；
    stdio 需用户在设置中勾选信任后才会连接。密钥只放 env/headers，不会回显。"""
    name = name.strip()
    if not name or len(name) > 100:
        raise ValueError('名称必填，最多 100 字。')
    if transport not in ('http', 'stdio'):
        raise ValueError('transport 只能是 http 或 stdio。')
    if not isinstance(timeout_sec, int) or not 5 <= timeout_sec <= 120:
        raise ValueError('timeout_sec 取 5 至 120 的整数秒。')
    for label, value in (('args_json', args_json or ''), ('env_json', env_json or ''),
                         ('headers_json', headers_json or '')):
        if len(value) > 20000:
            raise ValueError(f'{label} 过大，上限 2 万字符。')
    args = _load_args(args_json)
    env = _load_json_object(env_json, 'env_json')
    headers = _load_json_object(headers_json, 'headers_json')
    command = command.strip()
    if transport == 'http':
        if not url or len(url) > 500:
            raise ValueError('http 服务器需提供 url（最多 500 字符）。')
        parts = urlsplit(url.strip())
        if parts.scheme not in ('http', 'https') or not parts.hostname:
            raise ValueError('url 必须是 http/https 地址。')
    elif not command:
        raise ValueError('stdio 服务器需提供可执行命令 command。')

    def action():
        # Serialize SQLite writers before the uniqueness read (skills.write pattern).
        db.connection().exec_driver_sql('UPDATE mcp_servers SET id = id WHERE 0')
        existing = db.scalar(select(MCPServer).where(MCPServer.name == name))
        if existing is not None:
            raise ValueError(f'已有同名 MCP 服务器 #{existing.id}「{existing.name}」；'
                             '请换名称，或请用户在设置 → 网络服务中修改。')
        row = MCPServer(name=name, transport=transport, command=command,
                        args_json=json.dumps(args, ensure_ascii=False),
                        env_json=json.dumps(env, ensure_ascii=False),
                        headers_json=json.dumps(headers, ensure_ascii=False),
                        url=(url.strip() if transport == 'http' else None),
                        timeout_sec=timeout_sec, enabled=True, trusted=False)
        db.add(row)
        db.flush()
        return {'ok': True, 'id': row.id, 'name': row.name, 'transport': row.transport,
                'enabled': row.enabled, 'trusted': row.trusted}

    result = json.loads(execute_mutation(db, tool='configure_mcp_server',
                            arguments={'name': name, 'transport': transport, 'url': url,
                                       'command': command, 'args_json': args_json,
                                       'env_json': env_json, 'headers_json': headers_json,
                                       'timeout_sec': timeout_sec},
                            action=action, ctx=ctx, request_key=request_key))
    if result.get('replayed'):
        return json.dumps(result, ensure_ascii=False)
    row = db.get(MCPServer, result['id'], populate_existing=True)
    if row.transport == 'stdio':
        result.update(tested=False, tool_count=0,
                      note='stdio 服务器已保存（启用、未信任）：请用户在设置 → 网络服务勾选信任后连接，'
                           '信任前的对话不会拉起该进程。')
        return json.dumps(result, ensure_ascii=False)
    from zhishi.adapters import mcp_client
    try:   # 与 POST /ai/mcp/servers/{sid}/test 同语义：真连、回写 last_status
        tools = await mcp_client.list_tools(row, use_cache=False)
        row.last_status, row.last_error = 'ok', None
        db.commit()
        result.update(tested=True, tool_count=len(tools),
                      tools=[{'name': t['name'], 'description': t['description'][:200]} for t in tools[:20]],
                      note='已连接；工具（mcp__ 前缀）经 search_tools 查询、后续对话回合可调用，调用仍走授权。')
    except Exception as exc:  # noqa: BLE001 -- 配置保留，回报脱敏错误供修正
        row.last_status, row.last_error = 'error', str(exc)[:300]
        db.commit()
        result.update(tested=True, tool_count=0, error=str(exc)[:300],
                      note='已保存但连接失败：请核对地址与网络，或让用户在设置 → 网络服务中编辑/删除。')
    return json.dumps(result, ensure_ascii=False)


register(ToolSpec('configure_mcp_server', configure_mcp_server.__doc__ or '',
                  'confirm', None, configure_mcp_server))
