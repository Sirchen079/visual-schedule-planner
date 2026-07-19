"""幕僚洞察引擎 + 周报全域扩充。"""
from datetime import date, datetime, timedelta

from app.services import insight_service


def _kinds(insights):
    return {i["kind"] for i in insights}


def test_insights_empty_when_no_data(db_session):
    assert insight_service.compute_insights(db_session) == []


def test_habit_streak_risk_insight(db_session):
    from app.models import Habit, HabitLog

    habit = Habit(name="喝水", target_count=1)
    db_session.add(habit)
    db_session.commit()
    today = date.today()
    for offset in (1, 2, 3):  # 连续 3 天达标，但今天还没打卡
        db_session.add(HabitLog(habit_id=habit.id, date=today - timedelta(days=offset), count=1))
    db_session.commit()

    insights = insight_service.compute_insights(db_session)
    assert "habit_streak_risk" in _kinds(insights)
    text = next(i["text"] for i in insights if i["kind"] == "habit_streak_risk")
    assert "喝水" in text and "3" in text

    # 今天打卡后不再提醒
    db_session.add(HabitLog(habit_id=habit.id, date=today, count=1))
    db_session.commit()
    assert "habit_streak_risk" not in _kinds(insight_service.compute_insights(db_session))


def test_kr_behind_insight(db_session):
    from app.models import Goal, KeyResult

    today = date.today()
    goal = Goal(
        title="Q3 英语",
        status="active",
        start_date=today - timedelta(days=40),
        end_date=today + timedelta(days=20),  # 时间已过 2/3
    )
    db_session.add(goal)
    db_session.commit()
    db_session.add(KeyResult(goal_id=goal.id, title="背单词", kind="manual", target_value=100, current_value=10))
    db_session.commit()

    insights = insight_service.compute_insights(db_session)
    assert "kr_behind" in _kinds(insights)
    text = next(i["text"] for i in insights if i["kind"] == "kr_behind")
    assert "Q3 英语" in text


def test_timer_long_running_insight(db_session):
    from app.models import Task, TimeLog

    task = Task(title="超长任务", status="进行中")
    db_session.add(task)
    db_session.commit()
    db_session.add(
        TimeLog(task_id=task.id, task_title="超长任务", started_at=datetime.now() - timedelta(minutes=75))
    )
    db_session.commit()

    insights = insight_service.compute_insights(db_session)
    assert "timer_long_running" in _kinds(insights)


def test_journal_mood_low_insight(db_session):
    from app.models import JournalEntry

    today = date.today()
    for offset in (0, 1):
        db_session.add(JournalEntry(date=today - timedelta(days=offset), content="心事重重", mood="差"))
    db_session.commit()

    insights = insight_service.compute_insights(db_session)
    assert "journal_mood_low" in _kinds(insights)


def test_no_time_tracking_insight(db_session):
    from app.models import Task

    db_session.add(
        Task(title="已完成", status="完成", completed_at=datetime.now() - timedelta(days=1))
    )
    db_session.add(
        Task(title="已完成2", status="完成", completed_at=datetime.now() - timedelta(days=2))
    )
    db_session.commit()

    insights = insight_service.compute_insights(db_session)
    assert "no_time_tracking" in _kinds(insights)


def test_insights_respect_feature_flags(db_session):
    from app.models import Habit, HabitLog
    from app.services import app_setting_service

    habit = Habit(name="喝水", target_count=1)
    db_session.add(habit)
    db_session.commit()
    today = date.today()
    for offset in (1, 2, 3):
        db_session.add(HabitLog(habit_id=habit.id, date=today - timedelta(days=offset), count=1))
    db_session.commit()

    app_setting_service.set_setting(db_session, "feature_habits_enabled", "false")
    assert "habit_streak_risk" not in _kinds(insight_service.compute_insights(db_session))


# ---- 周报全域扩充 ----

def test_weekly_extra_includes_domains(db_session):
    from app.models import Goal, Habit, KeyResult
    from app.services import ai_report_service

    db_session.add(Goal(title="目标A", status="active"))
    db_session.commit()
    goal = db_session.query(Goal).first()
    db_session.add(KeyResult(goal_id=goal.id, title="KR", target_value=10, current_value=5))
    db_session.add(Habit(name="习惯A", target_count=1))
    db_session.commit()

    extra = ai_report_service._weekly_extra(db_session)
    assert extra["goals"][0]["title"] == "目标A"
    assert extra["goals"][0]["krs"][0]["progress"] == 50
    assert extra["habits"][0]["name"] == "习惯A"
    assert "time" in extra
    assert "insights" in extra


def test_weekly_prompt_contains_extra_sections(db_session):
    from app.services import ai_report_service

    data = {
        "period_start": date(2026, 7, 13),
        "period_end": date(2026, 7, 19),
        "next_label": "下周",
        "next_range": ["2026-07-20", "2026-07-26"],
        "summary": {},
        "completed": [],
        "in_progress": [],
        "due_in_window": [],
        "overdue": [],
        "new_in_window": [],
        "next": [],
        "goals": [{"title": "目标A", "progress": 50, "krs": []}],
        "insights": ["观察一"],
    }
    _system, user = ai_report_service.build_report_prompt(None, "weekly", data)
    assert "目标进度（OKR）" in user
    assert "目标A" in user
    assert "幕僚观察" in user
    assert "观察一" in user
