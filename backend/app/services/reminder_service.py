from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Task


def effective_due(task: Task) -> datetime | None:
    """有效截止时间：due_date 与 due_time 组合；无 due_time 时保持 due_date 原样。

    （纯日期任务沿用旧行为：按日期当天 0 点参与比较，避免破坏既有 UX。）
    """
    if not task.due_date:
        return None
    if not task.due_time:
        return task.due_date
    try:
        hour, minute = (int(part) for part in task.due_time.split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except (ValueError, AttributeError):
        return task.due_date
    return task.due_date.replace(hour=hour, minute=minute, second=0, microsecond=0)


def due_reminders(
    db: Session, hours: int = 24, now: datetime | None = None
) -> tuple[list[Task], list[Task]]:
    """返回 (即将到期, 已逾期) 两组未完成、未软删的任务。

    - 即将到期：有效截止时间在 now ~ now+hours 之间
    - 已逾期：有效截止时间早于 now
    仅在程序运行时由前端轮询调用，故不依赖后台定时任务。
    """
    now = _comparison_time(now or datetime.now())
    horizon = now + timedelta(hours=max(0, hours))
    stmt = select(Task).where(
        Task.deleted_at.is_(None),
        Task.status != "完成",
        Task.due_date.is_not(None),
    )
    rows = list(db.execute(stmt).scalars().all())
    upcoming = sorted(
        (t for t in rows if now <= _comparison_time(effective_due(t)) <= horizon),
        key=lambda t: _comparison_time(effective_due(t)),
    )
    overdue = sorted(
        (t for t in rows if _comparison_time(effective_due(t)) < now),
        key=lambda t: _comparison_time(effective_due(t)),
    )
    return upcoming, overdue


def triggered_reminders(db: Session, now: datetime | None = None) -> list[dict]:
    """到点提醒：按任务 remind_offsets 展开，命中 [remind_at, 截止] 窗口的提醒项。

    remind_at = 有效截止 - 偏移分钟；偏移为 0 即「截止时」。
    返回项按截止时间升序；调用方（前端轮询）负责按 task_id+remind_at 去重。
    """
    now = _comparison_time(now or datetime.now())
    stmt = select(Task).where(
        Task.deleted_at.is_(None),
        Task.status != "完成",
        Task.due_date.is_not(None),
    )
    items = []
    for task in db.execute(stmt).scalars().all():
        due = _comparison_time(effective_due(task))
        if due is None or due < now:
            continue
        for offset in task.remind_offsets:
            remind_at = due - timedelta(minutes=offset)
            if remind_at <= now <= due:
                items.append(
                    {
                        "task": task,
                        "remind_at": remind_at,
                        "due_at": due,
                        "offset_minutes": offset,
                    }
                )
    items.sort(key=lambda item: item["due_at"])
    return items


def _comparison_time(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.replace(tzinfo=None)
