"""Persistent, evidence-based project followups; no model call is needed to notice drift."""
# ruff: noqa: DTZ005 -- v2 stores local wall time.
from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from zhishi.domain import settingsvc
from zhishi.domain.models import NotificationLog, ResearchPlan, ResearchProject, SecretaryFollowup
from zhishi.domain.research import planning, service


class FollowupConflict(ValueError):
    def __init__(self, message: str, followup_id: int):
        super().__init__(message)
        self.followup_id = followup_id


def get(db: Session, followup_id: int) -> SecretaryFollowup:
    row = db.get(SecretaryFollowup, followup_id, populate_existing=True)
    if row is None:
        raise LookupError('跟进记录不存在')
    return row


def to_read(db: Session, row: SecretaryFollowup, *, include_plan: bool = False):
    from zhishi.domain.followup_schemas import FollowupRead
    plan = service.plan_read(service.get_plan(db, row.plan_id)) if include_plan and row.plan_id else None
    return FollowupRead(**{key:getattr(row,key) for key in (
        'id','project_id','kind','title','body','status','version','plan_id','snoozed_until',
        'error','created_at','updated_at')}, target_path=f'/research?project={row.project_id}&followup={row.id}', plan=plan)


def _review_evidence(project: ResearchProject, feedback_ids: list[int]) -> dict | None:
    if not feedback_ids:
        return None
    return {'kind':'needs_review', 'feedback_ids':feedback_ids,
            'title':f'「{project.title}」有待回应的学习反馈',
            'body':f'你记录了 {len(feedback_ids)} 条偏难或偏易的感受。可以结合原目标补充巩固练习或下一阶段内容。'}


def observe(db: Session, project_id: int, now: datetime) -> dict | None:
    project = service.get_project(db, project_id)
    if project.status != 'active':
        return None
    from zhishi.domain.research.feedback import pending_difficulties
    feedback_ids = pending_difficulties(db, project_id)
    spec = service.spec_of(project)
    state = planning.calendar_state(db, project_id, spec, now)
    members = state['members']
    remaining = [m for m in members if m['status'] in ('todo', 'doing')]
    if members and not remaining:
        if all(m['status'] == 'done' for m in members):
            return _review_evidence(project, feedback_ids) or {'kind':'completed', 'tasks':[m['task_id'] for m in members],
                    'title':f'「{project.title}」本阶段已完成',
                    'body':'本阶段所有任务均已完成。可以回顾成果，并告诉知时下一阶段想深入的内容。'}
        return None
    if not members:
        if now.date() >= spec.start_date and project.created_at + timedelta(days=1) <= now:
            return {'kind':'needs_plan', 'tasks':[], 'title':f'「{project.title}」还没有落实计划',
                    'body':'项目目标已保留，但还没有实际任务。可继续补充资料、拟定步骤并安排第一段时间。'}
        return None
    if planning.end_date(spec) < now.date():
        return {'kind':'needs_window', 'tasks':[m['task_id'] for m in remaining],
                'end':str(planning.end_date(spec)), 'title':f'「{project.title}」需要新的可用时间',
                'body':f'原规划窗口已结束，还有 {len(remaining)} 项未完成。请调整截止日或可用时间，再继续重排。'}
    missed, unscheduled, conflicts, missed_slots = [], [], [], []
    future = [e for e in state['entries'] if e['date'] > str(now.date()) or
              (e['date'] == str(now.date()) and (not e['end'] or e['end'] > now.strftime('%H:%M')))]
    for member in remaining:
        if member['status'] != 'todo':
            continue
        tid = member['task_id']
        own = [e for e in future if e['task_id'] == tid]
        if not own:
            historic = [e for e in state['entries'] if e['task_id'] == tid]
            (missed if historic else unscheduled).append(tid)
            if historic:
                latest = max(historic, key=lambda e:(e['date'],e['end'] or '',e['id']))
                missed_slots.append({'task':tid,'slot':latest['id'],'date':latest['date'],'end':latest['end']})
        for slot in own:
            if not slot['start'] or not slot['end']:
                continue
            for event in state['events']:
                if event['date'] == slot['date'] and (not event['start_time'] or not event['end_time'] or
                    slot['start'] < event['end_time'] and event['start_time'] < slot['end']):
                    conflicts.append({'task':tid, 'slot':slot['id'], 'event':event['event_id'], 'date':slot['date']})
            for other in future:
                if other['task_id'] != tid and other['date'] == slot['date'] and other['start'] and other['end'] and \
                        slot['start'] < other['end'] and other['start'] < slot['end']:
                    conflicts.append({'task':tid, 'slot':slot['id'], 'other_slot':other['id']})
    if not (missed or unscheduled or conflicts):
        return _review_evidence(project, feedback_ids)
    summary = []
    if missed:
        summary.append(f'{len(missed)} 项错过原定时间')
    if unscheduled:
        summary.append(f'{len(unscheduled)} 项尚未安排时间')
    if conflicts:
        summary.append(f'{len({c["task"] for c in conflicts})} 项与已有安排冲突')
    return {'kind':'replan', 'missed':missed, 'missed_slots':missed_slots,
            'unscheduled':unscheduled, 'conflicts':conflicts,
            'timing':{k:v for k,v in spec.model_dump(mode='json').items() if k not in ('title','objective','background','kind')},
            'title':f'「{project.title}」需要调整安排',
            'body':'，'.join(summary)+'。知时会保留完成记录和人工调整，准备新的时间安排。'}


