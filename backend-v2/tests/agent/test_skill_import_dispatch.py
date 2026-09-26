import json

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.tools import DeferredToolRequests

from tests.domain.test_skill_imports import skill
from zhishi.adapters import github_skills
from zhishi.agent.runtime import AgentDeps, AgentRuntime
from zhishi.domain import settingsvc
from zhishi.domain.models import AISkill


async def test_ai_discovers_imports_github_and_reads_packaged_reference(db, monkeypatch):
    monkeypatch.setattr(github_skills, 'fetch', lambda *_: (
        {'weekly/SKILL.md': skill(), 'weekly/references/rules.md': b'Facts only.'},
        'https://github.com/acme/report/tree/' + 'a' * 40))
    def model(messages, info):
        results = [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
        if not results:
            return ModelResponse(parts=[ToolCallPart('search_tools', {'query': 'GitHub 技能导入'}, 'discover')])
        result = json.loads(results[-1].content)
        if len(results) == 1:
            assert 'import_skill' in result['loaded_tools']
            return ModelResponse(parts=[ToolCallPart('execute_tool', {'name': 'import_skill',
                'arguments': {'github_url': 'https://github.com/acme/report'}}, 'import')])
        if len(results) == 2:
            assert result['status'] == 'imported'
            return ModelResponse(parts=[ToolCallPart('execute_tool', {'name': 'read_skill',
                'arguments': {'skill_id': result['skill_id']}}, 'read')])
        if len(results) == 3:
            assert any(f['path'] == 'references/rules.md' for f in result['files'])
            return ModelResponse(parts=[ToolCallPart('execute_tool', {'name': 'read_skill_file',
                'arguments': {'skill_id': result['id'], 'path': 'references/rules.md'}}, 'reference')])
        assert result['text'] == 'Facts only.'
        return ModelResponse(parts=[TextPart('已导入并读取规则')])
    result = await AgentRuntime(FunctionModel(model), db)._build_agent().run(
        '请导入 https://github.com/acme/report 的技能', deps=AgentDeps(db=db, emit=None))
    assert result.output == '已导入并读取规则' and db.query(AISkill).count() == 1


@pytest.mark.parametrize('mode', ['careful', 'plan', 'brainstorm'])
async def test_import_has_no_download_or_write_before_permission(db, monkeypatch, mode):
    monkeypatch.setattr(github_skills, 'fetch', lambda *_: pytest.fail('Import must not run'))
    if mode == 'careful':
        settingsvc.set_setting(db, 'agent_autonomy', 'careful')
    calls = []
    def model(messages, info):
        calls.append(1)
        if len(calls) == 1:
            return ModelResponse(parts=[ToolCallPart('execute_tool', {'name': 'import_skill',
                'arguments': {'github_url': 'https://github.com/acme/report'}}, 'import')])
        return ModelResponse(parts=[TextPart('当前不能导入')])
    result = await AgentRuntime(FunctionModel(model), db)._build_agent(
        plan_mode=mode == 'plan', brainstorm_mode=mode == 'brainstorm').run(
        '导入技能', deps=AgentDeps(db=db, emit=None))
    assert db.query(AISkill).count() == 0
    if mode == 'careful':
        assert isinstance(result.output, DeferredToolRequests)
