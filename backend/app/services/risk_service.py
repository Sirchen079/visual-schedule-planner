"""逾期风险预测：确定性规则打分（不依赖 AI），供 stats API 与晨报共用。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Task, TaskScheduleEntry


def compute_risk(db: Session, limit: int = 10, now: datetime | None = None) -> list[dict]:
    """返回分数最高的前 limit 个未完成风险任务（score>0）。

    规则：逾期 50 分起（按天数加成，最多 +20）；2 天内截止但进度不足半 30 分；
    进行中停滞 3 天以上 20 分；高优先级但完全未安排（无截止且无排期）15 分。
    """
    now = now or datetime.now()
    today = now.date()
    scheduled_ids = set(db.execute(select(TaskScheduleEntry.task_id)).scalars().all())
    tasks = list(
        db.execute(select(Task).where(Task.deleted_at.is_(None))).scalars().all()
    )
    items = []
    for t in tasks:
        if t.status == "完成":
            continue
        score = 0
        reasons = []
        due = t.due_date.date() if t.due_date else None
        if due and due < today:
            days = (today - due).days
            score += 50 + min(days, 10) * 2
            reasons.append(f"已逾期 {days} 天")
        elif due and (due - today).days <= 2 and (t.progress or 0) < 50:
            score += 30
            reasons.append("临近截止但进度不足一半")
        if t.status == "进行中" and t.updated_at and (now - t.updated_at).days >= 3:
            score += 20
            reasons.append(f"进行中但 {(now - t.updated_at).days} 天未更新")
        if t.priority == "高" and not due and t.id not in scheduled_ids:
            score += 15
            reasons.append("高优先级但未安排时间")
        if score > 0:
            items.append(
                {
                    "task_id": t.id,
                    "title": t.title,
                    "priority": t.priority,
                    "status": t.status,
                    "due_date": t.due_date,
                    "progress": t.progress or 0,
                    "score": score,
                    "reasons": reasons,
                }
            )
    items.sort(key=lambda i: i["score"], reverse=True)
    return items[: max(1, limit)]
