# ruff: noqa: DTZ001, DTZ005 -- v2 schedules use local wall time.
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Event
import json

import pytest
from freezegun import freeze_time
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from zhishi.adapters.web import WebDocument
from zhishi.domain.models import NotificationLog, ResearchWatch, ResearchWatchRun, Task
from zhishi.domain.research import service, watches
from zhishi.domain.research.schemas import ProjectCreate
from zhishi.domain.research.watch_schemas import WatchConfig, WatchUpdate


def setup(db, monkeypatch, **kwargs):
    p = service.create_project(db, ProjectCreate(title='教程', objective='PRIVATE_GOAL', background='PRIVATE_BACKGROUND'))
    calls = []
    def search(session, query, limit):
        calls.append(query)
        return [{'url':'https://example.org/tutorial', 'title':'公开教程'}]
    monkeypatch.setattr(watches.web_services, 'search', search)
    monkeypatch.setattr(watches.web_services, 'fetch_document', lambda *a: WebDocument('真实正文' * 3000))
    watches.configure(db, p.id, WatchUpdate(version=0, enabled=True, queries=['公开主题'], **kwargs))
    return p, calls


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


@freeze_time('2032-01-05 08:00:00')
def test_schedule_catchup_dedup_snapshots_failure_recovery(db, monkeypatch):
    p, calls = setup(db, monkeypatch, frequency='daily')
    assert watches.read(db, p.id).next_run_at == datetime(2032, 1, 5, 9)
    watches.scan(db)
    assert not calls
    with freeze_time('2032-01-12 10:00:00'):
        watches.scan(db)
        watches.scan(db)
        assert calls == ['公开主题']  # one catchup, never a week of backlog
        state = watches.read(db, p.id)
        assert state.next_run_at == datetime(2032, 1, 13, 9)
        assert state.runs[0].status == 'updated'
        assert count(db, NotificationLog) == 1
        assert watches.execute(db, p.id).status == 'unchanged'
        assert count(db, NotificationLog) == 1
        old = service.detail(db, p.id).sources[0]
        monkeypatch.setattr(watches.web_services, 'fetch_document', lambda *a: WebDocument('更新正文' * 3000))
        run = watches.execute(db, p.id)
        assert run.status == 'updated' and run.sources[0].source_id != old.id
        assert count(db, NotificationLog) == 2
        def fail(*args):
            raise ValueError('临时网络故障')
        monkeypatch.setattr(watches.web_services, 'fetch_document', fail)
        assert watches.execute(db, p.id).status == 'partial'
        assert count(db, NotificationLog) == 3
        watches.execute(db, p.id)
        assert count(db, NotificationLog) == 3
        monkeypatch.setattr(watches.web_services, 'fetch_document', lambda *a: WebDocument('更新正文' * 3000))
        assert watches.execute(db, p.id).status == 'unchanged'
        assert count(db, NotificationLog) == 3
        assert count(db, Task) == 0
        detail = service.detail(db, p.id)
        assert len(detail.sources) == 2 and detail.project.verified_sources == 1


def test_config_validation_weekly_conflict_and_disabled_default(db):
    p = service.create_project(db, ProjectCreate(title='主题', objective='目标'))
    assert not watches.read(db, p.id).config.enabled
    with pytest.raises(ValueError, match='开启'):
        watches.execute(db, p.id)
    for fields in ({'queries':[]}, {'queries':['x'*501]}, {'queries':['x'], 'time':'24:00'},
                   {'queries':['x'], 'max_sources':7}, {'queries':['x'], 'weekday':7}):
        with pytest.raises(ValueError):
            WatchUpdate(version=0, enabled=True, **fields)
    settings = WatchUpdate(version=0, enabled=True, queries=['主题',' 主题 '])
    saved = watches.configure(db, p.id, settings)
    assert saved.version == 1 and saved.config.queries == ['主题']
    with pytest.raises(service.ResearchConflict):
        watches.configure(db, p.id, settings)
    assert watches.read(db, p.id).version == 1
    config = WatchConfig(queries=['主题'], frequency='weekly', weekday=0)
    assert watches.next_time(config, datetime(2032,1,5,9)) == datetime(2032,1,12,9)


