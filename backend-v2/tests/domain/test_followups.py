# ruff: noqa: DTZ001 -- v2 follows local wall time.
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from tests.domain.test_research import NOW, draft, project
from zhishi.domain import followups, settingsvc
from zhishi.domain.models import (
    NotificationLog,
    ResearchPlan,
    SecretaryFollowup,
    Task,
    TaskScheduleEntry,
)
from zhishi.domain.research import service


def started(db):
    p = project(db)
    plan = service.preview_plan(db, p.id, draft(), now=NOW)
    service.apply_plan(db, plan.id, now=NOW)
    return p, service.detail(db, p.id).tasks


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_missed_time_creates_one_persistent_preview_and_notification(db):
    p, tasks = started(db)
    now = NOW + timedelta(days=1)
    first = followups.check_project(db, p.id, now=now)
    assert first.kind == 'replan' and first.status == 'pending' and first.plan_id
    assert count(db, Task) == 3
    assert first.notification_id
    for _ in range(3):
        same = followups.check_project(db, p.id, now=now)
        assert same.id == first.id and same.plan_id == first.plan_id
    assert count(db, NotificationLog) == 1 and count(db, SecretaryFollowup) == 1
    applied = followups.apply(db, same.id, same.version, now=now)
    assert applied.status == 'applied'
    assert followups.check_project(db, p.id, now=now) is None
    assert count(db, Task) == 3
    assert service.detail(db, p.id).tasks[0].task_id == tasks[0].task_id
    assert followups.apply(db, applied.id, 1, now=now).status == 'applied'


def test_snooze_dismiss_and_reopen_only_on_new_evidence(db):
    p, _ = started(db)
    now = NOW + timedelta(days=1)
    row = followups.check_project(db, p.id, now=now)
    until = now + timedelta(hours=2)
    followups.respond(db, row.id, row.version, snooze_until=until, now=now)
    assert followups.check_project(db, p.id, now=now+timedelta(hours=1)).status == 'snoozed'
    assert count(db, NotificationLog) == 1
    awake = followups.check_project(db, p.id, now=until)
    assert awake.status == 'pending' and count(db, NotificationLog) == 2
    followups.respond(db, awake.id, awake.version, now=until)
    assert followups.check_project(db, p.id, now=until).status == 'dismissed'
    assert count(db, NotificationLog) == 2
    later = followups.check_project(db, p.id, now=now+timedelta(days=2))
    assert later.id != row.id


def test_autonomous_followup_obeys_switch_and_permission(db):
    p, _ = started(db)
    now = NOW + timedelta(days=1)
    settingsvc.set_setting(db, 'feature_autopilot_enabled', 'true')
    row = followups.check_project(db, p.id, now=now)
    assert row.status == 'pending'  # standard mode still requires approval
    settingsvc.set_setting(db, 'agent_autonomy', 'autonomous')
    row = followups.check_project(db, p.id, now=now)
    assert row.status == 'applied' and count(db, Task) == 3


def test_expired_window_and_completion_are_actionable_without_fake_replanning(db):
    p, tasks = started(db)
    now = datetime(2026, 9, 21, 9)
    row = followups.check_project(db, p.id, now=now)
    assert row.kind == 'needs_window' and row.plan_id is None
    for task in tasks:
        db.get(Task, task.task_id).status = 'done'
    db.commit()
    finished = followups.check_project(db, p.id, now=now)
    assert finished.kind == 'completed' and finished.plan_id is None
    assert followups.get(db, row.id).status == 'resolved'


def test_stale_followup_apply_does_not_change_calendar(db):
    p, tasks = started(db)
    now = NOW + timedelta(days=1)
    row = followups.check_project(db, p.id, now=now)
    count_before = count(db, TaskScheduleEntry)
    db.get(Task, tasks[0].task_id).status = 'done'
    db.commit()
    with pytest.raises(followups.FollowupConflict):
        followups.apply(db, row.id, row.version, now=now)
    assert count(db, TaskScheduleEntry) == count_before


def test_concurrent_scans_do_not_duplicate_followups_or_notifications(db):
    p, _ = started(db)
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    now = NOW + timedelta(days=1)
    def scan():
        with factory() as session:
            return followups.check_project(session, p.id, now=now).id
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert len(set(pool.map(lambda _: scan(), range(4)))) == 1
    assert count(db, SecretaryFollowup) == 1 and count(db, NotificationLog) == 1
    assert count(db, ResearchPlan) == 2


def test_new_missed_occurrence_is_not_suppressed_by_previous_adjustment(db):
    p, tasks = started(db)
    for task in tasks[1:]:
        db.get(Task,task.task_id).status = 'done'
    db.commit()
    now = NOW + timedelta(days=1)
    row = followups.check_project(db,p.id,now=now)
    followups.apply(db,row.id,row.version,now=now)
    assert followups.check_project(db,p.id,now=now) is None
    assigned = service.plan_read(service.get_plan(db,row.plan_id)).assignments[0]
    missed_again = datetime.fromisoformat(assigned.date+'T'+assigned.end)+timedelta(minutes=1)
    later = followups.check_project(db,p.id,now=missed_again)
    assert later.id != row.id and later.status == 'pending'


