import json
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import pytest
from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from tests.domain.test_research import NOW, project
from zhishi.domain.library import reading
from zhishi.domain.library import service as library
from zhishi.domain.models import MaterialChunk, MaterialIndex, Task
from zhishi.domain.research import service, sources
from zhishi.domain.research.schemas import PlanDraft


def upload(db, root, text, name='long.txt'):
    return library.save_upload(db, storage_root=root, upload=UploadFile(filename=name, file=BytesIO(text.encode())))


def test_old_truncated_cache_is_rebuilt_and_tail_is_searchable_after_restart(db, tmp_path):
    root = tmp_path/'attachments'
    body = '前文知识。'*8000+'\n最终要求：9月30日前完成研究报告。'
    file = upload(db, root, body)
    file.parse_status = 'parsed'
    file.extracted_text = json.dumps({'kind':'text','text':body[:30000],'tables':[]})
    db.commit()
    result = reading.search(db, '最终要求', root, file_id=file.id)
    hit = result['hits'][0]
    assert hit['part'] > 15 and result['documents'][0]['partial'] is False
    detail = reading.read(db, hit['file_id'], root, part=hit['part'], revision=hit['revision'])
    assert '9月30日' in detail['parts'][0]['text'] and detail['next_call'] is None
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    with factory() as restarted:
        assert reading.read(restarted, file.id, root, part=hit['part'])['document']['revision'] == hit['revision']


def test_concurrent_indexing_pagination_and_deleted_file_scope(db, tmp_path):
    root = tmp_path/'attachments'
    file = upload(db, root, 'abcdefghijklmn '*2000)
    library.ensure_parsed(db, file, storage_root=root)
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    def index():
        with factory() as session:
            return reading.read(session, file.id, root)['document']
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _:index(), range(4)))
    assert len({r['revision'] for r in results}) == 1
    assert db.scalar(select(func.count()).select_from(MaterialChunk)) == results[0]['total_parts']
    page = reading.read(db, file.id, root)
    args = page['next_call']['args']
    assert args['part'] == 4 and len(page['parts']) == 3
    assert reading.read(db, storage_root=root, **args)['parts'][0]['part'] == 4
    with pytest.raises(reading.MaterialConflict):
        reading.read(db, file.id, root, revision='0'*64)
    library.soft_delete(db, file.id)
    assert reading.search(db, 'abc', root)['hits'] == []
    with pytest.raises(LookupError):
        reading.read(db, file.id, root)


def test_search_literal_characters_and_project_scope(db, tmp_path):
    root = tmp_path/'attachments'
    one = upload(db, root, '费用：100%_确认。附录结论：可靠。')
    two = upload(db, root, '费用：1000。另一个项目的附录。', 'other.txt')
    p = project(db)
    sources.attach_material(db, p.id, one.id, root)
    result = reading.search(db, '附录', root, project_id=p.id)
    assert {h['file_id'] for h in result['hits']} == {one.id}
    assert reading.search(db, '%_', root)['hits'][0]['file_id'] == one.id
    assert reading.search(db, '附录', root, project_id=p.id, file_id=two.id)['hits'] == []


def test_phrase_crossing_chunk_boundary_is_searchable(db, tmp_path):
    root = tmp_path/'attachments'
    file = upload(db, root, '甲'*1998+'边界处的关键要求'+'乙'*2000)
    assert reading.search(db, '边界处的关键要求', root, file_id=file.id)['hits']


def test_quotes_are_validated_before_plan_and_saved_to_real_task(db, tmp_path):
    root = tmp_path/'attachments'
    file = upload(db, root, '基础介绍。'*8000+'附录要求：先复现基线，再比较实验。')
    p = project(db)
    source = sources.attach_material(db, p.id, file.id, root)
    assert source.document.total_parts > 15 and source.content_is_excerpt
    hit = reading.search(db, '附录要求', root, project_id=p.id)['hits'][0]
    ref = {'source_id':source.id,'part':hit['part'],'revision':hit['revision'],'quote':'先复现基线，再比较实验'}
    payload = {'version':1,'rationale':'遵循附录要求','steps':[{'title':'复现实验','outcome':'提交对照结果',
        'minutes':45,'source_refs':[ref]}]}
    bad = PlanDraft.model_validate(payload)
    bad.steps[0].source_refs[0].quote = '不存在的原文'
    with pytest.raises(reading.MaterialConflict):
        service.preview_plan(db, p.id, bad, now=NOW)
    plan = service.preview_plan(db, p.id, PlanDraft.model_validate(payload), now=NOW)
    result = service.apply_plan(db, plan.id, now=NOW)
    task = db.get(Task, result.result['task_ids'][0])
    assert ref['quote'] in task.notes and f'片段 {hit["part"]}' in task.notes
    assert f'revision={hit["revision"]}' in task.notes
    assert plan.units[0].source_ids == [source.id]
    assert service.detail(db, p.id).tasks[0].source_refs[0].quote == ref['quote']
    replan = service.preview_replan(db, p.id, 2, now=NOW)
    service.apply_plan(db, replan.id, now=NOW)
    assert service.detail(db, p.id).tasks[0].source_refs[0].quote == ref['quote']


def test_stale_index_revision_prevents_applying_quote_preview(db, tmp_path):
    root = tmp_path/'attachments'
    file = upload(db, root, '必须阅读这一句。')
    p = project(db)
    source = sources.attach_material(db, p.id, file.id, root)
    doc = reading.read(db, file.id, root)
    plan = service.preview_plan(db, p.id, PlanDraft(version=1,rationale='引用原文',steps=[{
        'title':'阅读','outcome':'解释原文','minutes':45,'source_refs':[{'source_id':source.id,'part':1,
        'revision':doc['document']['revision'],'quote':'必须阅读'}]}]), now=NOW)
    db.get(MaterialIndex, file.id).revision = 'a'*64
    db.commit()
    with pytest.raises(reading.MaterialConflict):
        service.apply_plan(db, plan.id, now=NOW)
    assert db.scalar(select(func.count()).select_from(Task)) == 0


def test_purge_removes_index_and_old_link_cache_is_marked_partial(db, tmp_path):
    root = tmp_path/'attachments'
    file = upload(db, root, '会被彻底删除的材料')
    reading.read(db, file.id, root)
    library.soft_delete(db, file.id)
    library.purge(db, file.id, storage_root=root)
    assert db.scalar(select(func.count()).select_from(MaterialChunk)) == 0
    link = library.save_link(db,title='旧网页',url='https://example.org/article')
    link.parse_status = 'parsed'
    link.extracted_text = json.dumps({'kind':'text','text':'旧开头摘要','tables':[]})
    db.commit()
    doc = reading.read(db, link.id, root)
    assert doc['document']['partial'] and '旧缓存' in doc['document']['warnings'][0]
