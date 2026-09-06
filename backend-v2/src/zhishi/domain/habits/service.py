"""习惯打卡：当天幂等累加；streak 今天未达标不打断（算到昨天，给补卡机会）。"""
from __future__ import annotations
from datetime import date, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from zhishi.domain.models import Habit, HabitLog
from zhishi.domain.habits.schemas import HabitCreate


def create_habit(db: Session, payload: HabitCreate) -> Habit:
    habit = Habit(**payload.model_dump())
    db.add(habit)
    db.commit()
    db.refresh(habit)
    return habit


def delete_habit(db: Session, habit_id: int) -> None:
    habit = db.get(Habit, habit_id)
    if habit is None or habit.deleted_at is not None:
        raise LookupError(f"habit {habit_id} 不存在")
    habit.deleted_at = date.today()
    db.commit()


def list_habits(db: Session) -> list[Habit]:
    return list(db.scalars(select(Habit).where(Habit.deleted_at.is_(None))
                           .order_by(Habit.sort_order, Habit.id)))


def _get_log(db: Session, habit_id: int, day: date) -> HabitLog | None:
    return db.scalar(select(HabitLog).where(HabitLog.habit_id == habit_id, HabitLog.date == day))


def check_in(db: Session, habit_id: int, day: date | None = None) -> HabitLog:
    habit = db.get(Habit, habit_id)
    if habit is None or habit.deleted_at is not None:
        raise LookupError(f"habit {habit_id} 不存在")
    day = day or date.today()
    log = _get_log(db, habit_id, day)
    if log is None:
        log = HabitLog(habit_id=habit_id, date=day, count=0)
        db.add(log)
    log.count += 1
    db.commit()
    db.refresh(log)
    return log


def uncheck(db: Session, habit_id: int, day: date) -> None:
    log = _get_log(db, habit_id, day)
    if log is None:
        return
    log.count -= 1
    if log.count <= 0:
        db.delete(log)
    db.commit()


def list_logs(db: Session, habit_id: int, days: int = 30) -> list[HabitLog]:
    since = date.today() - timedelta(days=days)
    return list(db.scalars(select(HabitLog).where(
        HabitLog.habit_id == habit_id, HabitLog.date >= since).order_by(HabitLog.date)))


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _daily_streak(by_date: dict[date, int], target: int, today: date) -> int:
    cursor = today if by_date.get(today, 0) >= target else today - timedelta(days=1)
    streak = 0
    while by_date.get(cursor, 0) >= target:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _weekly_streak(by_date: dict[date, int], target: int, today: date) -> int:
    def week_sum(ws: date) -> int:
        return sum(c for d, c in by_date.items() if ws <= d < ws + timedelta(days=7))
    this_week = _week_start(today)
    cursor = this_week if week_sum(this_week) >= target else this_week - timedelta(days=7)
    streak = 0
    while week_sum(cursor) >= target:
        streak += 1
        cursor -= timedelta(days=7)
    return streak


def habit_status(db: Session, habit_id: int) -> dict:
    habit = db.get(Habit, habit_id)
    if habit is None or habit.deleted_at is not None:
        raise LookupError(f"habit {habit_id} 不存在")
    today = date.today()
    logs = {l.date: l.count for l in list_logs(db, habit_id, days=400)}
    if habit.period == "weekly":
        streak = _weekly_streak(logs, habit.target_count, today)
        period_count = sum(c for d, c in logs.items()
                           if _week_start(today) <= d < _week_start(today) + timedelta(days=7))
    else:
        streak = _daily_streak(logs, habit.target_count, today)
        period_count = logs.get(today, 0)
    return {"today_count": logs.get(today, 0), "period_count": period_count,
            "streak": streak, "done_today": logs.get(today, 0) >= habit.target_count}