@freeze_time('2032-01-05 10:00:00')
def test_concurrent_run_pause_and_archive_stop_subsequent_requests(db, monkeypatch):
    p, _ = setup(db, monkeypatch)
    started, release = Event(), Event()
    requests = []
    def search(*args, **kwargs):
        started.set()
        assert release.wait(5)
        return [{'url':'https://example.org/one'}]
    monkeypatch.setattr(watches.web_services, 'search', search)
    monkeypatch.setattr(watches.web_services, 'fetch_document', lambda *a: requests.append(a))
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    def run():
        with factory() as session:
            return watches.execute(session, p.id)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run)
        assert started.wait(5)
        with pytest.raises(service.ResearchConflict):
            watches.execute(db, p.id)
        watches.configure(db, p.id, WatchUpdate(version=1, enabled=False))
        release.set()
        assert future.result(5).status == 'stopped'
    assert not requests and count(db, NotificationLog) == 0
    assert not watches.read(db, p.id).running
    service.archive_project(db, p.id, p.version, True)
    with pytest.raises(ValueError):
        watches.configure(db, p.id, WatchUpdate(version=2, enabled=True, queries=['主题']))
    watches.scan(db)
    assert count(db, ResearchWatchRun) == 1


@freeze_time('2032-01-05 10:00:00')
def test_interrupted_lease_recovery_keeps_history_and_retries_once(db, monkeypatch):
    p, calls = setup(db, monkeypatch)
    watch = db.get(ResearchWatch, p.id)
    watch.active_token, watch.heartbeat_at = 'interrupted-token', datetime.now() - timedelta(minutes=21)
    row = ResearchWatchRun(project_id=p.id, token=watch.active_token, config_json=watch.config_json)
    db.add(row)
    db.commit()
    watches.scan(db)
    watches.scan(db)
    assert calls == ['公开主题']
    db.refresh(row)
    assert row.status == 'interrupted'
    assert [r.status for r in watches.read(db, p.id).runs] == ['updated','interrupted']


def test_bounded_partial_results_and_no_secret_context_sent(db, monkeypatch):
    p, calls = setup(db, monkeypatch, max_sources=2)
    def search(session, query, limit):
        calls.append(query)
        return [{'url':f'https://example.org/{i}', 'title':f'资料{i}'} for i in range(6)]
    def fetch(session, url):
        if url.endswith('/1'):
            raise ValueError('读取失败')
        return WebDocument('正文')
    monkeypatch.setattr(watches.web_services, 'search', search)
    monkeypatch.setattr(watches.web_services, 'fetch_document', fetch)
    row = watches.execute(db, p.id)
    assert row.status == 'partial' and len(row.sources) == 2
    assert calls == ['公开主题']
    assert row.sources[0].changed and not row.sources[1].changed
    assert 'PRIVATE' not in row.model_dump_json()


def test_disable_during_fetch_preserves_returned_material_and_stops_rest(db, monkeypatch):
    p, _ = setup(db, monkeypatch)
    monkeypatch.setattr(watches.web_services, 'search', lambda *a, **k:[
        {'url':'https://example.org/one'}, {'url':'https://example.org/two'}])
    calls = []
    def fetch(session, url):
        calls.append(url)
        watches.configure(db, p.id, WatchUpdate(version=1, enabled=False))
        return WebDocument('本次已取得的正文')
    monkeypatch.setattr(watches.web_services, 'fetch_document', fetch)
    row = watches.execute(db, p.id)
    assert row.status == 'stopped' and len(row.sources) == 1
    assert len(calls) == 1 and service.detail(db, p.id).project.verified_sources == 1
    assert not watches.read(db, p.id).config.enabled


def test_model_history_paginates_without_skipping_and_configuration_requires_permission(db, monkeypatch):
    from zhishi.agent.permissions import classify
    from zhishi.agent.tools.research_tools import configure_research_watch, get_research_watch
    p, _ = setup(db, monkeypatch)
    for _ in range(5):
        watches.execute(db, p.id)
    ids, before = [], None
    while True:
        page = json.loads(get_research_watch(db, p.id, before))
        assert len(page['runs']) <= 2
        ids.extend(row['id'] for row in page['runs'])
        assert all('url' not in source for run in page['runs'] for source in run['sources'])
        if not page['next_call']:
            break
        before = page['next_call']['args']['before']
    assert ids == [r.id for r in watches.read(db, p.id).runs]
    assert len(set(ids)) == 5
    assert classify(db,'get_research_watch',{'project_id':p.id}) == 'allow'
    assert classify(db,'configure_research_watch',{'project_id':p.id}) == 'confirm'
    saved = json.loads(configure_research_watch(db, p.id, WatchUpdate(version=1, enabled=False)))
    assert saved['version'] == 2 and not saved['config']['enabled'] and len(saved['runs']) == 2
