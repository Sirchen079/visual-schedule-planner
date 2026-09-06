# src/zhishi/domain/notifications.py
"""Task reminders, scanned every 30s while the backend runs.

The durable scan cursor recovers up to seven days after sleep or restart.
Older missed offsets collapse to the latest one per task to avoid a backlog storm.
"""
from __future__ import annotations
import json
import re
from datetime import datetime, timedelta
from sqlalchemy import select, update, func
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session
from zhishi.domain.models import AppSetting, Event, NotificationLog, Task

SCAN_WINDOW_MINUTES = 35  # 覆盖两次扫描间隔，宁可重扫靠幂等去重
CURSOR_KEY = "task_reminder_scan_at"
MAX_CATCHUP_DAYS = 7


def _deadline(task: Task) -> datetime | None:
    if task.due_date is None or task.status == "done":
        return None
    if task.due_time:
        # Invalid imported legacy values must not break every other reminder.
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", task.due_time):
            return None
        hour, minute = map(int, task.due_time.split(":"))
        return task.due_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return task.due_date


def _due_points(task: Task) -> list[datetime]:
    due = _deadline(task)
    if due is None:
        return []
    try:
        offsets = json.loads(task.remind_offsets or "[]")
    except (ValueError, TypeError):
        return []
    if not isinstance(offsets, list):
        return []
    points = []
    for m in offsets:
        if type(m) is int and 0 <= m <= 525600:
            try:
                points.append(due - timedelta(minutes=m))
            except OverflowError:
                continue
    return sorted(set(points))


def record_due_reminders(db: Session, now: datetime | None = None) -> int:
    """把已到点未落的提醒写进 notification_logs，返回新增条数。幂等。"""
    now = now or datetime.now()
    horizon = now - timedelta(minutes=SCAN_WINDOW_MINUTES)
    saved = db.get(AppSetting, CURSOR_KEY)
    if saved:
        try:
            last = datetime.fromisoformat(saved.value)
            if last.tzinfo is None:
                horizon = max(now - timedelta(days=MAX_CATCHUP_DAYS), min(horizon, last))
        except ValueError:
            pass
    created = 0
    tasks = db.scalars(select(Task).where(Task.deleted_at.is_(None))).all()
    for task in tasks:
        due = _deadline(task)
        points = [point for point in _due_points(task) if horizon <= point <= now]
        cutoff = now - timedelta(minutes=SCAN_WINDOW_MINUTES)
        missed = [point for point in points if point < cutoff]
        recent = [point for point in points if point >= cutoff]
        # When a recent reminder exists it already supersedes old missed offsets.
        selected = recent or missed[-1:]
        for point in selected:
            label = "补发提醒" if point < cutoff else "提醒"
            result = db.execute(insert(NotificationLog).values(
                task_id=task.id, kind="reminder", title=task.title,
                body=f"{task.title} · {label}（截止 {due:%m-%d %H:%M}）",
                target_path=f"/board?task={task.id}", remind_at=point,
            ).on_conflict_do_nothing(index_elements=["task_id", "remind_at"]))
            created += result.rowcount
    created += _record_event_reminders(db, now, horizon)
    # Cursor and reminders commit together: a failed scan never advances the cursor.
    db.execute(insert(AppSetting).values(key=CURSOR_KEY, value=now.isoformat()).on_conflict_do_update(
        index_elements=["key"], set_={"value": now.isoformat(), "updated_at": now}))
    db.commit()
    return created


def _record_event_reminders(db: Session, now: datetime, horizon: datetime) -> int:
    from zhishi.domain.schedule.schemas import reminder_recurrence_supported
    from zhishi.domain.schedule.service import _expand_one, event_reminder_offsets
    cutoff = now - timedelta(minutes=SCAN_WINDOW_MINUTES)
    created = 0
    for event in db.scalars(select(Event).where(Event.remind_offsets != '[]')):
        offsets = event_reminder_offsets(event)
        clock = event.start_time or event.reminder_time
        if not offsets or not clock or not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', clock):
            continue
        if not reminder_recurrence_supported(event.recur_rrule):
            continue  # Invalid legacy data must never stall reminders for other events.
        try:
            latest = now + timedelta(minutes=max(offsets))
            days = set(_expand_one(event, horizon.date(), latest.date()))
            hour, minute = map(int, clock.split(':'))
            points = []
            for day in days:
                begins = datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute)
                for offset in offsets:
                    point = begins - timedelta(minutes=offset)
                    if horizon <= point <= now:
                        points.append((point, begins))
        except (ValueError, TypeError, OverflowError):
            continue
        points.sort()
        recent = [pair for pair in points if pair[0] >= cutoff]
        # One most recent missed notification per recurring event after a long absence.
        for point, begins in recent or points[-1:]:
            label = '补发提醒' if point < cutoff else '提醒'
            location = f' · {event.location}' if event.location else ''
            identity = f'event:{event.id}:{event.created_at.isoformat()}:{begins.isoformat()}:{point.isoformat()}'
            result = db.execute(insert(NotificationLog).values(
                kind='event_reminder', title=event.title, dedupe_key=identity,
                body=f'{event.title} · {label}（日程 {begins:%m-%d %H:%M}）{location}',
                target_path=f'/calendar?date={begins:%Y-%m-%d}&event={event.id}', remind_at=point,
            ).on_conflict_do_nothing(index_elements=['dedupe_key']))
            created += result.rowcount
    return created


def list_notifications(db: Session, limit: int = 50) -> list[NotificationLog]:
    return list(db.scalars(select(NotificationLog).order_by(
        NotificationLog.remind_at.desc(), NotificationLog.id.desc()).limit(limit)))


def unread_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(NotificationLog).where(
        NotificationLog.read_at.is_(None))) or 0


def mark_read(db: Session, notification_id: int | None = None) -> None:
    if notification_id is not None:
        log = db.get(NotificationLog, notification_id)
        if log is not None and log.read_at is None:
            log.read_at = datetime.now()
    else:
        db.execute(update(NotificationLog).where(NotificationLog.read_at.is_(None)).values(
            read_at=datetime.now()))
    db.commit()
