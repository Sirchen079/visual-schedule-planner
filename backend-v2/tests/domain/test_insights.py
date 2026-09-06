# tests/domain/test_insights.py
from datetime import date, datetime, timedelta
from freezegun import freeze_time
from zhishi.domain import insights
from zhishi.domain.habits import service as hs
from zhishi.domain.habits.schemas import HabitCreate
from zhishi.domain.tasks import service as ts
from zhishi.domain.tasks.schemas import TaskCreate


@freeze_time("2026-09-10")
def test_streak_risk_insight(db):
    h = hs.create_habit(db, HabitCreate(name="背单词", target_count=1))
    for d in (7, 8, 9):
        hs.check_in(db, h.id, date(2026, 9, d))
    texts = [i["text"] for i in insights.compute_insights(db)]
    assert any("背单词" in t for t in texts)


@freeze_time("2026-09-10")
def test_urgent_task_without_schedule_insight(db):
    ts.create_task(db, TaskCreate(title="交报告", priority="high",
                                  due_date=datetime(2026, 9, 11, 18, 0)))
    texts = [i["text"] for i in insights.compute_insights(db)]
    assert any("交报告" in t for t in texts)
