"""番茄钟：全局至多一条运行中（新计时先停旧的）；统计聚合。"""
from __future__ import annotations
from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy import select
from sqlalchemy.orm import Session
from zhishi.domain.models import TimeLog
from zhishi.domain.focus.schemas import TimerStart


def current_log(db: Session) -> TimeLog | None:
    return db.scalar(select(TimeLog).where(TimeLog.ended_at.is_(None)))


def _stop(db: Session, log: TimeLog, end: datetime) -> TimeLog:
    log.ended_at = end
    log.minutes = max(0, int((end - log.started_at).total_seconds() // 60))
    return log


def start_timer(db: Session, payload: TimerStart) -> TimeLog:
    running = current_log(db)
    if running is not None:
        _stop(db, running, datetime.now())
    log = TimeLog(task_id=payload.task_id, task_title=payload.task_title,
                  kind=payload.kind, started_at=datetime.now())
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def stop_timer(db: Session, log_id: int | None) -> TimeLog | None:
    log = db.get(TimeLog, log_id) if log_id else current_log(db)
    if log is None or log.ended_at is not None:
        return None
    _stop(db, log, datetime.now())
    db.commit()
    db.refresh(log)
    return log


def list_logs(db: Session, days: int = 7, task_id: int | None = None) -> list[TimeLog]:
    since = datetime.now() - timedelta(days=days)
    stmt = select(TimeLog).where(TimeLog.started_at >= since)
    if task_id:
        stmt = stmt.where(TimeLog.task_id == task_id)
    return list(db.scalars(stmt.order_by(TimeLog.started_at.desc())))


def time_stats(db: Session, days: int = 7) -> dict:
    logs = [l for l in list_logs(db, days=days) if l.ended_at is not None]
    by_day: dict[str, int] = defaultdict(int)
    by_task: dict[str, int] = defaultdict(int)
    for l in logs:
        by_day[l.started_at.date().isoformat()] += l.minutes
        by_task[l.task_title or "未命名"] += l.minutes
    span = [(datetime.now() - timedelta(days=i)).date().isoformat() for i in range(days - 1, -1, -1)]
    return {
        "by_day": [{"date": d, "minutes": by_day.get(d, 0)} for d in span],
        "by_task": [{"task_title": t, "minutes": m}
                    for t, m in sorted(by_task.items(), key=lambda x: -x[1])],
        "total_minutes": sum(l.minutes for l in logs),
    }
