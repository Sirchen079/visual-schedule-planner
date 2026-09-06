# ruff: noqa: DTZ001 -- the v2 calendar stores local wall time.
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from io import BytesIO

import pytest
from fastapi import UploadFile
from freezegun import freeze_time
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from zhishi.domain.models import (
    Goal,
    KeyResult,
    LibraryFile,
    ResearchSource,
    ResearchTask,
    Task,
    TaskScheduleEntry,
)
from zhishi.domain.research import planning, service, sources
from zhishi.domain.research.schemas import GatherInput, PlanDraft, ProjectCreate, ProjectUpdate
from zhishi.domain.schedule import service as schedule
from zhishi.domain.tasks import service as tasks

NOW = datetime(2026, 9, 8, 9)


def project(db, **kwargs):
    return service.create_project(db, ProjectCreate(title='学习测试主题', objective='完成一个小项目并写出总结',
        start_date=date(2026,9,8), end_date=date(2026,9,20), daily_minutes=60,
        window_start='18:30', window_end='21:00', **kwargs))


def draft(version=1, source_ids=None):
    return PlanDraft(version=version, rationale='先理解概念，再用小项目验证。', steps=[
        {'title':'阅读基础', 'outcome':'能解释关键概念', 'minutes':90, 'source_ids':source_ids or []},
        {'title':'动手验证', 'outcome':'运行示例并记录结果', 'minutes':30, 'source_ids':source_ids or []}])


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_model_context_bounds_reference_text_and_exposes_continuation(db, monkeypatch):
    p = project(db)
    monkeypatch.setattr(sources.web, 'fetch_document', lambda url: sources.web.WebDocument('正文内容' * 2000))
    for i in range(5):
        sources.add_source(db, p.id, f'https://example.org/page-{i}', f'资料{i}')
    context = service.model_detail(db, p.id, excerpts=True)
    assert len(context['sources']) == 3 and len(context['sources'][0]['content']) == 600
    next_call = context['pagination']['next_calls'][0]
    assert next_call == {'tool': 'get_research_project', 'args': {'project_id': p.id, 'source_offset': 3, 'task_offset': 0}}
    last = service.model_detail(db, **next_call['args'])
    assert len(last['sources']) == 2 and len(last['sources'][0]['content']) == 8000
    assert not last['pagination']['next_calls']


def test_research_saves_each_outcome_and_retries_without_duplicate_library(db, monkeypatch):
    p = project(db)
    monkeypatch.setattr(sources.web, 'search', lambda *a, **k:[
        {'title':'教程', 'url':'https://example.org/tutorial', 'description':'基础教程'},
        {'title':'暂不可达', 'url':'https://example.org/unavailable'}])
    fetched = []
    def fetch(url):
        fetched.append(url)
        if url.endswith('unavailable'):
            raise ValueError('HTTP 503')
        return sources.web.WebDocument('真实抓取的测试正文，供学习项目检索和关联。')
    monkeypatch.setattr(sources.web, 'fetch_document', fetch)
    for _ in range(2):
        result = sources.gather(db, p.id, GatherInput(max_sources=2))
        assert result['ok'] and [r['status'] for r in result['sources']] == ['verified','failed']
        assert result['next_step']['tool'] == 'preview_research_plan'
    assert count(db, ResearchSource) == 2 and count(db, LibraryFile) == 1
    assert fetched.count('https://example.org/tutorial') == 1
    source = service.detail(db, p.id).sources[0]
    assert '真实抓取' in source.content and source.library_state == 'active'
    file = db.get(LibraryFile, source.library_file_id)
    assert file.parse_status == 'parsed' and '真实抓取' in file.extracted_text


