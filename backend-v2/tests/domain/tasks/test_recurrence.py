from datetime import date, datetime, time
from freezegun import freeze_time
from zhishi.domain.tasks import service as ts
from zhishi.domain.tasks.recurrence import advance_occurrence, next_rrule_occurrence
from zhishi.domain.tasks.schemas import TaskCreate


def test_enum_advance_weekly():
    due = datetime(2026, 9, 7, 9, 0)  # 周一
    assert advance_occurrence(due, "weekly", 1, after=due) == datetime(2026, 9, 14, 9, 0)


def test_enum_advance_weekdays_skips_weekend():
    due = datetime(2026, 9, 4, 9, 0)  # 周五
    assert advance_occurrence(due, "weekdays", 1, after=due) == datetime(2026, 9, 7, 9, 0)  # 跳到周一


def test_enum_advance_monthly_clamps_day():
    due = datetime(2026, 1, 31, 9, 0)
    assert advance_occurrence(due, "monthly", 1, after=due) == datetime(2026, 2, 28, 9, 0)


def test_enum_advance_catches_up_after():
    """逾期补卡：结果不得早于 after（今天 0 点）。"""
    due = datetime(2026, 9, 1, 9, 0)
    after = datetime(2026, 9, 20)
    assert advance_occurrence(due, "weekly", 1, after=after) == datetime(2026, 9, 22, 9, 0)


def test_rrule_next_biweekly():
    """单双周：FREQ=WEEKLY;INTERVAL=2 —— 课表核心场景。"""
    nxt = next_rrule_occurrence("FREQ=WEEKLY;INTERVAL=2;BYDAY=MO",
                                after=datetime(2026, 9, 3))
    assert nxt == datetime(2026, 9, 7, 0, 0)  # 下一个周一


@freeze_time("2026-09-03")
def test_complete_recurring_spawns_next(db):
    t = ts.create_task(db, TaskCreate(title="周会", due_date=datetime(2026, 9, 2, 10, 0),
                                      recur_rule="weekly"))
    ts.update_task(db, t.id, status="done")
    spawned = ts.list_tasks(db, status="todo")
    assert len(spawned) == 1
    assert spawned[0].due_date == datetime(2026, 9, 9, 10, 0)  # 从原截止推进；过期则跳到未来
    assert spawned[0].title == "周会"


@freeze_time("2026-09-03")
def test_complete_rrule_task_spawns_next(db):
    t = ts.create_task(db, TaskCreate(title="双周实验", due_date=datetime(2026, 8, 31, 14, 0),
                                      recur_rrule="FREQ=WEEKLY;INTERVAL=2;BYDAY=MO"))
    ts.update_task(db, t.id, status="done")
    spawned = ts.list_tasks(db, status="todo")
    assert spawned[0].due_date == datetime(2026, 9, 14, 14, 0)  # 9/7 不是双周，跳到 9/14
