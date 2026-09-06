"""Opt-in, bounded recurring public research; every attempt has a durable outcome."""
# ruff: noqa: DTZ005 -- v2 schedules use host local wall time.
from __future__ import annotations

import json
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from zhishi.adapters import web_services
from zhishi.domain.models import NotificationLog, ResearchProject, ResearchWatch, ResearchWatchRun
from zhishi.domain.research import planning, service, sources
from zhishi.domain.research.watch_schemas import WatchConfig, WatchRead, WatchRunRead, WatchUpdate


def next_time(config: WatchConfig, now: datetime) -> datetime:
    hour, minute = map(int, config.time.split(':'))
    due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if config.frequency == 'weekly':
        due += timedelta(days=(config.weekday - due.weekday()) % 7)
    if due <= now:
        due += timedelta(days=7 if config.frequency == 'weekly' else 1)
    return due


def run_read(row: ResearchWatchRun) -> WatchRunRead:
    return WatchRunRead(id=row.id, project_id=row.project_id, status=row.status,
        config=WatchConfig.model_validate_json(row.config_json),
        sources=json.loads(row.sources_json), errors=json.loads(row.errors_json),
        started_at=row.started_at, finished_at=row.finished_at)


def read(db: Session, project_id: int, before: int | None = None) -> WatchRead:
    project = service.get_project(db, project_id)
    watch = db.get(ResearchWatch, project_id, populate_existing=True)
    query = select(ResearchWatchRun).where(ResearchWatchRun.project_id == project_id)
    if before is not None:
        query = query.where(ResearchWatchRun.id < before)
    rows = db.scalars(query.order_by(ResearchWatchRun.id.desc()).limit(21)).all()
    return WatchRead(project_id=project_id, version=watch.version if watch else 0,
        config=WatchConfig.model_validate_json(watch.config_json) if watch else WatchConfig(),
        next_run_at=watch.next_run_at if watch else None, running=bool(watch and watch.active_token),
        project_active=project.status == 'active', runs=[run_read(r) for r in rows[:20]],
        next_before=rows[19].id if len(rows) > 20 else None)


def configure(db: Session, project_id: int, payload: WatchUpdate) -> WatchRead:
    service.get_project(db, project_id, active=payload.enabled)
    config = WatchConfig.model_validate(payload.model_dump(exclude={'version'}))
    db.execute(insert(ResearchWatch).values(project_id=project_id).on_conflict_do_nothing())
    result = db.execute(update(ResearchWatch).where(ResearchWatch.project_id == project_id,
        ResearchWatch.version == payload.version).values(enabled=config.enabled,
        version=payload.version+1, config_json=config.model_dump_json(), last_error_key='',
        next_run_at=next_time(config, datetime.now()) if config.enabled else None))
    if result.rowcount != 1:
        db.rollback()
        raise service.ResearchConflict('资料跟进设置已变化，请刷新后重试', project_id)
    db.commit()
    return read(db, project_id)


class WatchStopped(Exception):
    pass


def _check(db: Session, project_id: int, token: str, version: int) -> None:
    db.commit()
    result = db.execute(update(ResearchWatch).where(ResearchWatch.project_id == project_id,
        ResearchWatch.active_token == token, ResearchWatch.version == version,
        ResearchWatch.enabled.is_(True), ResearchWatch.project_id.in_(
            select(ResearchProject.id).where(ResearchProject.status == 'active'))
        ).values(heartbeat_at=datetime.now()))
    db.commit()
    if result.rowcount != 1:
        raise WatchStopped


def _notify(db: Session, watch: ResearchWatch, row: ResearchWatchRun, changed: int, errors: list[str]) -> None:
    error_key = planning.fingerprint(sorted(set(errors))) if errors else ''
    should_notify = changed or (error_key and error_key != watch.last_error_key)
    watch.last_error_key = error_key
    if not should_notify:
        return
    project = service.get_project(db, watch.project_id)
    body = f'已保存 {changed} 份新增或更新资料。' if changed else '本次资料检索需要处理。'
    if errors:
        body += f'有 {len(errors)} 项未完成，可在项目中查看原因并重试。'
    db.add(NotificationLog(kind='research_watch', title=f'「{project.title}」资料跟进',
        body=body, remind_at=datetime.now(), dedupe_key=f'research-watch:{row.id}',
        target_path=f'/research?project={project.id}'))


def recover_stale(db: Session) -> None:
    """No second worker may overlap an active network call; leases exceed adapter timeouts."""
    cutoff = datetime.now() - timedelta(minutes=20)
    watches = db.scalars(select(ResearchWatch).where(ResearchWatch.active_token.is_not(None),
        ResearchWatch.heartbeat_at < cutoff)).all()
    for watch in watches:
        token = watch.active_token
        result = db.execute(update(ResearchWatch).where(ResearchWatch.project_id == watch.project_id,
            ResearchWatch.active_token == token, ResearchWatch.heartbeat_at < cutoff).values(
                active_token=None, heartbeat_at=None, next_run_at=datetime.now() if watch.enabled else None))
        if result.rowcount != 1:
            db.rollback()
            continue
        row = db.scalar(select(ResearchWatchRun).where(ResearchWatchRun.token == token))
        if row and row.status == 'running':
            row.status, row.finished_at = 'interrupted', datetime.now()
            row.errors_json = json.dumps(['上次执行中断，已保存的资料保留；将补做一次检查。'], ensure_ascii=False)
        db.commit()