def test_research_material_gather_uses_configured_web_services(db, monkeypatch):
    from zhishi.adapters import web_services
    p = project(db)
    calls = []
    def search(session, query, limit):
        assert session is db
        calls.append(('search', query))
        return [{'title': '已配置的来源', 'url': 'https://example.org/configured'}]
    def fetch(session, url):
        assert session is db
        calls.append(('fetch', url))
        return sources.web.WebDocument('通过所选网页服务读取的项目正文。')
    monkeypatch.setattr(web_services, 'search', search)
    monkeypatch.setattr(web_services, 'fetch_document', fetch)
    result = sources.gather(db, p.id, GatherInput(queries=['主题资料'], max_sources=1))
    assert result['ok']
    assert calls == [('search', '主题资料'), ('fetch', 'https://example.org/configured')]
    assert result['sources'][0]['content'] == '通过所选网页服务读取的项目正文。'


def test_plan_uses_sources_available_evenings_and_all_day_commitments(db, monkeypatch):
    p = project(db)
    monkeypatch.setattr(sources.web, 'fetch_document', lambda url:sources.web.WebDocument('A fetched tutorial with reproducible examples.'))
    src = sources.add_source(db,p.id,'https://example.org/tutorial','学习教程')
    schedule.create_event(db,title='晚间会议',date=date(2026,9,8),start_time='19:00',end_time='20:00')
    schedule.create_event(db,title='全天出行',date=date(2026,9,9))
    plan = service.preview_plan(db,p.id,draft(source_ids=[src.id]),now=NOW)
    assert [(a.date,a.start,a.end) for a in plan.assignments] == [
        ('2026-09-08','20:00','20:45'),('2026-09-10','18:30','19:15'),('2026-09-11','18:30','19:00')]
    assert count(db,Task) == 0 and count(db,Goal) == 0
    assert service.preview_plan(db,p.id,draft(source_ids=[src.id]),now=NOW).id == plan.id
    applied = service.apply_plan(db,plan.id,now=NOW)
    assert applied.state == 'applied' and applied.result['scheduled'] == 3
    assert service.apply_plan(db,plan.id,now=NOW).result == applied.result
    assert count(db,Task) == 3 and count(db,ResearchTask) == 3 and count(db,Goal) == 1
    assert all(t.files[0].id == src.library_file_id for t in db.scalars(select(Task)))
    assert service.detail(db,p.id).project.total_tasks == 3


def test_changed_calendar_or_elapsed_slot_rejects_stale_preview(db):
    p = project(db)
    plan = service.preview_plan(db,p.id,draft(),now=NOW)
    schedule.create_event(db,title='临时新增',date=date(2026,9,8),start_time='18:30',end_time='20:00')
    with pytest.raises(service.ResearchConflict, match='日历'):
        service.apply_plan(db,plan.id,now=NOW)
    assert service.get_project(db,p.id).version == 1 and count(db,Task) == 0
    refreshed = service.preview_plan(db,p.id,draft(),now=NOW)
    assert refreshed.id != plan.id
    with pytest.raises(service.ResearchConflict, match='已经开始'):
        service.apply_plan(db,refreshed.id,now=datetime(2026,9,8,20,1))
    assert count(db,Task) == 0


def test_target_creation_failure_rolls_back_whole_project_plan(db, monkeypatch):
    p = project(db)
    plan = service.preview_plan(db,p.id,draft(),now=NOW)
    original = tasks.create_task
    calls = 0
    def fail(*args, **kwargs):
        nonlocal calls
        row = original(*args, **kwargs)
        calls += 1
        if calls == 2:
            raise RuntimeError('interrupted')
        return row
    monkeypatch.setattr(tasks,'create_task',fail)
    with pytest.raises(RuntimeError):
        service.apply_plan(db,plan.id,now=NOW)
    assert all(count(db,model) == 0 for model in (Task,ResearchTask,TaskScheduleEntry,Goal,KeyResult))
    assert service.get_project(db,p.id).version == 1
    assert service.get_plan(db,plan.id).state == 'draft'
    monkeypatch.setattr(tasks,'create_task',original)
    assert service.apply_plan(db,plan.id,now=NOW).result['scheduled'] == 3


def test_concurrent_apply_commits_one_project_task_set(db):
    p = project(db)
    plan = service.preview_plan(db,p.id,draft(),now=NOW)
    factory = sessionmaker(bind=db.get_bind(),expire_on_commit=False)
    def apply(_):
        with factory() as session:
            return service.apply_plan(session,plan.id,now=NOW).result['task_ids']
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(apply,range(8)))
    assert all(ids == results[0] for ids in results)
    assert count(db,Task) == 3 and count(db,Goal) == 1 and count(db,TaskScheduleEntry) == 3


