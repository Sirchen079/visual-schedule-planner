"""Brainstorming has its own interview policy and readonly toolset; Plan is unchanged."""
import json

from pydantic_ai.models.function import FunctionModel
from zhishi.agent import prompts
from zhishi.agent.runtime import AgentRuntime


def test_routes_only_the_selected_thinking_skill(db):
    prompts.seed_builtin_skills(db)
    for deferred in (True, False):
        normal = prompts.build_instructions(db, defer_builtin=deferred)
        brainstorming = prompts.build_instructions(db, brainstorm_mode=True, defer_builtin=deferred)
        plan = prompts.build_instructions(db, plan_mode=True, defer_builtin=deferred)
        assert '【技能：内置·梳理想法】' in normal
        assert '完整决策访谈' not in normal
        assert '【技能：内置·完整决策访谈】' in brainstorming
        assert '【技能：内置·梳理想法】' not in brainstorming
        assert '决策树' in brainstorming and '用户明确确认理解一致后' in brainstorming
        assert '【技能：内置·梳理想法】' not in plan
        assert '【技能：内置·完整决策访谈】' not in plan
        assert prompts.PLAN_MODE_INSTRUCTION in plan


async def test_question_ends_once_without_forcing_a_plan(db):
    calls = []
    async def scripted(messages, info):
        calls.append(info)
        yield '你希望先解决哪一个问题？'
    events = [e async for e in AgentRuntime(FunctionModel(stream_function=scripted), db).run_stream(
        user_text='帮我问清楚需求', conversation_id=None, brainstorm_mode=True)]
    assert len(calls) == 1
    assert events[-1]['type'] == 'done'
    assert not any(e['type'] in ('plan_card', 'run_error') for e in events)
    from zhishi.domain.models import AIMessage
    user = db.query(AIMessage).filter_by(role='user').one()
    assert json.loads(user.display_json)['brainstorm_mode'] is True


async def test_discovery_cannot_enable_writes_or_plan_submission(db):
    from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
    from zhishi.agent.runtime import AgentDeps
    def scripted(messages, info):
        names = {tool.name for tool in info.function_tools}
        assert 'ask_user' in names
        assert 'propose_plan' not in names
        assert 'create_task' not in names
        results = [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
        if not results:
            return ModelResponse(parts=[ToolCallPart('search_tools', {'names': ['create_task', 'propose_plan', 'list_tasks']}, 'search')])
        result = json.loads(results[-1].content)
        assert result['loaded_tools'] == ['list_tasks']
        return ModelResponse(parts=[TextPart('继续讨论需求。')])
    agent = AgentRuntime(FunctionModel(scripted), db)._build_agent(brainstorm_mode=True)
    await agent.run('先讨论', deps=AgentDeps(db=db, emit=None))


def test_modes_are_exclusive_at_api_boundary():
    import pytest
    from pydantic import ValidationError
    from zhishi.server.routes.ai import ChatBody
    with pytest.raises(ValidationError):
        ChatBody(message='想想', plan_mode=True, brainstorm_mode=True)


def test_original_and_license_ship_with_skill():
    folder = prompts._SKILLS_DIR / 'grilling'
    assert 'design tree' in (folder / 'original.md').read_text(encoding='utf-8')
    license_text = (folder / 'LICENSE').read_text(encoding='utf-8')
    assert 'MIT License' in license_text and 'Copyright (c) 2026 Matt Pocock' in license_text
