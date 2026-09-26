import json
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import UploadFile
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.tools import DeferredToolRequests

from zhishi.agent import prompts
from zhishi.agent.runtime import AgentDeps, AgentRuntime
from zhishi.agent.tools.skill_tools import (
    read_skill,
    read_skill_resource,
    save_skill,
    search_skills,
    update_skill,
)
from zhishi.domain import settingsvc, skills
from zhishi.domain.library import service as library
from zhishi.domain.models import AIConversation, AISkill, AISkillResource
from zhishi.infra.database import make_session_factory


def create(db, **kwargs):
    return json.loads(save_skill(db, **{'name': '周报方法', 'description': '整理每周项目汇报时使用',
                                       'content': '先列出进度，再列风险与下一步。', **kwargs}))


def test_skill_persists_across_sessions_and_loads_only_on_demand(db):
    saved = create(db)
    with make_session_factory(db.get_bind())() as fresh:
        text = prompts.build_instructions(fresh)
        assert '周报方法' in text
        assert '先列出进度' not in text
        found = json.loads(search_skills(fresh, '周报'))['skills']
        assert found[0]['id'] == saved['id']
        loaded = json.loads(read_skill(fresh, saved['id']))
        assert loaded['content'] == '先列出进度，再列风险与下一步。'
        assert loaded['enabled'] is True


def test_snapshot_survives_source_deletion_and_supports_paging(db, tmp_path):
    root = tmp_path / 'attachments'
    source = library.save_upload(db, storage_root=root, upload=UploadFile(
        filename='method.txt', file=BytesIO(('第一步核对数据。\n' * 1800).encode())))
    ctx = SimpleNamespace(deps=SimpleNamespace(storage_root=root))
    saved = create(db, source_file_ids=[source.id], ctx=ctx)
    info = json.loads(read_skill(db, saved['id']))
    resource = info['resources'][0]
    library.soft_delete(db, source.id)
    library.purge(db, source.id, storage_root=root)
    first = json.loads(read_skill_resource(db, saved['id'], resource['id']))
    assert '第一步核对数据' in first['text'] and first['next_call']
    second = json.loads(read_skill_resource(db, **first['next_call']['args']))
    assert second['offset'] == len(first['text'])
    # Updating instructions preserves the independent snapshot by default.
    update_skill(db, saved['id'], info['revision'], '周报方法', '每周汇报', '核对后生成周报。')
    assert skills.resources(db, saved['id'])[0].id == resource['id']
    db.delete(db.get(AISkill, saved['id']))
    db.commit()
    assert db.query(AISkillResource).count() == 0


def test_failed_source_save_and_duplicate_do_not_leave_partial_skills(db, tmp_path):
    ctx = SimpleNamespace(deps=SimpleNamespace(storage_root=tmp_path))
    with pytest.raises(LookupError):
        create(db, source_file_ids=[999], ctx=ctx)
    assert db.query(AISkill).count() == 0
    create(db)
    with pytest.raises(skills.SkillConflict):
        create(db)
    assert db.query(AISkill).count() == 1


def test_pdf_snapshot_keeps_page_locations_and_scan_warnings(db, tmp_path):
    """PDF→技能：快照按页定位保存；扫描页告警与占位对 agent 可见，且独立于原文件。"""
    from tests.adapters.test_markdown_pipeline import _synthetic_pdf
    text_page = (b'BT /F1 14 Tf 50 750 Td (Weekly Review) Tj ET '
                 b'BT /F1 12 Tf 50 720 Td (Check progress and risks.) Tj ET')
    scan_page = b'50 50 500 700 re S'   # 只有矢量笔画没有文本：判扫描页
    path = tmp_path / 'mixed.pdf'
    _synthetic_pdf(path, [text_page, scan_page])
    root = tmp_path / 'attachments'
    root.mkdir()
    source = library.save_upload(db, storage_root=root, upload=UploadFile(
        filename='mixed.pdf', file=BytesIO(path.read_bytes())))
    ctx = SimpleNamespace(deps=SimpleNamespace(storage_root=root))
    saved = create(db, source_file_ids=[source.id], ctx=ctx)
    resource = json.loads(read_skill(db, saved['id']))['resources'][0]
    assert resource['name'] == 'mixed.pdf'
    assert any('扫描页' in w for w in resource['warnings'])
    first = json.loads(read_skill_resource(db, saved['id'], resource['id']))
    assert first['text'].startswith('【') and '第 1 页' in first['text']
    assert 'Weekly Review' in first['text'] and '等待 OCR 识别' in first['text']
    library.soft_delete(db, source.id)
    library.purge(db, source.id, storage_root=root)
    again = json.loads(read_skill_resource(db, saved['id'], resource['id']))
    assert 'Weekly Review' in again['text']


