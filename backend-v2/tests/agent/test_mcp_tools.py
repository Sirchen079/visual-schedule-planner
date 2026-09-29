import json
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults, ToolApproved
from sqlalchemy import select

from zhishi.adapters import mcp_client
from zhishi.agent.runtime import AgentDeps, AgentRuntime
from zhishi.agent.tool_discovery import CORE_TOOLS
from zhishi.agent.tools.mcp_tools import configure_mcp_server
from zhishi.agent.tools.registry import specs_for
from zhishi.domain import settingsvc
from zhishi.domain.models import AIConversation, MCPServer

FAKE_TOOLS = [{'name': 'echo', 'description': '回显文本', 'input_schema': {}, 'read_only': True}]


def _patch_tools(monkeypatch, tools=None, error=None, calls=None):
    async def fake(row, timeout=None, use_cache=True):
        if calls is not None:
            calls.append(row.id)
        if error is not None:
            raise error
        return tools if tools is not None else FAKE_TOOLS
    monkeypatch.setattr(mcp_client, 'list_tools', fake)


async def test_http_create_tests_and_reports_tools(db, monkeypatch):
    _patch_tools(monkeypatch)
    result = json.loads(await configure_mcp_server(
        db, name='示例服务', url='https://mcp.example.com/sse',
        headers_json='{"Authorization": "Bearer sk-secret"}'))
    assert result['ok'] and result['tested'] and result['tool_count'] == 1
    assert result['tools'][0]['name'] == 'echo'
    row = db.get(MCPServer, result['id'])
    assert row.transport == 'http' and row.enabled and not row.trusted
    assert row.last_status == 'ok'
    assert 'sk-secret' not in json.dumps(result)   # 密钥不回显


async def test_connection_failure_keeps_row_for_manual_fix(db, monkeypatch):
    _patch_tools(monkeypatch, error=mcp_client.MCPClientError('连接超时'))
    result = json.loads(await configure_mcp_server(db, name='坏地址', url='http://127.0.0.1:9/sse'))
    assert result['ok'] and result['tool_count'] == 0 and '连接超时' in result['error']
    assert db.get(MCPServer, result['id']).last_status == 'error'


async def test_stdio_saved_untrusted_without_connecting(db, monkeypatch):
    calls = []
    _patch_tools(monkeypatch, calls=calls)
    result = json.loads(await configure_mcp_server(
        db, name='本地服务', transport='stdio', command='uvx', args_json='["mcp-server-fetch"]'))
    assert result['ok'] and result['tested'] is False and calls == []
    row = db.get(MCPServer, result['id'])
    assert row.enabled and not row.trusted and row.command == 'uvx'
    assert '信任' in result['note']


async def test_validation_and_name_conflict(db):
    for kwargs in ({'transport': 'ftp'}, {'url': None}, {'url': 'ftp://x'},
                   {'transport': 'stdio'}, {'args_json': '["a", 1]'},
                   {'url': 'https://x/sse', 'headers_json': '{"k": 1}'}):
        with pytest.raises(ValueError):
            await configure_mcp_server(db, name='校验', **kwargs)
    await configure_mcp_server(db, name='校验', transport='stdio', command='run')
    with pytest.raises(ValueError, match='同名'):
        await configure_mcp_server(db, name='校验', transport='stdio', command='run')
    assert db.query(MCPServer).count() == 1


async def test_replay_returns_receipt_without_retesting(db, monkeypatch):
    calls = []
    _patch_tools(monkeypatch, calls=calls)
    conversation = AIConversation(title='配置 MCP')
    db.add(conversation)
    db.commit()
    ctx = SimpleNamespace(deps=SimpleNamespace(conversation_id=conversation.id, run_id='mcp-run'))
    first = json.loads(await configure_mcp_server(db, name='重放', url='https://x/sse', ctx=ctx))
    second = json.loads(await configure_mcp_server(db, name='重放', url='https://x/sse', ctx=ctx))
    assert second.get('replayed') is True and len(calls) == 1 and second['id'] == first['id']


@pytest.mark.parametrize('mode', ['careful', 'plan', 'brainstorm'])
async def test_configure_writes_obey_mode_gates(db, mode):
    if mode == 'careful':
        settingsvc.set_setting(db, 'agent_autonomy', 'careful')
    calls = []

    def model(messages, info):
        calls.append(1)
        if len(calls) == 1:
            return ModelResponse(parts=[ToolCallPart('execute_tool', {'name': 'configure_mcp_server',
                'arguments': {'name': '门控', 'url': 'https://x/sse'}}, 'save')])
        return ModelResponse(parts=[TextPart('不能写入')])

    result = await AgentRuntime(FunctionModel(model), db)._build_agent(
        plan_mode=mode == 'plan', brainstorm_mode=mode == 'brainstorm').run(
            '配置 MCP', deps=AgentDeps(db=db, emit=None))
    assert db.query(MCPServer).count() == 0
    if mode == 'careful':
        assert isinstance(result.output, DeferredToolRequests)


def test_budget_red_line_not_in_core_tools(db):
    names = {s.name for s in specs_for(db)}
    assert 'configure_mcp_server' in names
    assert not {'configure_mcp_server'} & CORE_TOOLS


async def test_real_dispatch_configures_via_execute_tool(db, monkeypatch):
    _patch_tools(monkeypatch)
    steps = []

    def model(messages, info):
        results = [p for m in messages for p in m.parts
                   if p.__class__.__name__ == 'ToolReturnPart']
        steps.append(len(results))
        if not results:
            return ModelResponse(parts=[ToolCallPart('search_tools', {'names': ['configure_mcp_server']}, 'find')])
        payload = json.loads(results[-1].content)
        if len(results) == 1:
            assert 'configure_mcp_server' in payload['loaded_tools']
            return ModelResponse(parts=[ToolCallPart('execute_tool', {'name': 'configure_mcp_server',
                'arguments': {'name': '检索服务', 'url': 'https://mcp.example.com/mcp'}}, 'save')])
        assert payload['ok'] and payload['tools'][0]['name'] == 'echo'
        return ModelResponse(parts=[TextPart('已配置并试连')])

    agent = AgentRuntime(FunctionModel(model), db)._build_agent()
    first = await agent.run('配置这个 MCP 服务器：https://mcp.example.com/mcp',
                            deps=AgentDeps(db=db, emit=None))
    assert isinstance(first.output, DeferredToolRequests)   # confirm 门：先落审批卡
    assert db.query(MCPServer).count() == 0
    resumed = AgentRuntime(FunctionModel(model), db)._build_agent()
    result = await resumed.run(message_history=first.all_messages(),
        deferred_tool_results=DeferredToolResults(approvals={'save': ToolApproved()}),
        deps=AgentDeps(db=db, emit=None))
    assert result.output == '已配置并试连'
    assert db.query(MCPServer).count() == 1
    assert db.query(MCPServer).first().last_status == 'ok'
