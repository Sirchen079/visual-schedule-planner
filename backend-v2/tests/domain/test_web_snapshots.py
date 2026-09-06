# ruff: noqa: DTZ001 -- research schedules use local calendar time.
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from threading import Barrier

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from zhishi.adapters.web import WebDocument
from zhishi.domain.library import reading
from zhishi.domain.models import LibraryFile, ResearchSource, Task
from zhishi.domain.research import service, sources
from zhishi.domain.research.schemas import PlanDraft, ProjectCreate


def create(db):
    return service.create_project(db, ProjectCreate(title='学习专题', objective='读完整教程并完成练习',
        start_date=date(2032, 1, 1), end_date=date(2032, 1, 14)))


def test_web_tail_search_citation_refresh_and_old_plan_apply(db, tmp_path, monkeypatch):
    project = create(db)
    body = '基础概念与示例。' * 7000 + '最后练习：独立解释每个步骤。'
    monkeypatch.setattr(sources.web_services, 'fetch_document', lambda *a: WebDocument(body))
    src = sources.add_source(db, project.id, 'https://example.org/guide')
    assert len(src.content) == 8000 and '最后练习' not in src.content
    assert src.document.indexed_chars == len(body) and not src.document.partial
    hit = reading.search(db, '最后练习', tmp_path, project_id=project.id)['hits'][0]
    part = reading.read(db, src.library_file_id, tmp_path, part=hit['part'], revision=hit['revision'])
    assert '独立解释每个步骤' in part['parts'][0]['text']
    old_file = db.get(LibraryFile, src.library_file_id)
    old_cache = old_file.extracted_text
    old_file.notes = '用户保留的学习笔记'
    db.commit()
    plan = service.preview_plan(db, project.id, PlanDraft(version=1, rationale='按末尾练习检查理解', steps=[{
        'title':'完成最后练习', 'outcome':'独立解释步骤', 'minutes':30,
        'source_refs':[{'source_id':src.id,'part':hit['part'],'revision':hit['revision'],'quote':'独立解释每个步骤'}]}]),
        now=datetime(2032, 1, 1, 8))
    monkeypatch.setattr(sources.web_services, 'fetch_document', lambda *a: WebDocument(body + '新增复盘要求。'))
    newer = sources.add_source(db, project.id, src.url, refresh=True)
    assert newer.id != src.id and newer.library_file_id != src.library_file_id
    assert service.source_read(db, db.get(ResearchSource, src.id)).superseded_by == newer.id
    assert old_file.extracted_text == old_cache and old_file.notes == '用户保留的学习笔记'
    applied = service.apply_plan(db, plan.id, now=datetime(2032, 1, 1, 8))
    assert applied.state == 'applied'
    task = db.scalar(select(Task))
    assert src.library_file_id in [f.id for f in task.files]
    assert reading.read(db, src.library_file_id, tmp_path, part=hit['part'], revision=hit['revision']) == part
    assert sources.add_source(db, project.id, src.url).id == newer.id
    assert sources.fetch_source(db, project.id, src.id, refresh=True).id == newer.id
    assert db.scalar(select(func.count()).select_from(ResearchSource)) == 2


def test_legacy_excerpt_upgrade_retains_original_and_failed_refresh(db, tmp_path, monkeypatch):
    project = create(db)
    legacy = LibraryFile(original_name='旧网页', storage_path='https://example.org/legacy',
        source_url='https://example.org/legacy', resource_type='link', mime_type='text/uri-list',
        parse_status='parsed', extracted_text=json.dumps({'kind':'text','text':'仅有开头','tables':[]}))
    db.add(legacy)
    db.commit()
    src = sources.register_source(db, project.id, legacy.source_url)
    src.status, src.content, src.library_file_id = 'verified', '仅有开头', legacy.id
    db.commit()
    old = reading.read(db, legacy.id, tmp_path)
    assert old['document']['partial']
    monkeypatch.setattr(sources.web_services, 'fetch_document', lambda *a: WebDocument('完整正文' * 5000))
    updated = sources.fetch_source(db, project.id, src.id, refresh=True)
    assert updated.id != src.id and updated.document.indexed_chars == 20_000
    assert reading.read(db, legacy.id, tmp_path) == old
    def fail(*a):
        raise ValueError('服务暂不可用')
    monkeypatch.setattr(sources.web_services, 'fetch_document', fail)
    retained = sources.fetch_source(db, project.id, updated.id, refresh=True)
    assert retained.status == 'verified' and '已保留原版本' in retained.error
    assert retained.library_file_id == updated.library_file_id


def test_concurrent_refresh_has_one_new_version_and_deleted_snapshot_stays_deleted(db, monkeypatch):
    project = create(db)
    monkeypatch.setattr(sources.web_services, 'fetch_document', lambda *a: WebDocument('第一版'))
    src = sources.add_source(db, project.id, 'https://example.org/shared')
    gate = Barrier(2)
    def fetch(*a):
        gate.wait(timeout=10)
        return WebDocument('第二版')
    monkeypatch.setattr(sources.web_services, 'fetch_document', fetch)
    factory = sessionmaker(db.bind)
    def run():
        with factory() as session:
            return sources.fetch_source(session, project.id, src.id, refresh=True)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert results[0].id == results[1].id != src.id
    db.expire_all()
    file = db.get(LibraryFile, results[0].library_file_id)
    file.deleted_at = datetime(2032, 1, 2)
    db.commit()
    monkeypatch.setattr(sources.web_services, 'fetch_document', lambda *a: WebDocument('第二版'))
    result = sources.fetch_source(db, project.id, results[0].id, refresh=True)
    assert result.library_state == 'deleted' and result.document is None
    assert db.scalar(select(func.count()).select_from(ResearchSource)) == 2
    assert db.scalar(select(func.count()).select_from(LibraryFile)) == 2
