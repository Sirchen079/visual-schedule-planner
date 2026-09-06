import json

import pytest

from zhishi.agent.tools.atomic_write import create_task, update_task
from zhishi.domain.notifications import record_due_reminders
from zhishi.domain.tasks.service import get_task
from datetime import datetime


def test_model_task_time_and_explicit_clear(db):
    row = json.loads(create_task(db, '发送报告', due_date='2026-09-06', due_time='09:00', remind_offsets=[0]))
    assert record_due_reminders(db, datetime(2026, 9, 6, 0, 1)) == 0
    assert record_due_reminders(db, datetime(2026, 9, 6, 9)) == 1
    changed = json.loads(update_task(db, row['id'], clear_due_time=True, clear_due_date=True, remind_offsets=[]))
    assert changed['due_date'] is None and changed['due_time'] is None and changed['remind_offsets'] == []
    assert get_task(db, row['id']).due_date is None


def test_conflicting_clear_does_not_mutate_task(db):
    row = json.loads(create_task(db, '报告', due_date='2026-09-06', due_time='09:00'))
    with pytest.raises(ValueError):
        update_task(db, row['id'], title='不应保存', due_time='10:00', clear_due_time=True)
    assert get_task(db, row['id']).title == '报告'