def execute(db: Session, project_id: int, *, scheduled: bool = False) -> WatchRunRead | None:
    service.get_project(db, project_id, active=True)
    recover_stale(db)
    watch = db.get(ResearchWatch, project_id, populate_existing=True)
    if not watch or not watch.enabled:
        if scheduled:
            return None
        raise ValueError('请先保存并开启此项目的定期资料检索')
    config, version, now = WatchConfig.model_validate_json(watch.config_json), watch.version, datetime.now()
    token = str(uuid4())
    claim = update(ResearchWatch).where(ResearchWatch.project_id == project_id,
        ResearchWatch.version == version, ResearchWatch.enabled.is_(True), ResearchWatch.active_token.is_(None))
    if scheduled:
        claim = claim.where(ResearchWatch.next_run_at <= now)
    result = db.execute(claim.values(active_token=token, heartbeat_at=now, next_run_at=next_time(config, now)))
    if result.rowcount != 1:
        db.rollback()
        if scheduled:
            return None
        raise service.ResearchConflict('此项目已有一次资料检索正在执行', project_id)
    row = ResearchWatchRun(project_id=project_id, token=token, config_json=config.model_dump_json(), started_at=now)
    db.add(row)
    db.commit()
    results, errors, seen = [], [], set()
    status = 'unchanged'
    try:
        for query in config.queries:
            _check(db, project_id, token, version)
            hits = web_services.search(db, query, limit=6)
            _check(db, project_id, token, version)
            for hit in hits:
                if hit.get('error'):
                    errors.append(str(hit['error'])[:500])
                    continue
                try:
                    url = sources.canonical_url(hit.get('url', ''))
                    if url in seen:
                        continue
                    seen.add(url)
                    _check(db, project_id, token, version)
                    source = sources.register_source(db, project_id, url, hit.get('title', ''),
                        query=query, description=hit.get('description', ''))
                    prior = (source.id, source.library_file_id) if source.status == 'verified' else None
                    saved = sources.fetch_source(db, project_id, source.id, refresh=config.refresh_existing)
                    changed = saved.status == 'verified' and (saved.id, saved.library_file_id) != prior
                    results.append({'source_id':saved.id, 'title':saved.title, 'url':saved.url,
                        'library_file_id':saved.library_file_id,
                        'changed':changed, 'status':saved.status, 'error':saved.error})
                    if saved.error:
                        errors.append(saved.error)
                    row.sources_json = json.dumps(results, ensure_ascii=False)
                    row.errors_json = json.dumps(errors, ensure_ascii=False)
                    db.commit()
                    _check(db, project_id, token, version)
                except (ValueError, LookupError) as exc:
                    errors.append(str(exc)[:500])
                if len(seen) >= config.max_sources:
                    break
            if len(seen) >= config.max_sources:
                break
        if not results and not errors:
            errors.append('未找到资料，可调整公开主题检索词后重试。')
        status = 'partial' if errors and any(r['status'] == 'verified' for r in results) else (
            'failed' if errors else 'updated' if any(r['changed'] for r in results) else 'unchanged')
    except WatchStopped:
        status = 'stopped'
        errors.append('设置或项目状态已变化，后续检索已停止；本次已取得的资料保留。')
    except Exception:  # noqa: BLE001 — never persist unredacted transport/config exceptions
        db.rollback()
        status = 'failed'
        errors.append('资料检索执行失败，已保存的资料保留；请检查网页服务设置后重试。')
    # Finalize only while still owning the lease, without overwriting concurrent settings edits.
    done = db.execute(update(ResearchWatch).where(ResearchWatch.project_id == project_id,
        ResearchWatch.active_token == token).values(active_token=None, heartbeat_at=None))
    if done.rowcount == 1:
        row.status, row.finished_at = status, datetime.now()
        row.sources_json, row.errors_json = json.dumps(results, ensure_ascii=False), json.dumps(errors, ensure_ascii=False)
        watch = db.get(ResearchWatch, project_id, populate_existing=True)
        if watch.version == version and status != 'stopped':
            _notify(db, watch, row, sum(r['changed'] for r in results), errors)
        db.commit()
    else:
        db.rollback()
        db.refresh(row)
    return run_read(row)


def scan(db: Session) -> None:
    recover_stale(db)
    ids = list(db.scalars(select(ResearchWatch.project_id).join(ResearchProject).where(
        ResearchWatch.enabled.is_(True), ResearchWatch.next_run_at <= datetime.now(),
        ResearchWatch.active_token.is_(None), ResearchProject.status == 'active')
        .order_by(ResearchWatch.next_run_at).limit(10)))
    db.commit()
    for project_id in ids:
        try:
            execute(db, project_id, scheduled=True)
        except (ValueError, LookupError):
            db.rollback()  # project may have been archived after selection
