from datetime import date, datetime, timedelta

from app.models import Task
from app.services import schedule_service


def _add_task(db_session, title, due_date=None, estimated_minutes=None, priority="中"):
    task = Task(
        title=title,
        due_date=datetime.combine(due_date, datetime.min.time()) if due_date else None,
        estimated_minutes=estimated_minutes,
        priority=priority,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def test_range_load_overdue_only_on_first_day(db_session):
    """① 逾期任务只出现在第 1 天的 items 里，第 2-7 天没有。"""
    today = date.today()
    overdue = _add_task(db_session, "逾期两天", due_date=today - timedelta(days=2), estimated_minutes=60)

    load = schedule_service.get_range_load(db_session, today, 7)
    assert len(load) == 7

    day1_item_ids = {it["task_id"] for it in load[0]["items"]}
    assert overdue.id in day1_item_ids  # 逾期计入第 1 天（start 当天）

    for day in load[1:]:
        later_ids = {it["task_id"] for it in day["items"]}
        assert overdue.id not in later_ids  # 逾期不向后蔓延


def test_range_load_safe_across_month_boundary(db_session):
    """② start 接近月末时，跨月的第 6/7 天仍有正确计数（治「跨月读成 0」）。"""
    start = date(2026, 1, 29)  # 1 月 29 日起 7 天，会跨到 2 月
    cross_month_day = date(2026, 2, 2)  # 第 5 天（index=4）落到 2 月
    _add_task(db_session, "跨月任务", due_date=cross_month_day, estimated_minutes=90)

    load = schedule_service.get_range_load(db_session, start, 7)
    dates = [d["date"] for d in load]
    assert dates == [
        "2026-01-29", "2026-01-30", "2026-01-31",
        "2026-02-01", "2026-02-02", "2026-02-03", "2026-02-04",
    ]

    cross_day = next(d for d in load if d["date"] == "2026-02-02")
    assert cross_day["count"] >= 1  # 跨月那天任务仍被正确计入


def test_range_load_includes_chinese_weekday_and_minutes(db_session):
    """③ 每日 dict 含 weekday（中文星期）与 total_minutes。"""
    today = date.today()
    _add_task(db_session, "今日截止", due_date=today, estimated_minutes=45)

    load = schedule_service.get_range_load(db_session, today, 7)
    chinese_weekdays = set("一二三四五六日")
    for day in load:
        assert day["weekday"] in chinese_weekdays
        assert isinstance(day["total_minutes"], int)
    # 今日那条应包含预估时长
    today_day = load[0]
    assert today_day["total_minutes"] == 45


def test_range_load_future_due_not_counted_before_due_date(db_session):
    """未来截止的任务只在到期当天出现，不提前计入（验证不误算）。"""
    today = date.today()
    _add_task(db_session, "明天截止", due_date=today + timedelta(days=1), estimated_minutes=30)

    load = schedule_service.get_range_load(db_session, today, 7)
    today_day = load[0]
    tomorrow_day = load[1]
    assert today_day["count"] == 0  # 今天还没到截止
    assert tomorrow_day["count"] == 1  # 明天才出现
