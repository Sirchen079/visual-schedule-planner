"""习惯打卡：habits CRUD + 按日累加打卡 + 连续纪录（streak）计算。"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Habit, HabitLog
from app.schemas import HabitCreate, HabitUpdate

HABIT_COLORS = ["#74ccf2", "#a5f2c1", "#fbbf7a", "#c4a5f2", "#f2a5c4", "#7fd4c4", "#f2d479"]


def _habit_query():
    return select(Habit).options(selectinload(Habit.logs))


def create_habit(db: Session, payload: HabitCreate) -> Habit:
    habit = Habit(**payload.model_dump())
    db.add(habit)
    db.commit()
    return get_habit(db, habit.id)


def get_habit(db: Session, habit_id: int) -> Habit | None:
    stmt = _habit_query().where(Habit.id == habit_id, Habit.deleted_at.is_(None))
    return db.execute(stmt).scalar_one_or_none()


def list_habits(db: Session) -> list[Habit]:
    stmt = (
        _habit_query()
        .where(Habit.deleted_at.is_(None))
        .order_by(Habit.sort_order.asc(), Habit.created_at.desc(), Habit.id.desc())
    )
    return list(db.execute(stmt).scalars().all())


def update_habit(db: Session, habit_id: int, payload: HabitUpdate) -> Habit | None:
    habit = get_habit(db, habit_id)
    if habit is None:
        return None
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(habit, field, value)
    db.commit()
    return get_habit(db, habit_id)


def soft_delete_habit(db: Session, habit_id: int) -> bool:
    habit = get_habit(db, habit_id)
    if habit is None:
        return False
    from datetime import datetime

    habit.deleted_at = datetime.now()
    db.commit()
    return True


# ---- 打卡 ----
def check_in(db: Session, habit_id: int, day: date | None = None) -> Habit | None:
    """打卡一次（当天 count+1，幂等键 (habit, date)）。"""
    habit = get_habit(db, habit_id)
    if habit is None:
        return None
    day = day or date.today()
    log = _get_log(db, habit_id, day)
    if log is None:
        log = HabitLog(habit_id=habit_id, date=day, count=0)
        db.add(log)
    log.count += 1
    db.commit()
    return get_habit(db, habit_id)


def uncheck(db: Session, habit_id: int, day: date | None = None) -> Habit | None:
    """撤销一次打卡（count-1，到 0 删除记录）。"""
    habit = get_habit(db, habit_id)
    if habit is None:
        return None
    day = day or date.today()
    log = _get_log(db, habit_id, day)
    if log is not None:
        log.count -= 1
        if log.count <= 0:
            db.delete(log)
        db.commit()
    return get_habit(db, habit_id)


def _get_log(db: Session, habit_id: int, day: date) -> HabitLog | None:
    stmt = select(HabitLog).where(HabitLog.habit_id == habit_id, HabitLog.date == day)
    return db.execute(stmt).scalar_one_or_none()


def list_logs(db: Session, habit_id: int, days: int = 84) -> list[HabitLog]:
    start = date.today() - timedelta(days=max(1, days) - 1)
    stmt = (
        select(HabitLog)
        .where(HabitLog.habit_id == habit_id, HabitLog.date >= start)
        .order_by(HabitLog.date)
    )
    return list(db.execute(stmt).scalars().all())


# ---- 计算：今日进度 / 连续纪录 ----
def habit_status(habit: Habit, today: date | None = None) -> dict:
    """返回 {today_count, period_count, streak, done_today}。

    streak 规则：daily 看连续「达到 target_count」的天数，weekly 看连续达标周数；
    今天（本周）未达标不打断——纪录算到昨天（上周）为止，给用户当天补卡机会。
    """
    today = today or date.today()
    by_date = {log.date: log.count for log in habit.logs}
    target = max(1, habit.target_count)
    today_count = by_date.get(today, 0)
    if habit.period == "weekly":
        week_start = today - timedelta(days=today.weekday())
        period_count = sum(
            count
            for d, count in by_date.items()
            if week_start <= d <= week_start + timedelta(days=6)
        )
        streak = _weekly_streak(by_date, target, week_start)
        done = period_count >= target
    else:
        period_count = today_count
        streak = _daily_streak(by_date, target, today)
        done = today_count >= target
    return {
        "today_count": today_count,
        "period_count": period_count,
        "streak": streak,
        "done_today": done,
    }


def _daily_streak(by_date: dict, target: int, today: date) -> int:
    streak = 0
    cursor = today if by_date.get(today, 0) >= target else today - timedelta(days=1)
    while by_date.get(cursor, 0) >= target:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _weekly_streak(by_date: dict, target: int, this_week_start: date) -> int:
    def week_sum(start: date) -> int:
        return sum(
            count
            for d, count in by_date.items()
            if start <= d <= start + timedelta(days=6)
        )

    streak = 0
    cursor = this_week_start if week_sum(this_week_start) >= target else (
        this_week_start - timedelta(days=7)
    )
    while week_sum(cursor) >= target:
        streak += 1
        cursor -= timedelta(days=7)
    return streak
