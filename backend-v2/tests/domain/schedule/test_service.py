from datetime import date
from zhishi.domain.tasks import service as ts
from zhishi.domain.tasks.schemas import TaskCreate
from zhishi.domain.schedule import service as ss


def test_assign_and_unique_per_date(db):
    t = ts.create_task(db, TaskCreate(title="复习"))
    ss.assign_task_to_day(db, t.id, date(2026, 9, 10))
    ss.assign_task_to_day(db, t.id, date(2026, 9, 10), start_time="14:00", end_time="15:30")  # upsert
    day = ss.day_schedule(db, date(2026, 9, 10))
    assert len(day["tasks"]) == 1
    assert day["tasks"][0]["start_time"] == "14:00"


def test_month_view_counts(db):
    for d in (3, 10, 17):
        t = ts.create_task(db, TaskCreate(title=f"周任务{d}"))
        ss.assign_task_to_day(db, t.id, date(2026, 9, d))
    month = ss.month_schedule(db, 2026, 9)
    assert {c["date"] for c in month if c["task_count"] > 0} == {"2026-09-03", "2026-09-10", "2026-09-17"}


def test_range_load_for_ai(db):
    t = ts.create_task(db, TaskCreate(title="负载任务", estimated_minutes=60))
    ss.assign_task_to_day(db, t.id, date(2026, 9, 3))
    load = ss.range_load(db, date(2026, 9, 1), days=7)
    assert load["2026-09-03"]["estimated_minutes"] == 60
    assert load["2026-09-02"]["estimated_minutes"] == 0
