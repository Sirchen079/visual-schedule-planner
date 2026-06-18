from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Task


def due_reminders(db: Session, hours: int = 24) -> tuple[list[Task], list[Task]]:
    """返回 (即将到期, 已逾期) 两组未完成、未软删的任务。

    - 即将到期：截止时间在 now ~ now+hours 之间
    - 已逾期：截止时间早于 now
    仅在程序运行时由前端轮询调用，故不依赖后台定时任务。
    """
    now = datetime.now()
    horizon = now + timedelta(hours=max(0, hours))
    stmt = select(Task).where(
        Task.deleted_at.is_(None),
        Task.status != "完成",
        Task.due_date.is_not(None),
    )
    rows = list(db.execute(stmt).scalars().all())
    upcoming = sorted(
        (t for t in rows if now <= t.due_date <= horizon),
        key=lambda t: t.due_date,
    )
    overdue = sorted(
        (t for t in rows if t.due_date < now),
        key=lambda t: t.due_date,
    )
    return upcoming, overdue