def evidence_key(project_id: int, evidence: dict) -> str:
    facts = {k:v for k,v in evidence.items() if k not in ('title','body')}
    return f'research:{project_id}:' + planning.fingerprint(facts)


def _resolve_others(db: Session, project_id: int, current_key: str | None, now: datetime) -> None:
    rows = db.scalars(select(SecretaryFollowup).where(SecretaryFollowup.project_id == project_id,
        SecretaryFollowup.status.in_(('pending','snoozed','applying','waiting')))).all()
    for row in rows:
        if row.evidence_key == current_key:
            continue
        plan = db.get(ResearchPlan, row.plan_id) if row.plan_id else None
        changed = db.execute(update(SecretaryFollowup).where(SecretaryFollowup.id == row.id,
            SecretaryFollowup.version == row.version,
            SecretaryFollowup.status.in_(('pending','snoozed','applying','waiting'))).values(
                status='applied' if plan and plan.state == 'applied' else 'resolved',
                version=row.version+1, updated_at=now))
        if changed.rowcount != 1:
            continue
        if row.notification_id:
            notification = db.get(NotificationLog, row.notification_id)
            if notification and notification.read_at is None:
                notification.read_at = now
    db.commit()


def _notify(db: Session, row: SecretaryFollowup, now: datetime) -> None:
    claimed = db.execute(update(SecretaryFollowup).where(SecretaryFollowup.id == row.id,
        SecretaryFollowup.version == row.version, SecretaryFollowup.notification_id.is_(None),
        SecretaryFollowup.status.in_(('pending','applied','waiting'))).values(version=row.version+1, updated_at=now))
    if claimed.rowcount != 1:
        db.rollback()
        return
    notification = NotificationLog(kind='followup', title=row.title, body=row.body, remind_at=now,
        target_path=f'/research?project={row.project_id}&followup={row.id}')
    db.add(notification)
    db.flush()
    row.notification_id = notification.id
    db.commit()


def _prepare(db: Session, row: SecretaryFollowup, now: datetime) -> SecretaryFollowup:
    if row.kind != 'replan' or row.status != 'pending':
        return row
    project = service.get_project(db, row.project_id, active=True)
    plan = db.get(ResearchPlan, row.plan_id, populate_existing=True) if row.plan_id else None
    if plan and plan.state == 'applied':
        row.status = 'waiting'
        row.version += 1
        row.updated_at = now
        db.commit()
        return row
    # Refresh a preview only if its calendar evidence has actually changed.
    state = planning.calendar_state(db, project.id, service.spec_of(project), now)
    stale = not plan or plan.project_version != project.version or plan.calendar_fingerprint != planning.fingerprint(state)
    if plan and not stale:
        stale = any(datetime.fromisoformat(a['date']+'T'+a['start']) < now for a in json.loads(plan.assignments_json))
    if stale:
        version = row.version
        prepared = service.preview_replan(db, project.id, project.version, now=now)
        changed = db.execute(update(SecretaryFollowup).where(SecretaryFollowup.id == row.id,
            SecretaryFollowup.version == version, SecretaryFollowup.status == 'pending').values(
                plan_id=prepared.id, version=version+1, updated_at=now, error=''))
        db.commit()
        row = get(db, row.id)
        if changed.rowcount != 1:
            return row
    return row


