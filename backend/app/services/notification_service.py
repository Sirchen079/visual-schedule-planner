"""通知中心：到点提醒触发记录（幂等）+ 未读/已读管理。

触发仍由前端轮询 /reminders/due 驱动（无后台定时器）：
每次轮询命中 triggered 提醒时，按 (task_id, remind_at) 唯一约束幂等落库，
错过的提醒留在通知中心可回溯、可标记已读。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import NotificationLog


def _offset_label(minutes: int) -> str:
    if minutes <= 0:
        return "截止时"
    if minutes < 60:
        return f"提前 {minutes} 分钟"
    if minutes < 1440:
        hours = minutes // 60
        return f"提前 {hours} 小时"
    days = minutes // 1440
    return f"提前 {days} 天"


def log_triggered(db: Session, triggered: list[dict], now: datetime | None = None) -> int:
    """把 /reminders/due 的 triggered 项幂等落库，返回新增条数。"""
    created = 0
    for item in triggered:
        task = item["task"]
        exists = db.execute(
            select(NotificationLog.id).where(
                NotificationLog.task_id == task.id,
                NotificationLog.remind_at == item["remind_at"],
            )
        ).scalar_one_or_none()
        if exists is not None:
            continue
        due_at = item["due_at"]
        entry = NotificationLog(
            task_id=task.id,
            kind="reminder",
            title=task.title,
            body=f"截止 {due_at.strftime('%m-%d %H:%M')} · {_offset_label(item['offset_minutes'])}",
            remind_at=item["remind_at"],
        )
        db.add(entry)
        created += 1
    if created:
        db.commit()
    return created


def list_notifications(db: Session, limit: int = 50) -> list[NotificationLog]:
    stmt = (
        select(NotificationLog)
        .order_by(NotificationLog.created_at.desc(), NotificationLog.id.desc())
        .limit(max(1, min(limit, 200)))
    )
    return list(db.execute(stmt).scalars().all())


def unread_count(db: Session) -> int:
    return db.execute(
        select(func.count())
        .select_from(NotificationLog)
        .where(NotificationLog.read_at.is_(None))
    ).scalar() or 0


def mark_read(db: Session, notification_id: int) -> NotificationLog | None:
    entry = db.get(NotificationLog, notification_id)
    if entry is None:
        return None
    if entry.read_at is None:
        entry.read_at = datetime.now()
        db.commit()
        db.refresh(entry)
    return entry


def mark_all_read(db: Session) -> int:
    result = db.execute(
        update(NotificationLog)
        .where(NotificationLog.read_at.is_(None))
        .values(read_at=datetime.now())
    )
    db.commit()
    return result.rowcount or 0
