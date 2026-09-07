import json
from types import SimpleNamespace

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart, UserPromptPart
from pydantic_ai.models import ModelRequestContext, ModelRequestParameters
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.tools import ToolDefinition

from zhishi.agent import compaction
from zhishi.agent.context_budget import estimate_messages_tokens, history_budget
from zhishi.agent.tool_discovery import CORE_TOOLS, ToolDiscovery
from zhishi.agent.tool_results import externalize_results, save_artifact
from zhishi.agent.tools.session_tools import read_tool_result
from zhishi.domain.models import AIConversation, AIContextArtifact


def test_discovery_chinese_feature_filter_and_bounded_resume_working_set():
    discovery = ToolDiscovery()
    discovery.catalog = {f'read_{i}': ToolDefinition(name=f'read_{i}', description='阅读资料正文') for i in range(30)}
    discovery.catalog['record_transaction'] = ToolDefinition(name='record_transaction', description='记录账本支出收入')
    found = json.loads(discovery.search(None, query='账本支出'))
    assert found['loaded_tools'] == ['record_transaction']
    assert json.loads(discovery.search(None, names=['disabled_tool']))['unknown_names'] == ['disabled_tool']
    messages = [ModelRequest(parts=[ToolReturnPart('search_tools', {'loaded_tools': [f'read_{i}']}, f'id{i}')]) for i in range(30)]
    active = discovery._working_set(messages)
    assert len(active - CORE_TOOLS) == 18 and 'read_29' in active and 'read_0' not in active


def test_long_result_saved_in_full_is_scoped_paginated_and_never_rearchives_reader(db):
    a, b = AIConversation(title='a'), AIConversation(title='b')
    db.add_all([a, b]); db.commit()
    content = json.dumps({'ok': False, 'error': 'remote failure', 'data': '资料甲乙丙丁' * 3000 + 'TAIL_SENTINEL'}, ensure_ascii=False)
    original = ModelRequest(parts=[ToolReturnPart('read_material', content, 'exact-call')])
    result = externalize_results([original], budget=8192, archive=lambda tool, text: save_artifact(db, a.id, tool, text))
    part = result[0].parts[0]
    pointer = json.loads(part.content)
    assert pointer['ok'] is False and pointer['error'] == 'remote failure'
    assert part.tool_call_id == 'exact-call' and original.parts[0].content == content
    assert len(part.content) < 1200
    ref = pointer['result_ref']
    assert db.get(AIContextArtifact, ref).content == content
    assert save_artifact(db, a.id, 'read_material', content) == ref
    ctx = SimpleNamespace(deps=SimpleNamespace(conversation_id=a.id))
    page = json.loads(read_tool_result(db, ref, query='TAIL_SENTINEL', ctx=ctx))
    assert 'TAIL_SENTINEL' in page['content']
    assert not json.loads(read_tool_result(db, ref, ctx=SimpleNamespace(deps=SimpleNamespace(conversation_id=b.id))))['ok']
    rebuilt, offset = '', 0
    while True:
        page = json.loads(read_tool_result(db, ref, offset=offset, ctx=ctx))
        rebuilt += page['content']
        if not page['next_call']:
            break
        offset = page['end_offset']
    assert rebuilt == content
    bounded_page = [ModelRequest(parts=[ToolReturnPart('read_tool_result', page, 'page')])]
    assert externalize_results(bounded_page, budget=1024, archive=lambda *_: pytest.fail('reader cannot archive itself')) == bounded_page


def test_single_long_tool_turn_compacts_at_safe_step_and_preserves_exact_user(monkeypatch):
    cfg = SimpleNamespace(context_window=8192, max_output_tokens=512, model='test')
    user_text = '用户原文不能丢，最后核对所有材料。'
    messages = [ModelRequest(parts=[UserPromptPart(user_text)])]
    for i in range(10):
        messages += [ModelResponse(parts=[ToolCallPart('read_material', {'id': i}, f'call{i}')]),
                     ModelRequest(parts=[ToolReturnPart('read_material', '材料编号甲乙丙丁' * 300, f'call{i}')])]
    seen = []
    def summary(cfg, system, prompt, timeout):
        seen.append(prompt)
        return '保留任务目标与已经核对材料的摘要。'
    monkeypatch.setattr(compaction, '_oneshot_with_timeout', summary)
    result, text, fingerprint = compaction.summarize_history(None, cfg, messages, threshold=12, timeout=20)
    assert text and fingerprint and seen
    assert any(isinstance(p, UserPromptPart) and p.content == user_text for m in result for p in m.parts)
    calls = {p.tool_call_id for m in result for p in m.parts if isinstance(p, ToolCallPart)}
    returns = {p.tool_call_id for m in result for p in m.parts if isinstance(p, ToolReturnPart)}
    assert calls == returns and 'call9' in calls and len(calls) < 10
    assert estimate_messages_tokens(result) <= history_budget(cfg)


async def test_plan_mode_discovery_cannot_load_mutating_tools(db):
    from zhishi.agent.runtime import AgentRuntime, AgentDeps
    observed = []
    def model(messages, info):
        observed.append({tool.name for tool in info.function_tools})
        if len(observed) == 1:
            return ModelResponse(parts=[ToolCallPart('search_tools', {'names': ['record_transaction', 'delete_task']}, 'find')])
        return ModelResponse(parts=[TextPart('计划不执行写入')])
    agent = AgentRuntime(FunctionModel(model), db)._build_agent(plan_mode=True)
    await agent.run('先做计划', deps=AgentDeps(db=db, emit=None))
    assert not {'record_transaction', 'delete_task'} & set.union(*observed)