def test_auto_adjustment_does_not_claim_to_fix_preserved_manual_conflict(db):
    from zhishi.domain.schedule import service as schedule
    p, tasks = started(db)
    manual = db.get(TaskScheduleEntry,tasks[0].slots[0].id)
    manual.note = 'user moved this appointment'
    db.commit()
    schedule.create_event(db,title='Meeting',date=manual.date,start_time=manual.start_time,end_time=manual.end_time)
    settingsvc.set_setting(db,'agent_autonomy','autonomous')
    settingsvc.set_setting(db,'feature_autopilot_enabled','true')
    row = followups.check_project(db,p.id,now=NOW)
    assert row.status == 'pending'
    assert service.get_plan(db,row.plan_id).state == 'draft'


def test_committed_adjustment_recovers_receipt_after_process_interruption(db, monkeypatch):
    p, tasks = started(db)
    now = NOW + timedelta(days=1)
    row = followups.check_project(db, p.id, now=now)
    settingsvc.set_setting(db, 'feature_autopilot_enabled', 'true')
    settingsvc.set_setting(db, 'agent_autonomy', 'autonomous')
    original = followups._finish_apply
    def crash(*args):
        raise RuntimeError('simulated process interruption after calendar commit')
    monkeypatch.setattr(followups, '_finish_apply', crash)
    with pytest.raises(RuntimeError):
        followups.apply(db, row.id, row.version, now=now, automatic=True)
    db.rollback()
    assert followups.get(db, row.id).status == 'applying'
    assert service.get_plan(db, row.plan_id).state == 'applied'
    monkeypatch.setattr(followups, '_finish_apply', original)
    assert followups.check_project(db, p.id, now=now) is None
    receipt = followups.get(db, row.id)
    assert receipt.status == 'applied' and '已按最新约束调整' in receipt.body
    assert count(db, NotificationLog) == 2
    followups.check_project(db, p.id, now=now)
    assert count(db, NotificationLog) == 2 and count(db, Task) == len(tasks)


def test_waiting_partial_replan_retries_when_calendar_capacity_changes(db):
    from zhishi.domain.models import Event
    from zhishi.domain.schedule import service as schedule
    p, tasks = started(db)
    for task in tasks[1:]:
        db.get(Task, task.task_id).status = 'done'
    db.commit()
    now = NOW + timedelta(days=1)
    for offset in range(1, 13):
        schedule.create_event(db, title='Unavailable', date=(NOW+timedelta(days=offset)).date())
    row = followups.check_project(db, p.id, now=now)
    assert service.plan_read(service.get_plan(db, row.plan_id)).unassigned
    row = followups.apply(db, row.id, row.version, now=now)
    assert row.status == 'waiting'
    old_plan = row.plan_id
    assert followups.check_project(db, p.id, now=now).status == 'waiting'
    db.query(Event).filter_by(title='Unavailable').delete()
    db.commit()
    fresh = followups.check_project(db, p.id, now=now)
    assert fresh.status == 'pending' and fresh.plan_id != old_plan
    assert not service.plan_read(service.get_plan(db, fresh.plan_id)).unassigned


def test_revoked_autonomy_after_preview_prevents_calendar_write(db, monkeypatch):
    p, _ = started(db)
    now = NOW + timedelta(days=1)
    settingsvc.set_setting(db, 'feature_autopilot_enabled', 'true')
    settingsvc.set_setting(db, 'agent_autonomy', 'autonomous')
    original = followups.apply
    def revoke(session, *args, **kwargs):
        settingsvc.set_setting(session, 'feature_followup_enabled', 'false')
        return original(session, *args, **kwargs)
    monkeypatch.setattr(followups, 'apply', revoke)
    before = [(e.id, e.date) for e in db.scalars(select(TaskScheduleEntry))]
    row = followups.check_project(db, p.id, now=now)
    assert row.status == 'pending' and '自动调整已暂停' in row.error
    assert service.get_plan(db, row.plan_id).state == 'draft'
    assert [(e.id, e.date) for e in db.scalars(select(TaskScheduleEntry))] == before


def test_snooze_wins_race_before_apply_claim(db, monkeypatch):
    p, _ = started(db)
    now = NOW + timedelta(days=1)
    row = followups.check_project(db, p.id, now=now)
    version = row.version
    original = followups.observe
    def snooze_first(session, *args):
        followups.respond(session, row.id, version, now=now, snooze_until=now+timedelta(hours=2))
        return original(session, *args)
    monkeypatch.setattr(followups, 'observe', snooze_first)
    with pytest.raises(followups.FollowupConflict):
        followups.apply(db, row.id, version, now=now)
    assert followups.get(db, row.id).status == 'snoozed'
    assert service.get_plan(db, row.plan_id).state == 'draft'


def test_guidance_for_blocked_or_completed_followups_does_not_loop_between_reads(db):
    import json

    from zhishi.agent.tools.followup_tools import get_secretary_followup
    p, tasks = started(db)
    row = followups.check_project(db, p.id, now=datetime(2026, 9, 21, 9))
    result = json.loads(get_secretary_followup(db, row.id))
    assert 'next_call' not in result and result['project_context']['spec']['end_date'] == '2026-09-20'
    assert '到此结束' in result['next_step']
    for task in tasks:
        db.get(Task, task.task_id).status = 'done'
    db.commit()
    row = followups.check_project(db, p.id, now=datetime(2026, 9, 21, 9))
    result = json.loads(get_secretary_followup(db, row.id))
    assert 'next_call' not in result and '不重排已完成任务' in result['next_step']
