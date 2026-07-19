"""番茄钟 / 时间记录：计时器生命周期（全局至多一条运行中）+ 时间统计聚合。"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Tag, Task, TimeLog


def current_log(db: Session) -> TimeLog | None:
    stmt = (
        select(TimeLog)
        .where(TimeLog.ended_at.is_(None))
        .order_by(TimeLog.started_at.desc())
    )
    return db.execute(stmt).scalars().first()


def start_timer(db: Session, task: Task, kind: str = "pomodoro") -> TimeLog:
    """开始计时；若已有运行中的计时，先把它停掉（单计时器语义）。"""
    running = current_log(db)
    if running is not None:
        _stop(running, datetime.now())
    log = TimeLog(
        task_id=task.id,
        task_title=task.title,
        kind=kind,
        started_at=datetime.now(),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def stop_timer(db: Session, log_id: int | None = None) -> TimeLog | None:
    """停止计时（缺省停当前运行中的）。返回停止的记录，无运行中则 None。"""
    log = current_log(db) if log_id is None else db.get(TimeLog, log_id)
    if log is None or log.ended_at is not None:
        return None
    _stop(log, datetime.now())
    db.commit()
    db.refresh(log)
    return log


def _stop(log: TimeLog, end: datetime) -> None:
    log.ended_at = end
    seconds = max(0, (end - log.started_at).total_seconds())
    log.minutes = max(1, round(seconds / 60))  # 至少记 1 分钟


def list_logs(db: Session, days: int = 30, task_id: int | None = None) -> list[TimeLog]:
    start = datetime.combine(date.today() - timedelta(days=days - 1), time.min)
    stmt = (
        select(TimeLog)
        .where(TimeLog.started_at >= start, TimeLog.ended_at.is_not(None))
        .order_by(TimeLog.started_at.desc())
    )
    if task_id is not None:
        stmt = stmt.where(TimeLog.task_id == task_id)
    return list(db.execute(stmt).scalars().all())


# ---- 统计：按日序列 / 标签分布 / 任务排行 / 预估 vs 实际 ----
def time_stats(db: Session, days: int = 30) -> dict:
    today = date.today()
    start_day = today - timedelta(days=days - 1)
    logs = list_logs(db, days)

    daily_map: dict[date, int] = {}
    task_map: dict[tuple, int] = {}
    total = 0
    for log in logs:
        d = log.started_at.date()
        daily_map[d] = daily_map.get(d, 0) + log.minutes
        key = (log.task_id, log.task_title)
        task_map[key] = task_map.get(key, 0) + log.minutes
        total += log.minutes
    daily = [
        {"date": start_day + timedelta(days=i), "minutes": daily_map.get(start_day + timedelta(days=i), 0)}
        for i in range(days)
    ]
    by_task = [
        {"task_id": k[0], "title": k[1], "minutes": v}
        for k, v in sorted(task_map.items(), key=lambda kv: kv[1], reverse=True)[:10]
    ]

    # 标签分布：按任务当前标签归属分摊（任务已删则计入「无标签」）
    tag_map: dict[str, dict] = {}
    task_ids = {log.task_id for log in logs if log.task_id is not None}
    tasks_by_id = {}
    if task_ids:
        rows = db.execute(
            select(Task).options(selectinload(Task.tags)).where(Task.id.in_(task_ids))
        ).scalars().all()
        tasks_by_id = {t.id: t for t in rows}
    untagged = {"name": "无标签", "color": "#9db8c7", "minutes": 0}
    for log in logs:
        task = tasks_by_id.get(log.task_id)
        tags = list(task.tags) if task else []
        if not tags:
            untagged["minutes"] += log.minutes
            continue
        share = log.minutes / len(tags)
        for tag in tags:
            bucket = tag_map.setdefault(tag.name, {"name": tag.name, "color": tag.color, "minutes": 0})
            bucket["minutes"] += share
    by_tag = sorted(tag_map.values(), key=lambda b: b["minutes"], reverse=True)
    if untagged["minutes"] > 0:
        by_tag.append(untagged)
    for bucket in by_tag:
        bucket["minutes"] = round(bucket["minutes"])

    # 预估 vs 实际：窗口内有计时且设了预估的任务
    estimates = []
    for (task_id, title), minutes in sorted(task_map.items(), key=lambda kv: kv[1], reverse=True):
        task = tasks_by_id.get(task_id)
        if task and task.estimated_minutes:
            estimates.append(
                {
                    "task_id": task.id,
                    "title": task.title,
                    "estimated_minutes": task.estimated_minutes,
                    "actual_minutes": minutes,
                }
            )
    return {
        "daily": daily,
        "by_tag": by_tag[:8],
        "by_task": by_task,
        "estimates": estimates[:10],
        "total_minutes": total,
    }
