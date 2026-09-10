import json
from datetime import datetime, timedelta, timezone

import httpx2 as httpx
import pytest
from pydantic_ai import Agent

from zhishi.agent.prompt_cache import live_clock_hooks
from zhishi.agent.providers import build_model
from zhishi.agent.runtime import _usage_dict
from zhishi.domain.models import AIConfig
from zhishi.infra import local_clock


@pytest.mark.parametrize(('protocol', 'cache_mode', 'ttl', 'key'), [
    ('openai_compat', 'auto', '5m', None), ('openai_responses', 'auto', '5m', True),
    ('anthropic', 'auto', '5m', None), ('anthropic', 'auto', '1h', None),
    ('anthropic', 'disabled', '5m', None), ('openai_compat', 'anthropic_compat', '1h', True),
    ('openai_compat', 'disabled', '5m', True),
])
def test_cache_markers_stable_prefix_and_reported_usage_reach_wire(protocol, cache_mode, ttl, key, monkeypatch):
    """Real adapters, mocked HTTP: inspect requests, not just configured flags."""
    captured = []
    now = datetime(2026, 12, 31, 23, 59, tzinfo=timezone(timedelta(hours=8)))
    monkeypatch.setattr(local_clock, 'local_now', lambda: now)

    def respond(request):
        captured.append(json.loads(request.content))
        if protocol == 'anthropic':
            payload = {'id': 'msg-test', 'type': 'message', 'role': 'assistant', 'model': 'test',
                       'content': [{'type': 'text', 'text': 'ok'}], 'stop_reason': 'end_turn',
                       'stop_sequence': None, 'usage': {'input_tokens': 7, 'output_tokens': 1,
                           'cache_read_input_tokens': 1024, 'cache_creation_input_tokens': 512}}
        elif protocol == 'openai_responses':
            payload = {'id': 'resp-test', 'object': 'response', 'created_at': 1, 'model': 'test',
                       'status': 'completed', 'output': [{'type': 'message', 'id': 'msg-test',
                           'status': 'completed', 'role': 'assistant', 'content': [
                               {'type': 'output_text', 'text': 'ok', 'annotations': []}]}],
                       'usage': {'input_tokens': 1543, 'output_tokens': 1, 'total_tokens': 1544,
                                 'input_tokens_details': {'cached_tokens': 1024}}}
        else:
            payload = {'id': 'chat-test', 'object': 'chat.completion', 'created': 1, 'model': 'test',
                       'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'ok'},
                                    'finish_reason': 'stop'}],
                       'usage': {'prompt_tokens': 1543, 'completion_tokens': 1, 'total_tokens': 1544,
                                 'prompt_tokens_details': {'cached_tokens': 1024}}}
        return httpx.Response(200, json=payload)

    from pydantic_ai.providers import anthropic, openai
    module, name = (anthropic, 'AnthropicProvider') if protocol == 'anthropic' else (openai, 'OpenAIProvider')
    original = getattr(module, name)
    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(module, name, lambda **kw: original(**kw, http_client=client))
    config = AIConfig(name='test', model='test', provider_kind=protocol,
                      base_url='https://provider.example/v1', prompt_cache_mode=cache_mode,
                      prompt_cache_ttl=ttl, prompt_cache_key=key)
    model = build_model(config, api_key='mock-only')
    agent = Agent(model, instructions='Stable rules. ' * 100, capabilities=[live_clock_hooks(config, 42)])

    @agent.tool_plain
    def example_read() -> str:
        """A stable read-only tool definition."""
        return 'example'

    first = agent.run_sync('First question')
    history = first.all_messages()
    from pydantic_ai.messages import ModelMessagesTypeAdapter
    original_history = ModelMessagesTypeAdapter.dump_json(history)
    now += timedelta(minutes=2)
    second = agent.run_sync('Follow-up question', message_history=history)
    assert ModelMessagesTypeAdapter.dump_json(history) == original_history
    assert second.output == 'ok'
    assert captured[0]['tools'] == captured[1]['tools']
    assert '2027-01-01T00:01:00+08:00' in json.dumps(captured[1], ensure_ascii=False)
    if protocol == 'anthropic':
        assert captured[0]['system'] == captured[1]['system']
        assert '实时本机时钟' not in json.dumps(captured[0]['system'], ensure_ascii=False)
        content = captured[1]['messages'][-1]['content']
        assert '实时本机时钟' in content[-1]['text']
        assert 'cache_control' not in content[-1]
        if cache_mode != 'disabled':
            assert captured[0]['system'][-1]['cache_control'] == {'type': 'ephemeral', 'ttl': ttl}
            assert captured[0]['tools'][-1]['cache_control'] == {'type': 'ephemeral', 'ttl': ttl}
            assert content[-2]['cache_control'] == {'type': 'ephemeral', 'ttl': ttl}
        else:
            assert 'cache_control' not in json.dumps(captured)
        assert captured[0]['messages'][-1]['content'] == captured[1]['messages'][0]['content']
        assert 'cache_control' not in captured[1]  # Gateway-compatible block markers.
    elif protocol == 'openai_responses':
        assert captured[0]['instructions'] == captured[1]['instructions']
        assert '实时本机时钟' not in captured[0]['instructions']
        assert captured[1]['store'] is False
    else:
        systems = [[m for m in body['messages'] if m['role'] in ('system', 'developer')]
                   for body in captured]
        assert systems[0] == systems[1]
        assert '实时本机时钟' not in json.dumps(systems[0], ensure_ascii=False)
        if cache_mode == 'anthropic_compat':
            assert systems[0][-1]['content'][-1]['cache_control'] == {'type': 'ephemeral', 'ttl': ttl}
            assert 'cache_control' not in json.dumps(captured[1]['messages'][-1])
            markers = [block for message in captured[1]['messages']
                       for block in message.get('content', []) if isinstance(block, dict) and 'cache_control' in block]
            assert len(markers) == 3
            assert all(block['cache_control']['ttl'] == ttl for block in markers)
            assert captured[1]['messages'][:len(captured[0]['messages'])] == captured[0]['messages']
        else:
            assert 'cache_control' not in json.dumps(captured)
    if key and protocol != 'anthropic' and cache_mode != 'disabled':
        assert captured[0]['prompt_cache_key'] == captured[1]['prompt_cache_key']
        assert len(captured[1]['prompt_cache_key']) == 64
    else:
        assert 'prompt_cache_key' not in captured[0]
    usage = _usage_dict(second.usage)
    assert usage['input_tokens'] == 1543  # Includes cached input, never subtract for context budgeting.
    assert usage['cache_read_tokens'] == 1024
    assert usage['cache_write_tokens'] == (512 if protocol == 'anthropic' else 0)
    assert usage['total_tokens'] == 1544