def check_project(db: Session, project_id: int, *, now: datetime | None = None) -> SecretaryFollowup | None:
    now = now or datetime.now()
    # A process can stop after the calendar transaction commits but before its receipt.
    interrupted = db.scalars(select(SecretaryFollowup).where(
        SecretaryFollowup.project_id == project_id, SecretaryFollowup.status == 'applying')).all()
    for item in interrupted:
        if item.plan_id and service.get_plan(db, item.plan_id).state == 'applied':
            recovered = _finish_apply(db, item.id, now)
            _notify(db, recovered, now)
    evidence = observe(db, project_id, now)
    key = evidence_key(project_id, evidence) if evidence else None
    _resolve_others(db, project_id, key, now)
    if not evidence:
        return None
    db.execute(insert(SecretaryFollowup).values(evidence_key=key, project_id=project_id,
        kind=evidence['kind'], title=evidence['title'][:200], body=evidence['body'],
        evidence_json=planning.encoded(evidence), created_at=now, updated_at=now)
        .on_conflict_do_nothing(index_elements=['evidence_key']))
    db.commit()
    row = db.scalar(select(SecretaryFollowup).where(SecretaryFollowup.evidence_key == key))
    if row.status == 'resolved':
        db.execute(update(SecretaryFollowup).where(SecretaryFollowup.id == row.id,
            SecretaryFollowup.version == row.version, SecretaryFollowup.status == 'resolved').values(
                status='pending', plan_id=None, notification_id=None, error='',
                version=row.version+1, updated_at=now))
        db.commit()
        row = get(db,row.id)
    if row.status == 'waiting':
        recorded = json.loads(row.evidence_json)
        project = service.get_project(db, project_id)
        current = planning.fingerprint(planning.calendar_state(db, project_id, service.spec_of(project), now))
        if recorded.get('_wait_calendar') and recorded['_wait_calendar'] != current:
            db.execute(update(SecretaryFollowup).where(SecretaryFollowup.id == row.id,
                SecretaryFollowup.version == row.version, SecretaryFollowup.status == 'waiting').values(
                    status='pending', plan_id=None, title=evidence['title'][:200], body=evidence['body'],
                    version=row.version+1, updated_at=now))
            db.commit()
            row = get(db, row.id)
    if row.status == 'snoozed' and row.snoozed_until and row.snoozed_until <= now:
        db.execute(update(SecretaryFollowup).where(SecretaryFollowup.id == row.id,
            SecretaryFollowup.version == row.version, SecretaryFollowup.status == 'snoozed').values(
                status='pending', notification_id=None, snoozed_until=None, version=row.version+1, updated_at=now))
        db.commit()
        row = get(db, row.id)
    if row.status != 'pending':
        return row
    try:
        row = _prepare(db, row, now)
        if (row.status == 'pending' and row.plan_id and
                settingsvc.feature_enabled(db, 'feature_followup_enabled') and
                settingsvc.feature_enabled(db, 'feature_autopilot_enabled')):
            from zhishi.agent.permissions import classify
            plan = service.plan_read(service.get_plan(db, row.plan_id))
            # A partial replan needs a decision about the remaining workload.
            affected = set(evidence.get('missed', []) + evidence.get('unscheduled', []) +
                           [c['task'] for c in evidence.get('conflicts', [])])
            moved = {u.existing_task_id for u in plan.units}
            if affected <= moved and not plan.unassigned and classify(db, 'apply_research_plan', {'plan_id':plan.id}) == 'allow':
                row = apply(db, row.id, row.version, now=now, automatic=True)
    except (ValueError, LookupError) as exc:
        db.rollback()
        row = get(db, row.id)
        row.error = str(exc)[:1000]
        row.updated_at = now
        db.commit()
    _notify(db, row, now)
    return get(db, row.id)


def scan(db: Session, *, now: datetime | None = None) -> dict:
    if not settingsvc.feature_enabled(db, 'feature_followup_enabled'):
        return {'checked':0, 'disabled':True}
    now = now or datetime.now()
    ids = list(db.scalars(select(ResearchProject.id)))
    errors = []
    for project_id in ids:
        try:
            check_project(db, project_id, now=now)
        except Exception as exc:  # noqa: BLE001 -- a single project must not block the next one.
            db.rollback()
            errors.append({'project_id':project_id, 'error':str(exc)[:500]})
    settingsvc.set_setting(db, 'followup_last_scan', planning.encoded({
        'at':now.isoformat(), 'checked':len(ids), 'errors':errors}))
    return {'checked':len(ids), 'disabled':False, 'errors':errors}


