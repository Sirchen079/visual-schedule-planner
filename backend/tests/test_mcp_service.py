"""MCP 服务器服务与路由测试。

覆盖：CRUD 与脱敏、入参校验、真实 stdio echo 服务器端到端联测。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.models import MCPServer
from app.schemas import MCPServerCreate, MCPServerUpdate
from app.services import mcp_service

# 用当前解释器拉起 MCP 服务器子进程（测试环境即 venv 内的 python）
_PYTHON = sys.executable

_ECHO_SERVER = '''
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("echo-test")


@mcp.tool()
def echo(text: str) -> str:
    """原样回显输入文本。"""
    return text


if __name__ == "__main__":
    mcp.run()
'''


def _stdio_payload(name: str, command: str = _PYTHON, args: list[str] | None = None, **extra):
    base = {
        "name": name,
        "transport": "stdio",
        "command": command,
        "args": args or [],
        "env": {},
        "headers": {},
    }
    base.update(extra)
    return base


# ---- CRUD + 脱敏 ----

def test_crud_and_masking(db_session):
    created = mcp_service.create_server(
        db_session,
        MCPServerCreate(
            **_stdio_payload(
                "fs",
                args=["-y", "@modelcontextprotocol/server-filesystem", "D:/docs"],
                env={"API_TOKEN": "sk-abcdef1234567890"},
            )
        ),
    )
    assert created.id is not None
    # 响应里 env 值必须脱敏（不得出现明文）
    assert created.env["API_TOKEN"] != "sk-abcdef1234567890"
    assert "abcdef" not in created.env["API_TOKEN"]

    assert any(s.id == created.id for s in mcp_service.list_servers(db_session))
    got = mcp_service.get_server(db_session, created.id)
    assert got is not None and got.name == "fs"

    # 留空=不变：回传脱敏占位时保留原值；timeout 正常更新
    updated = mcp_service.update_server(
        db_session,
        created.id,
        MCPServerUpdate(env={"API_TOKEN": created.env["API_TOKEN"]}, timeout_sec=45),
    )
    assert updated is not None and updated.timeout_sec == 45
    # 库内仍为明文（脱敏仅出现在响应层）
    row = db_session.get(MCPServer, created.id)
    assert row is not None and "sk-abcdef1234567890" in row.env

    assert mcp_service.delete_server(db_session, created.id) is True
    assert mcp_service.get_server(db_session, created.id) is None


def test_enable_toggle(db_session):
    created = mcp_service.create_server(db_session, MCPServerCreate(**_stdio_payload("toggle")))
    assert created.enabled is True
    assert mcp_service.enable_server(db_session, created.id, enabled=False).enabled is False
    assert mcp_service.enable_server(db_session, created.id, enabled=True).enabled is True


# ---- 入参校验（经 HTTP 层验证 422） ----

def test_validation_missing_command(client):
    resp = client.post("/mcp/servers", json={"name": "x", "transport": "stdio", "command": ""})
    assert resp.status_code == 422


def test_validation_bad_url(client):
    resp = client.post(
        "/mcp/servers",
        json={"name": "x", "transport": "http", "url": "ftp://example.com"},
    )
    assert resp.status_code == 422


def test_validation_timeout_out_of_range(client):
    resp = client.post(
        "/mcp/servers",
        json={"name": "x", "transport": "stdio", "command": "npx", "timeout_sec": 200},
    )
    assert resp.status_code == 422


# ---- 真实 stdio echo 服务器端到端 ----

@pytest.fixture()
def echo_server(db_session, tmp_path: Path):
    script = tmp_path / "echo_server.py"
    script.write_text(_ECHO_SERVER, encoding="utf-8")
    created = mcp_service.create_server(
        db_session,
        MCPServerCreate(**_stdio_payload("echo", args=[str(script)])),
    )
    yield created
    mcp_service.invalidate_cache(created.id)
    mcp_service.delete_server(db_session, created.id)


def test_connection_and_tools(echo_server, db_session):
    result = mcp_service.test_connection(db_session, echo_server.id)
    assert result is not None and result.ok
    assert "echo" in [t.original_name for t in result.tools]


def test_call_tool_echo(echo_server, db_session):
    outcome = mcp_service.call_tool(db_session, echo_server.id, "echo", {"text": "hello-mcp"})
    assert outcome["ok"] is True
    assert outcome["text"] == "hello-mcp"


# ---- Agent 集成：直接执行闸门 + 危险动作两段确认 ----

def test_mcp_direct_execute_guard_requires_confirmation(echo_server, db_session):
    """未开「只读免确认」的 MCP 工具放进 tools[] 时，直接执行被拒并引导走确认。"""
    from app.services import ai_tool_service

    namespaced = mcp_service.namespaced_name(echo_server.id, "echo")
    result = ai_tool_service.execute_tool(db_session, namespaced, {"text": "hi"})
    assert result["ok"] is False
    assert "mcp_tool_call" in result["error"]


# ---- P4：原生模式 MCP 暴露 ----

def test_assemble_native_tools_includes_mcp_with_schema(db_session, monkeypatch):
    """原生装配：内置工具 + MCP 工具（namespaced），schema 原样透传。"""
    from app.routers.ai import _assemble_native_tools

    monkeypatch.setattr(
        mcp_service, "list_enabled_tools_for_agent",
        lambda db: [{
            "server_id": 1, "server_name": "S", "auto_approve_readonly": True,
            "read_only": True, "name": "echo", "namespaced": "mcp__s1__echo",
            "description": "回声工具",
            "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}},
        }],
    )
    tools = _assemble_native_tools(db_session)
    names = [t["name"] for t in tools]
    assert "create_task" in names  # 内置工具
    assert "mcp__s1__echo" in names  # MCP 工具
    mcp_tool = next(t for t in tools if t["name"] == "mcp__s1__echo")
    assert mcp_tool["description"] == "回声工具"
    assert mcp_tool["input_schema"] == {"type": "object", "properties": {"text": {"type": "string"}}}


def test_mcp_action_preview_and_confirm_flow(echo_server, db_session):
    """模拟模型返回 mcp_tool_call 危险动作：预览可见、两段确认后回填 echo 结果。"""
    from app.services import ai_action_service

    payload = {
        "server_id": echo_server.id,
        "tool_name": "echo",
        "arguments": {"text": "from-action"},
    }
    preview = ai_action_service.build_action_preview(db_session, "mcp_tool_call", payload)
    assert any("MCP 工具" in line for line in preview)
    assert any("echo" in line for line in preview)

    action = ai_action_service.create_pending_action(
        db_session, None, "mcp_tool_call", payload, "调用 echo 工具"
    )
    _action, token, err = ai_action_service.confirm_action(db_session, action.id)
    assert err is None and token
    ok, message = ai_action_service.execute_action(db_session, action.id, token)
    assert ok is True
    assert message == "from-action"