def test_missing_usage_keeps_zero_totals():
    assert _usage_dict(None) == dict(input_tokens=0, output_tokens=0, total_tokens=0,
                                    cache_read_tokens=0, cache_write_tokens=0)


def test_application_context_does_not_replace_user_input_during_compaction():
    from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart, TextPart, ModelMessagesTypeAdapter
    from zhishi.agent.context_parts import append_context, latest_context, adapt_cache_points
    from zhishi.agent.context_budget import safe_round_starts
    from zhishi.agent.context_steps import retained_prefix
    messages = [ModelRequest(parts=[UserPromptPart('Keep the exact original request')]),
                ModelResponse(parts=[TextPart('Working')])]
    messages = append_context(messages, 'clock', 'clock-one', cache_before=True)
    messages += [ModelResponse(parts=[TextPart('More work')])]
    messages = append_context(messages, 'clock', 'clock-two', cache_before=True)
    restored = ModelMessagesTypeAdapter.validate_json(ModelMessagesTypeAdapter.dump_json(messages))
    assert safe_round_starts(restored) == [0]
    retained = retained_prefix(restored, len(restored))
    assert len(retained) == 1 and len(retained[0].parts) == 1
    assert retained[0].parts[0].content == 'Keep the exact original request'
    assert latest_context(restored, 'clock') == 'clock-two'
    stripped = ModelMessagesTypeAdapter.dump_json(adapt_cache_points(restored))
    assert b'cache-point' not in stripped and b'clock-one' in stripped
    assert b'cache-point' in ModelMessagesTypeAdapter.dump_json(restored)


def test_skills_append_once_and_are_restored_after_compaction():
    from pydantic_ai.messages import ModelRequest, UserPromptPart, InstructionPart, ToolReturnPart
    from pydantic_ai.models import ModelRequestContext, ModelRequestParameters
    from pydantic_ai.models.test import TestModel
    from pydantic_ai.tools import ToolDefinition
    from zhishi.agent.tool_discovery import ToolDiscovery
    from zhishi.agent.context_parts import context_items, latest_context
    skill = '内置·任务、提醒与日程'
    discovery = ToolDiscovery([(skill, 'Use explicit dates.')])
    discovery.catalog = {'create_task': ToolDefinition(name='create_task')}
    request = ModelRequestContext(model=TestModel(), messages=[ModelRequest(parts=[UserPromptPart('hello'),
        ToolReturnPart('search_tools', {'loaded_tools': ['create_task']}, 'search')])],
        model_settings=None, model_request_parameters=ModelRequestParameters(
            function_tools=[ToolDefinition(name='create_task')], instruction_parts=[InstructionPart('Stable rules')]))
    first = discovery._with_context(request)
    second = discovery._with_context(first)
    assert first.model_request_parameters.instruction_parts == request.model_request_parameters.instruction_parts
    assert sum(len(context_items(part)) for message in second.messages for part in message.parts) == 1
    restored = discovery._with_context(request)  # Compacted context no longer carries the skill.
    assert latest_context(restored.messages, f'skill:{skill}') is not None
    discovery.skills = [(skill, 'Updated operation rules.')]
    updated = discovery._with_context(second)
    assert 'Updated operation rules.' in latest_context(updated.messages, f'skill:{skill}')
    assert 'Updated operation rules.' not in latest_context(first.messages, f'skill:{skill}')
