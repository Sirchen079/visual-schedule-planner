"""Inspect SDK HTTP bodies across durable runs; no provider or personal data access."""
import base64
import json
from datetime import datetime, timedelta, timezone
from itertools import pairwise

import httpx2 as httpx
import pytest
from pydantic_ai.messages import (
    BinaryContent,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from zhishi.agent.providers import build_model
from zhishi.agent.runtime import AgentDeps, AgentRuntime
from zhishi.domain.models import AIConfig, AIContextArtifact, AIConversation, AIMessage, MCPServer

MODES = [('openai_compat', 'auto'), ('openai_responses', 'auto'),
         ('anthropic', 'auto'), ('openai_compat', 'anthropic_compat')]


def reply(protocol, index, call=None):
    if protocol == 'anthropic':
        content = ([{'type': 'tool_use', 'id': f'call{index}', 'name': call[0], 'input': call[1]}]
                   if call else [{'type': 'text', 'text': 'Done'}])
        return {'id': f'msg{index}', 'type': 'message', 'role': 'assistant', 'model': 'test',
                'content': content, 'stop_reason': 'tool_use' if call else 'end_turn',
                'stop_sequence': None, 'usage': {'input_tokens': 10, 'output_tokens': 1}}
    if protocol == 'openai_responses':
        output = ([{'type': 'function_call', 'id': f'fc{index}', 'call_id': f'call{index}',
                    'name': call[0], 'arguments': json.dumps(call[1]), 'status': 'completed'}]
                  if call else [{'type': 'message', 'id': f'm{index}', 'status': 'completed',
                                 'role': 'assistant', 'content': [
                                     {'type': 'output_text', 'text': 'Done', 'annotations': []}]}])
        return {'id': f'resp{index}', 'object': 'response', 'created_at': 1, 'model': 'test',
                'status': 'completed', 'output': output,
                'usage': {'input_tokens': 10, 'output_tokens': 1, 'total_tokens': 11}}
    message = {'role': 'assistant', 'content': None if call else 'Done'}
    if call:
        message['tool_calls'] = [{'id': f'call{index}', 'type': 'function',
                                 'function': {'name': call[0], 'arguments': json.dumps(call[1])}}]
    return {'id': f'chat{index}', 'object': 'chat.completion', 'created': 1, 'model': 'test',
            'choices': [{'index': 0, 'message': message, 'finish_reason': 'tool_calls' if call else 'stop'}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 1, 'total_tokens': 11}}


def without_hints(value):
    if isinstance(value, list):
        return [without_hints(item) for item in value]
    if isinstance(value, dict):
        return {key: without_hints(item) for key, item in value.items() if key != 'cache_control'}
    return value


def assert_prefix(before, after, protocol):
    key = 'input' if protocol == 'openai_responses' else 'messages'
    old, new = without_hints(before[key]), without_hints(after[key])
    assert before['tools'] == after['tools']
    if protocol == 'anthropic':
        assert before['system'] == after['system']
        assert new[:len(old) - 1] == old[:-1]
        assert new[len(old) - 1]['content'][:len(old[-1]['content'])] == old[-1]['content']
    else:
        assert new[:len(old)] == old
        if protocol == 'openai_responses':
            assert before['instructions'] == after['instructions']
    if cache_blocks(before.get('messages', [])):
        previous = cache_blocks(before['messages'])[-1]
        retained = cache_blocks(after['messages'])[-2]
        assert without_hints(previous) == without_hints(retained)


def cache_blocks(value):
    if isinstance(value, list):
        return [block for item in value for block in cache_blocks(item)]
    if isinstance(value, dict):
        return ([value] if 'cache_control' in value else []) + [
            block for item in value.values() for block in cache_blocks(item)]
    return []


@pytest.mark.parametrize(('protocol', 'mode'), MODES)
@pytest.mark.parametrize('large_result', [False, True])
async def test_mcp_prefix_survives_fresh_agents_sqlite_and_compaction(
        db, monkeypatch, protocol, mode, large_result):
    from mcp.server.mcpserver import MCPServer as InProcessServer
    from mcp.types import ToolAnnotations
    from pydantic_ai.providers import anthropic, openai

    from zhishi.adapters import mcp_client
    from zhishi.agent import compaction
    from zhishi.infra import local_clock

    server = InProcessServer(name='cache-test')
    executions = []

    def read_cache_sample() -> dict:
        executions.append(1)
        return {'z': ['保留数组顺序', 3, 1], 'nested': {'second': True, 'first': None}, 'a': 2,
                'data': '资料甲乙丙丁' * 3000 + 'TAIL_SENTINEL' if large_result else 'short'}

    server.add_tool(read_cache_sample, name='read_cache_sample', description='Read a deterministic test result',
                    annotations=ToolAnnotations(read_only_hint=True))
    row = MCPServer(name='mock', transport='http', url='http://localhost:9/mcp', enabled=True,
                    auto_approve_readonly=True)
    conv = AIConversation(title='cache replay test')
    db.add_all([row, conv])
    db.commit()
    name = f'mcp__{row.id}__read_cache_sample'
    monkeypatch.setattr(mcp_client, 'build_client', lambda _: (server, {}))
    now = datetime(2026, 12, 31, 23, 59, tzinfo=timezone(timedelta(hours=8)))
    monkeypatch.setattr(local_clock, 'local_now', lambda: now)
    captured = []
    summaries = []

    def summarize(config, system, user, timeout):
        summaries.append(user)
        return 'The earlier sample reads completed; preserve subsequent results and user requests.'

    monkeypatch.setattr(compaction, '_oneshot_with_timeout', summarize)

    def respond(request):
        index = len(captured)
        captured.append(json.loads(request.content))
        calls = [('search_tools', {'names': [name]}),
                 ('execute_tool', {'name': name, 'arguments': {}}), None]
        return httpx.Response(200, json=reply(protocol, index, calls[index % 3]))

    module, provider = (anthropic, 'AnthropicProvider') if protocol == 'anthropic' else (openai, 'OpenAIProvider')
    original = getattr(module, provider)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(module, provider, lambda **kw: original(**kw, http_client=client))
        cfg = AIConfig(id=42, name='test', model='test', provider_kind=protocol,
                       base_url='https://test.example/v1', prompt_cache_mode=mode, prompt_cache_key=True)
        history = []
        for turn in range(6):
            if turn == 4:
                original_history = ModelMessagesTypeAdapter.dump_json(history)
                compacted, summary, fingerprint = compaction.summarize_history(
                    db, cfg, history, threshold=2, timeout=1)
                assert summary and fingerprint and summaries
                assert len(compacted) < len(history)
                assert ModelMessagesTypeAdapter.dump_json(history) == original_history
                history = ModelMessagesTypeAdapter.validate_json(ModelMessagesTypeAdapter.dump_json(compacted))
                calls = {p.tool_call_id for m in history for p in m.parts if isinstance(p, ToolCallPart)}
                returns = {p.tool_call_id for m in history for p in m.parts if isinstance(p, ToolReturnPart)}
                assert calls == returns and 'call10' in calls and 'call1' not in calls
            agent = AgentRuntime(build_model(cfg, api_key='mock-only'), db, model_config=cfg)._build_agent(
                conversation_id=conv.id)
            result = await agent.run(f'Read sample {turn}', message_history=history,
                                     deps=AgentDeps(db=db, emit=None, conversation_id=conv.id))
            assert result.output == 'Done' and result.usage.tool_calls == 2
            saved = AIMessage(conversation_id=conv.id, role='assistant',
                              history_json=ModelMessagesTypeAdapter.dump_json(result.all_messages()).decode())
            db.add(saved)
            db.commit()
            db.expire(saved)
            history = ModelMessagesTypeAdapter.validate_json(saved.history_json)
            now += timedelta(minutes=1)
    assert len(captured) == 18 and len(executions) == 6
    artifacts = db.query(AIContextArtifact).all()
    assert len(artifacts) == int(large_result)
    if large_result:
        assert json.loads(artifacts[0].content)['data'].endswith('TAIL_SENTINEL')
        assert 'TAIL_SENTINEL' not in json.dumps(captured, ensure_ascii=False)
    for segment in (captured[:12], captured[12:]):
        for before, after in pairwise(segment):
            assert_prefix(before, after, protocol)
    # Compaction necessarily changes the history prefix once. Static instructions
    # and entry points stay identical, and the new history then grows unchanged.
    assert all(body['tools'] == captured[0]['tools'] for body in captured)
    if protocol == 'anthropic':
        assert all(body['system'] == captured[0]['system'] for body in captured)
    elif protocol == 'openai_responses':
        assert all(body['instructions'] == captured[0]['instructions'] for body in captured)
    else:
        assert all(body['messages'][0] == captured[0]['messages'][0] for body in captured)
    assert len(captured[0]['tools']) == 5
    for index, body in enumerate(captured):
        markers = cache_blocks(body)
        if protocol == 'anthropic' or mode == 'anthropic_compat':
            expected = (3 if index == 0 else 4) if protocol == 'anthropic' else (2 if index == 0 else 3)
            assert len(markers) == expected
            assert all(block['cache_control'] == {'type': 'ephemeral', 'ttl': '5m'} for block in markers)
            # The live clock stays after the current checkpoint on every request.
            content = body['messages'][-1]['content']
            assert '实时本机时钟' in content[-1]['text'] and 'cache_control' not in content[-1]
            if protocol == 'anthropic':
                assert 'cache_control' in content[-2]
            else:
                assert 'cache_control' in body['messages'][-2]['content'][-1]
        else:
            assert not markers
    if protocol != 'anthropic':
        assert len({body['prompt_cache_key'] for body in captured}) == 1


@pytest.mark.parametrize(('protocol', 'mode'), MODES)
@pytest.mark.parametrize('outcome', ['success', 'failed'])
async def test_mixed_mcp_result_serialization_keeps_wire_blocks_and_outcome(
        db, monkeypatch, protocol, mode, outcome):
    """MCP mapping can return a list of JSON/text/image parts, including failures."""
    from pydantic_ai.providers import anthropic, openai

    png = base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a6wAAAABJRU5ErkJggg==')
    original_history = [
        ModelRequest(parts=[UserPromptPart('Inspect this test resource')]),
        ModelResponse(parts=[ToolCallPart('execute_tool',
            {'name': 'mcp__1__inspect', 'arguments': {}}, 'mixed-call')]),
        ModelRequest(parts=[ToolReturnPart('execute_tool',
            [{'z': [3, 1, '甲'], 'a': {'second': False, 'first': None}},
             'verbatim\ntext "quoted"', BinaryContent(png, media_type='image/png')],
            'mixed-call', outcome=outcome)]),
    ]
    original_bytes = ModelMessagesTypeAdapter.dump_json(original_history)
    captured = []

    def respond(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=reply(protocol, len(captured)))

    module, provider = (anthropic, 'AnthropicProvider') if protocol == 'anthropic' else (openai, 'OpenAIProvider')
    original = getattr(module, provider)
    conv = AIConversation(title='mixed result replay')
    db.add(conv)
    db.commit()
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(module, provider, lambda **kw: original(**kw, http_client=client))
        cfg = AIConfig(name='test', model='test', provider_kind=protocol,
                       base_url='https://test.example/v1', prompt_cache_mode=mode,
                       input_modalities_json='["text", "image"]')
        history = original_history
        for turn in range(3):
            agent = AgentRuntime(build_model(cfg, api_key='mock-only'), db, model_config=cfg)._build_agent(
                conversation_id=conv.id)
            result = await agent.run(f'Follow up {turn}', message_history=history,
                                     deps=AgentDeps(db=db, emit=None, conversation_id=conv.id))
            history = ModelMessagesTypeAdapter.validate_json(ModelMessagesTypeAdapter.dump_json(result.all_messages()))
            returned = next(p for m in history for p in m.parts if isinstance(p, ToolReturnPart))
            assert returned.outcome == outcome
            assert returned.metadata['zhishi_result_checked'] is True
            assert 'zhishi_result_ref' not in returned.metadata
    assert ModelMessagesTypeAdapter.dump_json(original_history) == original_bytes
    for before, after in pairwise(captured):
        assert_prefix(before, after, protocol)
    if protocol == 'anthropic':
        tool_result = next(block for message in captured[0]['messages'] for block in message['content']
                           if block['type'] == 'tool_result')
        assert tool_result.get('is_error', False) == (outcome == 'failed')
        assert any(block['type'] == 'image' for block in tool_result['content'])
    elif protocol == 'openai_responses':
        assert 'input_image' in json.dumps(captured[0])
    else:
        # Current application policy replaces Chat tool-return media with a notice.
        assert base64.b64encode(png).decode() not in json.dumps(captured[0])
        assert '历史附件内容未向当前模型提供' in json.dumps(captured[0], ensure_ascii=False)
