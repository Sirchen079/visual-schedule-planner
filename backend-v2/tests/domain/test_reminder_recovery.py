from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from zhishi.domain import notifications as ns
from zhishi.domain.models import AppSetting, NotificationLog
from zhishi.domain.tasks import service as ts
from zhishi.domain.tasks.schemas import TaskCreate, TaskUpdate


def task(db, **fields):
    return ts.create_task(db, TaskCreate(title="提醒", **fields))


def test_separate_due_time_takes_precedence_and_body_matches(db):
    row = task(db, due_date=datetime(2026, 9, 6), due_time="09:00", remind_offsets=[30, 0])
    assert ns.record_due_reminders(db, datetime(2026, 9, 6, 0, 1)) == 0
    assert ns.record_due_reminders(db, datetime(2026, 9, 6, 8, 29)) == 0
    assert ns.record_due_reminders(db, datetime(2026, 9, 6, 8, 30)) == 1
    log = ns.list_notifications(db)[0]
    assert "09-06 09:00" in log.body
    assert log.remind_at == datetime(2026, 9, 6, 8, 30)
    assert log.target_path == f"/board?task={row.id}"
    assert ns.record_due_reminders(db, datetime(2026, 9, 6, 8, 31)) == 0
    assert ns.record_due_reminders(db, datetime(2026, 9, 6, 9)) == 1


def test_restart_recovers_latest_missed_offset_once(db):
    task(db, due_date=datetime(2026, 9, 6, 9), remind_offsets=[60, 30, 0])
    ns.record_due_reminders(db, datetime(2026, 9, 6, 7))
    with Session(db.bind) as restarted:
        assert ns.record_due_reminders(restarted, datetime(2026, 9, 6, 12)) == 1
        log = ns.list_notifications(restarted)[0]
        assert log.remind_at == datetime(2026, 9, 6, 9)
        assert "补发提醒" in log.body
    with Session(db.bind) as again:
        assert ns.record_due_reminders(again, datetime(2026, 9, 6, 12, 1)) == 0


def test_current_offset_supersedes_missed_and_seven_day_cap(db):
    task(db, due_date=datetime(2026, 9, 6, 9), remind_offsets=[60, 30, 0])
    task(db, due_date=datetime(2026, 8, 20, 9), remind_offsets=[0])
    ns.record_due_reminders(db, datetime(2026, 8, 1, 7))
    assert ns.record_due_reminders(db, datetime(2026, 9, 6, 9, 10)) == 1
    assert "补发" not in ns.list_notifications(db)[0].body


@pytest.mark.parametrize("bad", ['{}', '[null, true, -1, 9999999999999999999, "0"]', 'broken'])
def test_bad_legacy_offsets_do_not_block_other_tasks(db, bad):
    due = datetime(2026, 9, 6, 9)
    broken = task(db, due_date=due, remind_offsets=[])
    broken.remind_offsets = bad
    invalid_time = task(db, due_date=due, remind_offsets=[0])
    invalid_time.due_time = "25:99"
    db.commit()
    good = task(db, due_date=due, remind_offsets=[0])
    assert ns.record_due_reminders(db, due) == 1
    assert ns.list_notifications(db)[0].task_id == good.id


def test_deleted_completed_disabled_and_cleared_dates_do_not_fire(db):
    due = datetime(2026, 9, 6, 9)
    cleared = task(db, due_date=due, due_time="09:00", remind_offsets=[0])
    ts.update_task(db, cleared.id, due_date=None, due_time=None)
    assert cleared.due_date is None and cleared.due_time is None
    disabled = task(db, due_date=due, remind_offsets=[0])
    ts.update_task(db, disabled.id, remind_offsets=[])
    done = task(db, due_date=due, remind_offsets=[0])
    ts.update_task(db, done.id, status="done")
    deleted = task(db, due_date=due, remind_offsets=[0])
    ts.soft_delete_task(db, deleted.id)
    assert ns.record_due_reminders(db, due) == 0


@pytest.mark.parametrize("offsets", [[-1], [True], ["30"], [525601], [0] * 21])
def test_invalid_offsets_rejected_on_create_and_update(offsets):
    with pytest.raises(ValidationError):
        TaskCreate(title="bad", remind_offsets=offsets)
    with pytest.raises(ValidationError):
        TaskUpdate(remind_offsets=offsets)


def test_read_all_does_not_leave_older_unread_rows(db):
    now = datetime(2026, 9, 6, 9)
    db.add_all(NotificationLog(title=str(i), remind_at=now-timedelta(minutes=i)) for i in range(1005))
    db.commit()
    ns.mark_read(db)
    assert ns.unread_count(db) == 0


def test_failed_write_does_not_advance_cursor(db, monkeypatch):
    now = datetime(2026, 9, 6, 9)
    ns.record_due_reminders(db, now - timedelta(hours=2))
    task(db, due_date=now, remind_offsets=[0])
    original = db.commit
    def fail():
        raise RuntimeError("disk failure")
    monkeypatch.setattr(db, 'commit', fail)
    with pytest.raises(RuntimeError):
        ns.record_due_reminders(db, now)
    db.rollback()
    monkeypatch.setattr(db, 'commit', original)
    assert db.scalar(select(AppSetting.value).where(AppSetting.key == ns.CURSOR_KEY)) == (now-timedelta(hours=2)).isoformat()
    assert ns.record_due_reminders(db, now) == 1