def test_replan_preserves_progress_and_manual_edits_outside_new_window(db):
    p = project(db)
    initial = service.apply_plan(db,service.preview_plan(db,p.id,draft(),now=NOW).id,now=NOW)
    completed, manual, pending = initial.result['task_ids']
    with freeze_time(NOW):
        tasks.update_task(db,completed,status='done')
    old_manual = db.scalar(select(TaskScheduleEntry).where(TaskScheduleEntry.task_id == manual))
    old_manual.date, old_manual.start_time, old_manual.end_time = date(2026,9,17),'08:00','08:45'
    db.commit()
    current = service.get_project(db,p.id)
    spec = service.spec_of(current).model_copy(update={'start_date':date(2026,9,15),'end_date':date(2026,9,20)})
    updated = service.update_project(db,p.id,ProjectUpdate(version=current.version,spec=spec))
    plan = service.preview_replan(db,p.id,updated.version,now=NOW)
    assert [u.existing_task_id for u in plan.units] == [pending]
    assert {r['task_id'] for r in plan.preserved} == {completed,manual}
    applied = service.apply_plan(db,plan.id,now=NOW)
    assert applied.result['task_ids'] == [pending] and count(db,Task) == 3
    manual_slot = db.scalar(select(TaskScheduleEntry).where(TaskScheduleEntry.task_id == manual))
    assert str(manual_slot.date) == '2026-09-17' and manual_slot.start_time == '08:00'
    pending_slots = list(db.scalars(select(TaskScheduleEntry).where(TaskScheduleEntry.task_id == pending)))
    # The preserved 45-minute session also consumes this project's daily 60-minute budget.
    assert len(pending_slots) == 1 and str(pending_slots[0].date) == '2026-09-18'
    assert service.detail(db,p.id).project.completed_tasks == 1


def test_local_material_dedup_and_cross_project_sources_are_validated(db,tmp_path):
    from zhishi.domain.library import service as library
    p = project(db)
    root = tmp_path/'attachments'
    one = library.save_upload(db,storage_root=root,upload=UploadFile(filename='guide.txt',file=BytesIO(b'Learn a little, practice a little.')))
    two = library.save_upload(db,storage_root=root,upload=UploadFile(filename='renamed.txt',file=BytesIO(b'Learn a little, practice a little.')))
    first = sources.attach_material(db,p.id,one.id,root)
    assert first.id == sources.attach_material(db,p.id,two.id,root).id and first.kind == 'file'
    another = project(db)
    with pytest.raises(service.ResearchConflict,match='本项目'):
        service.preview_plan(db,another.id,draft(source_ids=[first.id]),now=NOW)


def test_private_url_fails_without_library_import_and_missing_tasks_not_recreated(db):
    p = project(db)
    source = sources.add_source(db,p.id,'http://127.0.0.1/private')
    assert source.status == 'failed' and count(db,LibraryFile) == 0
    initial = service.apply_plan(db,service.preview_plan(db,p.id,draft(),now=NOW).id,now=NOW)
    row = db.get(Task,initial.result['task_ids'][0])
    row.deleted_at = NOW
    db.commit()
    plan = service.preview_replan(db,p.id,service.get_project(db,p.id).version,now=NOW)
    assert row.id not in [u.existing_task_id for u in plan.units]
    service.apply_plan(db,plan.id,now=NOW)
    assert count(db,Task) == 3 and service.detail(db,p.id).project.missing_tasks == 1


def test_project_defaults_and_repeat_request_are_explicit(db):
    with freeze_time(NOW):
        payload = ProjectCreate(title='从零学画画',objective='画出一张静物速写',request_key='same-request')
        p = service.create_project(db,payload)
        assert len(p.assumptions) >= 4
        assert service.create_project(db,payload).id == p.id
        assert planning.end_date(p.spec) == date(2026,9,21)
