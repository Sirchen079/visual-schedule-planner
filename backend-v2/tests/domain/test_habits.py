# tests/domain/test_habits.py
from datetime import date, timedelta
from freezegun import freeze_time
from zhishi.domain.habits import service as hs
from zhishi.domain.habits.schemas import HabitCreate


def _seed(db):
    return hs.create_habit(db, HabitCreate(name="跑步", target_count=1))


@freeze_time("2026-09-10")
def test_check_in_and_status(db):
    h = _seed(db)
    hs.check_in(db, h.id, date(2026, 9, 9))
    hs.check_in(db, h.id, date(2026, 9, 10))
    st = hs.habit_status(db, h.id)
    assert st["streak"] == 2 and st["done_today"] is True


@freeze_time("2026-09-10")
def test_today_not_done_keeps_streak(db):
    """今天未打卡不打断纪录——算到昨天为止（补卡机会）。"""
    h = _seed(db)
    for d in (8, 9):
        hs.check_in(db, h.id, date(2026, 9, d))
    st = hs.habit_status(db, h.id)
    assert st["streak"] == 2 and st["done_today"] is False


@freeze_time("2026-09-10")
def test_gap_breaks_streak(db):
    h = _seed(db)
    hs.check_in(db, h.id, date(2026, 9, 9))
    hs.check_in(db, h.id, date(2026, 9, 7))  # 8 日断
    assert hs.habit_status(db, h.id)["streak"] == 1


def test_uncheck_removes_log_at_zero(db):
    h = _seed(db)
    hs.check_in(db, h.id, date(2026, 9, 10))
    hs.uncheck(db, h.id, date(2026, 9, 10))
    logs = hs.list_logs(db, h.id, days=7)
    assert logs == []


def test_weekly_streak(db):
    h = hs.create_habit(db, HabitCreate(name="周报", period="weekly", target_count=1))
    with freeze_time("2026-09-10"):  # 周四，本周起 9/7
        hs.check_in(db, h.id, date(2026, 9, 7))
        hs.check_in(db, h.id, date(2026, 9, 2))  # 上周
        assert hs.habit_status(db, h.id)["streak"] == 2
