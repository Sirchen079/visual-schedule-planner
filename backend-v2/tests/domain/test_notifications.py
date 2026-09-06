# tests/domain/test_notifications.py
from datetime import datetime
from freezegun import freeze_time
from zhishi.domain.notifications import record_due_reminders, mark_read, unread_count
from zhishi.domain.tasks import service as ts
from zhishi.domain.tasks.schemas import TaskCreate


def _task_with_reminder(db, due, offsets):
    return ts.create_task(db, TaskCreate(title="提醒任务", due_date=due,
                                         remind_offsets=offsets))


@freeze_time("2026-09-03 09:00")
def test_due_reminders_recorded_idempotently(db):
    t = _task_with_reminder(db, datetime(2026, 9, 3, 10, 0), [30])  # 09:30 触发点已过? 09:00 未到
    # 09:35：30 分钟前提醒已到点
    with freeze_time("2026-09-03 09:35"):
        n = record_due_reminders(db)
    assert n == 1
    with freeze_time("2026-09-03 09:40"):
        assert record_due_reminders(db) == 0  # 幂等：不重复落
    assert unread_count(db) == 1


def test_mark_read(db):
    from sqlalchemy import select
    from zhishi.domain.models import NotificationLog
    t = _task_with_reminder(db, datetime(2026, 9, 3, 10, 0), [0])
    with freeze_time("2026-09-03 10:01"):
        record_due_reminders(db)
    log = db.scalars(select(NotificationLog)).first()
    mark_read(db, log.id)
    assert unread_count(db) == 0
