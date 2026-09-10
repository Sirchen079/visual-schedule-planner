import json
from dataclasses import asdict
from itertools import pairwise

import httpx2 as httpx
import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults, ToolApproved, ToolDenied

from zhishi.agent.runtime import AgentDeps, AgentRuntime
from zhishi.agent.tool_results import externalize_results


@pytest.mark.parametrize('decision', [True, False])
async def test_dispatch_validation_permission_resume_and_usage(db, decision):
    from zhishi.domain import settingsvc
    from zhishi.domain.models import Task
    settingsvc.set_setting(db, 'agent_autonomy', 'careful')
    observed = []
    def model(messages, info):
        observed.append(info)
        returns = [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
        if not returns:
            return ModelResponse(parts=[ToolCallPart('execute_tool',
                {'name': 'create_task', 'arguments': {'title': 'Approved exactly once'}}, 'write')])
        return ModelResponse(parts=[TextPart('Finished')])
    agent = AgentRuntime(FunctionModel(model), db)._build_agent()
    first = await agent.run('Create task', deps=AgentDeps(db=db, emit=None))
    assert isinstance(first.output, DeferredToolRequests)
    assert first.output.approvals[0].tool_name == 'execute_tool'
    assert db.query(Task).count() == 0
    # A fresh agent is essential: resume happens before discovery's first request.
    second_agent = AgentRuntime(FunctionModel(model), db)._build_agent()
    result = await second_agent.run(message_history=first.all_messages(),
        deferred_tool_results=DeferredToolResults(approvals={
            'write': ToolApproved() if decision else ToolDenied('Denied')}),
        deps=AgentDeps(db=db, emit=None))
    assert result.output == 'Finished'
    assert db.query(Task).count() == int(decision)
    assert result.usage.tool_calls == int(decision)
    assert all([asdict(t) for t in info.function_tools] == [asdict(t) for t in observed[0].function_tools]
               for info in observed)


@pytest.mark.parametrize(('plan', 'name', 'args'), [
    (False, 'create_task', {}), (False, 'missing_tool', {}),
    (True, 'create_task', {'title': 'Forbidden'}), (False, 'execute_tool', {})])
async def test_dispatch_invalid_args_unknown_and_plan_write_are_retried_without_execution(db, plan, name, args):
    from pydantic_ai.messages import RetryPromptPart

    from zhishi.domain.models import Task
    seen = []
    def model(messages, info):
        seen.append(messages)
        if len(seen) == 1:
            return ModelResponse(parts=[ToolCallPart('execute_tool', {'name': name, 'arguments': args}, 'bad')])
        assert any(isinstance(p, RetryPromptPart) for m in messages for p in m.parts)
        return ModelResponse(parts=[TextPart('Corrected')])
    result = await AgentRuntime(FunctionModel(model), db)._build_agent(plan_mode=plan).run(
        'Test', deps=AgentDeps(db=db, emit=None))
    assert result.output == 'Corrected' and result.usage.tool_calls == 0
    assert db.query(Task).count() == 0


def test_previously_sent_tool_results_stay_identical_under_later_pressure():
    original = [ModelRequest(parts=[ToolReturnPart('get_task', '甲' * 1000, 'read')])]
    frozen = externalize_results(original, budget=32000, archive=lambda *_: pytest.fail('Small first result'))
    later = [*frozen, ModelRequest(parts=[UserPromptPart('乙' * 5000),
             ToolReturnPart('get_task', 'small', 'b'), ToolReturnPart('get_task', 'small', 'c')])]
    result = externalize_results(later, budget=8192, archive=lambda *_: pytest.fail('Old text cannot be rewritten'))
    assert result[0].parts[0].content == original[0].parts[0].content


@pytest.mark.parametrize('protocol', ['openai_compat', 'openai_responses', 'anthropic'])
async def test_actual_wire_stays_stable_through_discovery_execution_and_followup(db, monkeypatch, protocol):
    from pydantic_ai.providers import anthropic, openai

    from zhishi.agent.providers import build_model
    from zhishi.domain.models import AIConfig
    captured = []
    calls = [('search_tools', {'names': ['get_current_time']}),
             ('execute_tool', {'name': 'get_current_time', 'arguments': {}}),
             ('search_tools', {'names': ['list_tasks']})]
    def respond(request):
        captured.append(json.loads(request.content))
        index = len(captured) - 1
        call = calls[index] if index < len(calls) else None
        if protocol == 'anthropic':
            content = ([{'type': 'tool_use', 'id': f'call{index}', 'name': call[0], 'input': call[1]}]
                       if call else [{'type': 'text', 'text': 'Done'}])
            payload = {'id': f'msg{index}', 'type': 'message', 'role': 'assistant', 'model': 'test',
                'content': content, 'stop_reason': 'tool_use' if call else 'end_turn', 'stop_sequence': None,
                'usage': {'input_tokens': 10, 'output_tokens': 1, 'cache_read_input_tokens': 1024}}
        elif protocol == 'openai_responses':
            output = ([{'type': 'function_call', 'id': f'fc{index}', 'call_id': f'call{index}',
                        'name': call[0], 'arguments': json.dumps(call[1]), 'status': 'completed'}]
                      if call else [{'type': 'message', 'id': f'm{index}', 'status': 'completed', 'role': 'assistant',
                                     'content': [{'type': 'output_text', 'text': 'Done', 'annotations': []}]}])
            payload = {'id': f'resp{index}', 'object': 'response', 'created_at': 1, 'model': 'test',
                'status': 'completed', 'output': output, 'usage': {'input_tokens': 1034, 'output_tokens': 1,
                'total_tokens': 1035, 'input_tokens_details': {'cached_tokens': 1024}}}
        else:
            message = {'role': 'assistant', 'content': None if call else 'Done'}
            if call:
                message['tool_calls'] = [{'id': f'call{index}', 'type': 'function',
                    'function': {'name': call[0], 'arguments': json.dumps(call[1])}}]
            payload = {'id': f'chat{index}', 'object': 'chat.completion', 'created': 1, 'model': 'test',
                'choices': [{'index': 0, 'message': message, 'finish_reason': 'tool_calls' if call else 'stop'}],
                'usage': {'prompt_tokens': 1034, 'completion_tokens': 1, 'total_tokens': 1035,
                          'prompt_tokens_details': {'cached_tokens': 1024}}}
        return httpx.Response(200, json=payload)
    module, name = (anthropic, 'AnthropicProvider') if protocol == 'anthropic' else (openai, 'OpenAIProvider')
    original = getattr(module, name)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(module, name, lambda **kw: original(**kw, http_client=client))
        cfg = AIConfig(name='test', model='test', provider_kind=protocol, base_url='https://test.example/v1')
        agent = AgentRuntime(build_model(cfg, api_key='mock'), db, model_config=cfg)._build_agent()
        first = await agent.run('Check time', deps=AgentDeps(db=db, emit=None))
        assert first.usage.tool_calls == 3
        second = await agent.run('Follow up', deps=AgentDeps(db=db, emit=None), message_history=first.all_messages())
        assert second.output == 'Done'
    assert len(captured) == 5
    assert all(row['tools'] == captured[0]['tools'] for row in captured)
    # Inspect provider bodies: previous request history is unchanged, including clock.
    key = 'input' if protocol == 'openai_responses' else 'messages'
    def content_only(value):
        if isinstance(value, list):
            return [content_only(x) for x in value]
        if isinstance(value, dict):
            return {k: content_only(v) for k, v in value.items() if k != 'cache_control'}
        return value
    for before, after in pairwise(captured):
        # Cache breakpoints move forward; they do not change cached prompt text.
        old, new = content_only(before[key]), content_only(after[key])
        assert new[:len(old) - 1] == old[:-1]
        if protocol != 'anthropic':
            assert new[:len(old)] == old
        else:
            # Anthropic merges consecutive user/tool-result messages at their tail.
            assert new[len(old) - 1]['content'][:len(old[-1]['content'])] == old[-1]['content']
