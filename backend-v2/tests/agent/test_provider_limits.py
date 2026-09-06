import json

import httpx2 as httpx
import pytest
from pydantic_ai import Agent

from zhishi.agent.providers import build_model
from zhishi.domain.models import AIConfig


@pytest.mark.parametrize(('protocol', 'wire_field'), [
    ('openai_compat', 'max_completion_tokens'),
    ('openai_responses', 'max_output_tokens'),
    ('anthropic', 'max_tokens'),
])
@pytest.mark.parametrize('effort', [None, 'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'])
def test_output_limit_reaches_provider_wire(protocol, wire_field, effort, monkeypatch):
    if protocol == 'anthropic' and effort == 'minimal':
        with pytest.raises(ValueError, match='Anthropic 不支持'):
            build_model(AIConfig(name='test', provider_kind=protocol, reasoning_effort=effort), api_key='mock')
        return
    captured = []
    def respond(request):
        captured.append(json.loads(request.content))
        if protocol == 'anthropic':
            payload = {'id': 'msg-test', 'type': 'message', 'role': 'assistant', 'model': 'test',
                       'content': [{'type': 'text', 'text': 'ok'}], 'stop_reason': 'end_turn',
                       'stop_sequence': None, 'usage': {'input_tokens': 2, 'output_tokens': 1}}
        elif protocol == 'openai_responses':
            payload = {'id': 'resp-test', 'object': 'response', 'created_at': 1,
                       'model': 'test', 'status': 'completed',
                       'output': [{'type': 'message', 'id': 'msg-test', 'status': 'completed',
                                   'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'ok', 'annotations': []}]}],
                       'usage': {'input_tokens': 2, 'output_tokens': 1, 'total_tokens': 3}}
        else:
            payload = {'id': 'chat-test', 'object': 'chat.completion', 'created': 1, 'model': 'test',
                       'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'ok'}, 'finish_reason': 'stop'}],
                       'usage': {'prompt_tokens': 2, 'completion_tokens': 1, 'total_tokens': 3}}
        return httpx.Response(200, json=payload)
    from pydantic_ai.providers import anthropic, openai
    module, name = (anthropic, 'AnthropicProvider') if protocol == 'anthropic' else (openai, 'OpenAIProvider')
    original = getattr(module, name)
    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(module, name, lambda **kw: original(**kw, http_client=client))
    config = AIConfig(name='test', model='test', provider_kind=protocol,
                      base_url='https://provider.example/v1', max_output_tokens=777, reasoning_effort=effort)
    model = build_model(config, api_key='mock-only')
    assert Agent(model).run_sync('hello').output == 'ok'
    assert captured[0][wire_field] == 777
    if protocol == 'openai_responses':
        assert captured[0]['store'] is False
        assert captured[0].get('reasoning', {}).get('effort') == effort
    elif protocol == 'anthropic':
        if effort is None:
            assert 'thinking' not in captured[0] and 'output_config' not in captured[0]
        elif effort == 'none':
            assert captured[0]['thinking'] == {'type': 'disabled'}
            assert 'output_config' not in captured[0]
        else:
            assert captured[0]['thinking'] == {'type': 'adaptive'}
            assert captured[0]['output_config']['effort'] == effort
    else:
        assert captured[0].get('reasoning_effort') == effort
    if effort is None:
        assert 'reasoning_effort' not in captured[0]
        assert 'reasoning' not in captured[0]