def apply(db: Session, followup_id: int, version: int, *, now: datetime | None = None,
          automatic: bool = False) -> SecretaryFollowup:
    now = now or datetime.now()
    row = get(db, followup_id)
    if row.status == 'applied' or (row.plan_id and service.get_plan(db, row.plan_id).state == 'applied'):
        return row
    if row.version != version or row.status != 'pending':
        raise FollowupConflict('跟进记录已变化，请刷新后操作', followup_id)
    evidence = observe(db, row.project_id, now)
    if not evidence or evidence_key(row.project_id, evidence) != row.evidence_key:
        raise FollowupConflict('项目状态已变化，请重新检查后再落实', followup_id)
    if not row.plan_id:
        raise FollowupConflict('这条跟进需要补充目标或可用时间，暂时没有可落实的时间安排', followup_id)
    claimed = db.execute(update(SecretaryFollowup).where(SecretaryFollowup.id == row.id,
        SecretaryFollowup.version == version, SecretaryFollowup.status == 'pending').values(
            status='applying', version=version+1, updated_at=now,
            evidence_json=planning.encoded({**json.loads(row.evidence_json), '_automatic':automatic})))
    if claimed.rowcount != 1:
        db.rollback()
        raise FollowupConflict('跟进记录已变化，请刷新后操作', followup_id)
    try:
        if automatic:
            from zhishi.agent.permissions import classify
            db.expire_all()
            if not settingsvc.feature_enabled(db, 'feature_followup_enabled') or \
                    not settingsvc.feature_enabled(db, 'feature_autopilot_enabled') or \
                    classify(db, 'apply_research_plan', {'plan_id':row.plan_id}) != 'allow':
                raise FollowupConflict('自动调整已暂停，等待现有授权或你的确认', followup_id)
        service.apply_plan(db, row.plan_id, now=now)
    except Exception:
        db.rollback()
        raise
    return _finish_apply(db, row.id, now)


def _finish_apply(db: Session, followup_id: int, now: datetime) -> SecretaryFollowup:
    row = get(db, followup_id)
    if row.status != 'applying':
        return row
    plan = service.plan_read(service.get_plan(db, row.plan_id))
    if plan.state != 'applied':
        return row
    recorded = json.loads(row.evidence_json)
    automatic = recorded.get('_automatic', False)
    remaining = observe(db, row.project_id, now)
    status = 'waiting' if remaining and evidence_key(row.project_id, remaining) == row.evidence_key else 'applied'
    project = service.get_project(db, row.project_id)
    if status == 'waiting':
        recorded['_wait_calendar'] = planning.fingerprint(planning.calendar_state(db, project.id, service.spec_of(project), now))
    changed = db.execute(update(SecretaryFollowup).where(SecretaryFollowup.id == row.id,
        SecretaryFollowup.version == row.version, SecretaryFollowup.status == 'applying').values(
            status=status, version=row.version+1, updated_at=now, error='',
            body=f'已按最新约束调整 {len(plan.assignments)} 项安排，保留 {len(plan.preserved)} 项现状；{len(plan.unassigned)} 项仍未排入。',
            title=f'「{project.title}」已调整学习安排'[:200], evidence_json=planning.encoded(recorded)))
    if changed.rowcount != 1:
        db.rollback()
        return get(db, row.id)
    if row.notification_id:
        notification = db.get(NotificationLog,row.notification_id)
        if notification:
            notification.read_at = now
            if not automatic:
                notification.title, notification.body = row.title, row.body
        if automatic:
            row.notification_id = None
    db.commit()
    return row


def respond(db: Session, followup_id: int, version: int, *, snooze_until: datetime | None = None,
            now: datetime | None = None) -> SecretaryFollowup:
    now = now or datetime.now()
    if snooze_until is not None and snooze_until.tzinfo is not None:
        snooze_until = snooze_until.astimezone().replace(tzinfo=None)
    if snooze_until and (snooze_until <= now or snooze_until > now + timedelta(days=30)):
        raise ValueError('稍后提醒时间须在未来30天以内')
    changed = db.execute(update(SecretaryFollowup).where(SecretaryFollowup.id == followup_id,
        SecretaryFollowup.version == version, SecretaryFollowup.status.in_(('pending','snoozed','waiting'))).values(
            status='snoozed' if snooze_until else 'dismissed', snoozed_until=snooze_until,
            version=version+1, updated_at=now))
    if changed.rowcount != 1:
        db.rollback()
        raise FollowupConflict('跟进记录已变化，请刷新后操作', followup_id)
    row = get(db, followup_id)
    if row.notification_id:
        notification = db.get(NotificationLog, row.notification_id)
        if notification and notification.read_at is None:
            notification.read_at = now
    db.commit()
    return row
