# ruff: noqa: DTZ001 -- v2 persists local wall times; these fixtures exercise that contract.
import json
from datetime import date, datetime

import pytest
from sqlalchemy import select

from zhishi.domain.models import AppSetting, Event, NotificationLog
from zhishi.domain.notifications import CURSOR_KEY, record_due_reminders
from zhishi.domain.schedule.schemas import EventUpdate
from zhishi.domain.schedule.service import create_event, delete_event, update_event


def event(db, **changes):
    return create_event(db, **{'title': '出差会议', 'date': date(2026, 9, 6),
        'start_time': '15:00', 'end_time': '16:00', 'location': '三楼', 'remind_offsets': [0, 30], **changes})


def logs(db):
    return list(db.scalars(select(NotificationLog).order_by(NotificationLog.id)))


def test_event_due_reminder_and_repeated_scan_are_separate_from_tasks(db):
    row = event(db)
    assert record_due_reminders(db, datetime(2026, 9, 6, 14, 29)) == 0
    assert record_due_reminders(db, datetime(2026, 9, 6, 14, 30)) == 1
    assert record_due_reminders(db, datetime(2026, 9, 6, 14, 31)) == 0
    note = logs(db)[0]
    assert note.task_id is None and note.kind == 'event_reminder'
    assert note.target_path == f'/calendar?date=2026-09-06&event={row.id}'
    assert '三楼' in note.body and '09-06 15:00' in note.body
    assert record_due_reminders(db, datetime(2026, 9, 6, 15, 0)) == 1


def test_all_day_reminder_requires_explicit_clock_and_supports_prior_day(db):
    with pytest.raises(ValueError, match='全天日程'):
        event(db, start_time=None, end_time=None)
    event(db, start_time=None, end_time=None, reminder_time='09:00', remind_offsets=[1440])
    assert record_due_reminders(db, datetime(2026, 9, 5, 9, 0)) == 1
    assert logs(db)[0].target_path.startswith('/calendar?date=2026-09-06')


def test_recurring_sleep_catchup_collapses_old_occurrences_then_reminds_next(db):
    event(db, date=date(2026, 9, 1), recur_rrule='FREQ=DAILY;COUNT=8')
    db.add(AppSetting(key=CURSOR_KEY, value='2026-09-01T10:00:00'))
    db.commit()
    assert record_due_reminders(db, datetime(2026, 9, 6, 18, 0)) == 1
    assert '补发提醒' in logs(db)[0].body
    assert logs(db)[0].remind_at == datetime(2026, 9, 6, 15, 0)
    assert record_due_reminders(db, datetime(2026, 9, 6, 18, 1)) == 0
    assert record_due_reminders(db, datetime(2026, 9, 7, 14, 30)) == 1


def test_reschedule_disable_and_delete_stop_old_reminders(db):
    row = event(db)
    update_event(db, row.id, EventUpdate(start_time='17:00', end_time='18:00'))
    assert record_due_reminders(db, datetime(2026, 9, 6, 14, 30)) == 0
    assert record_due_reminders(db, datetime(2026, 9, 6, 16, 30)) == 1
    update_event(db, row.id, EventUpdate(remind_offsets=[]))
    assert record_due_reminders(db, datetime(2026, 9, 6, 17, 0)) == 0
    update_event(db, row.id, EventUpdate(remind_offsets=[0], start_time='19:00'))
    delete_event(db, row.id)
    assert record_due_reminders(db, datetime(2026, 9, 6, 19, 0)) == 0
    assert len(logs(db)) == 1


@pytest.mark.parametrize('changes', [
    {'remind_offsets': [-1]}, {'remind_offsets': [True]}, {'remind_offsets': [10081]},
    {'remind_offsets': list(range(9))}, {'reminder_time': '24:00'},
    {'recur_rrule': 'FREQ=SECONDLY'}, {'recur_rrule': 'FREQ=DAILY;INTERVAL=0'},
    {'recur_rrule': 'FREQ=DAILY;BYHOUR=1,2'},
])
def test_invalid_reminder_settings_reject_before_insert(db, changes):
    with pytest.raises(ValueError):
        event(db, **changes)
    assert not list(db.scalars(select(Event)))


def test_invalid_legacy_event_cannot_block_valid_notifications(db):
    bad = event(db)
    bad.recur_rrule = 'FREQ=DAILY;INTERVAL=0'
    db.commit()
    good = event(db, title='正常会议')
    assert record_due_reminders(db, datetime(2026, 9, 6, 14, 30)) == 1
    assert logs(db)[0].title == good.title


def test_monthly_event_and_duplicate_offsets(db):
    row = event(db, date=date(2026, 8, 6), recur_rrule='FREQ=MONTHLY;COUNT=2', remind_offsets=[30, 30])
    assert json.loads(row.remind_offsets) == [30]
    assert record_due_reminders(db, datetime(2026, 9, 6, 14, 30)) == 1
    assert record_due_reminders(db, datetime(2026, 10, 6, 14, 30)) == 0