def test_replacing_snapshots_invalidates_old_resource_ids(db, tmp_path):
    root = tmp_path / 'attachments'
    source = library.save_upload(db, storage_root=root, upload=UploadFile(
        filename='rules.txt', file=BytesIO(b'Always check source facts.')))
    ctx = SimpleNamespace(deps=SimpleNamespace(storage_root=root))
    saved = create(db, source_file_ids=[source.id], ctx=ctx)
    old_id = skills.resources(db, saved['id'])[0].id
    update_skill(db, saved['id'], saved['revision'], '周报方法', '周报', '再次核对事实',
                 source_file_ids=[source.id], ctx=ctx)
    assert skills.resources(db, saved['id'])[0].id != old_id
    with pytest.raises(LookupError):
        read_skill_resource(db, saved['id'], old_id)


def test_receipt_replay_and_stale_update(db):
    conversation = AIConversation(title='保存技能')
    db.add(conversation)
    db.commit()
    ctx = SimpleNamespace(deps=SimpleNamespace(conversation_id=conversation.id, run_id='skill-run'))
    first = create(db, ctx=ctx)
    assert create(db, ctx=ctx)['replayed'] is True
    update_skill(db, first['id'], first['revision'], '周报方法', '周报', '先核对事实。')
    with pytest.raises(skills.SkillConflict):
        update_skill(db, first['id'], first['revision'], '周报方法', '周报', '覆盖新版本。')
    assert skills.get(db, first['id']).content == '先核对事实。'


def test_disabled_builtin_validation_and_paging(db):
    saved = create(db, content='方法' * 4000)
    first = json.loads(read_skill(db, saved['id']))
    second = json.loads(read_skill(db, **first['next_call']['args']))
    assert first['content'] + second['content'] == '方法' * 4000
    row = skills.get(db, saved['id'])
    row.enabled = False
    db.commit()
    assert not json.loads(search_skills(db))['skills']
    assert '周报方法' not in prompts.build_instructions(db)
    with pytest.raises(LookupError):
        read_skill(db, saved['id'])
    row.is_builtin = True
    db.commit()
    with pytest.raises(ValueError, match='内置'):
        update_skill(db, row.id, skills.revision(db, row), '内置', '用途', '修改')
    for values in ({'name': ' '}, {'description': ' '}, {'content': 'x' * 30001}):
        with pytest.raises(ValueError):
            create(db, **values)


async def test_real_dispatch_discovers_saves_and_reads_in_same_run(db):
    steps = []
    def model(messages, info):
        results = [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
        steps.append(len(results))
        if not results:
            return ModelResponse(parts=[ToolCallPart('search_tools', {'names': ['save_skill']}, 'find')])
        result = json.loads(results[-1].content)
        if len(results) == 1:
            assert 'save_skill' in result['loaded_tools']
            return ModelResponse(parts=[ToolCallPart('execute_tool', {'name': 'save_skill', 'arguments': {
                'name': '会议纪要', 'description': '整理会议记录时使用', 'content': '按议题、结论、责任人整理。'}}, 'save')])
        if len(results) == 2:
            assert result['ok'] is True
            return ModelResponse(parts=[ToolCallPart('execute_tool', {'name': 'read_skill',
                'arguments': {'skill_id': result['id']}}, 'read')])
        assert result['content'] == '按议题、结论、责任人整理。'
        return ModelResponse(parts=[TextPart('已保存并读取')])
    result = await AgentRuntime(FunctionModel(model), db)._build_agent().run(
        '把会议纪要方法保存成技能', deps=AgentDeps(db=db, emit=None))
    assert result.output == '已保存并读取' and len(steps) == 4


@pytest.mark.parametrize('mode', ['careful', 'plan', 'brainstorm'])
async def test_skill_writes_obey_existing_mode_and_permission_gates(db, mode):
    if mode == 'careful':
        settingsvc.set_setting(db, 'agent_autonomy', 'careful')
    calls = []
    def model(messages, info):
        calls.append(1)
        if len(calls) == 1:
            return ModelResponse(parts=[ToolCallPart('execute_tool', {'name': 'save_skill', 'arguments': {
                'name': '规则', 'description': '写作', 'content': '使用短句'}}, 'save')])
        return ModelResponse(parts=[TextPart('不能写入')])
    result = await AgentRuntime(FunctionModel(model), db)._build_agent(
        plan_mode=mode == 'plan', brainstorm_mode=mode == 'brainstorm').run(
            '保存技能', deps=AgentDeps(db=db, emit=None))
    assert db.query(AISkill).count() == 0
    if mode == 'careful':
        assert isinstance(result.output, DeferredToolRequests)
