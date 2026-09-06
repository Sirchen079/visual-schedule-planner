# tests/domain/test_stats.py
from datetime import datetime
from freezegun import freeze_time
from zhishi.domain import stats
from zhishi.domain.tasks import service as ts
from zhishi.domain.tasks.schemas import TaskCreate


@freeze_time("2026-09-10")
def test_summary_and_daily(db):
    a = ts.create_task(db, TaskCreate(title="昨日完成"))
    ts.update_task(db, a.id, status="done")
    ts.create_task(db, TaskCreate(title="今日新增"))
    s = stats.summary(db)
    assert s["done"] >= 1 and s["todo"] >= 1
    daily = stats.daily(db, days=7)
    assert any(p["completed"] >= 1 for p in daily)


@freeze_time("2026-09-10")
def test_risk_scores_overdue(db):
    t = ts.create_task(db, TaskCreate(title="已逾期", due_date=datetime(2026, 9, 1)))
    risks = stats.risk(db)
    assert risks and risks[0]["task_id"] == t.id and risks[0]["score"] >= 50
