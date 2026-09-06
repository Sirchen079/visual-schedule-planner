"""确定性统计：summary/daily/by_tag/by_priority + 逾期风险分。不依赖 AI。"""
from __future__ import annotations
from datetime import datetime, timedelta
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from zhishi.domain.models import Task


# ---- typed 响应面（openapi 200 schema 定型；字段即各函数回包实形） ----

class StatsSummary(BaseModel):
    """任务面汇总计数。"""
    todo: int
    doing: int
    done: int
    overdue: int
    due_today: int
    due_7d: int


class StatsDailyPoint(BaseModel):
    """单日完成/新建计数（daily 序列项，date 为 YYYY-MM-DD）。"""
    date: str
    completed: int
    created: int


class StatsTagItem(BaseModel):
    """按标签聚合（by-tag 序列项，按 total 降序）。"""
    tag: str
    total: int
    done: int


class StatsPriorityItem(BaseModel):
    """按优先级聚合（by-priority 序列项，fixed high/medium/low）。"""
    priority: str
    todo: int
    doing: int
    done: int


class RiskItem(BaseModel):
    """逾期风险分条目（risk 序列项，score 降序；规则分见 risk）。"""
    task_id: int
    title: str
    score: int
    due_date: str | None = None


def _active(db: Session) -> list[Task]:
    return list(db.scalars(select(Task).where(Task.deleted_at.is_(None))
                           .options(selectinload(Task.tags))))


def summary(db: Session) -> dict:
    tasks = _active(db)
    now = datetime.now()
    week = now + timedelta(days=7)
    return {
        "todo": sum(1 for t in tasks if t.status == "todo"),
        "doing": sum(1 for t in tasks if t.status == "doing"),
        "done": sum(1 for t in tasks if t.status == "done"),
        "overdue": sum(1 for t in tasks if t.due_date and t.due_date < now and t.status != "done"),
        "due_today": sum(1 for t in tasks if t.due_date and t.due_date.date() == now.date()),
        "due_7d": sum(1 for t in tasks if t.due_date and now <= t.due_date <= week),
    }


def daily(db: Session, days: int = 14) -> list[dict]:
    tasks = _active(db)
    span = [(datetime.now() - timedelta(days=i)).date() for i in range(days - 1, -1, -1)]
    return [{"date": d.isoformat(),
             "completed": sum(1 for t in tasks if t.completed_at and t.completed_at.date() == d),
             "created": sum(1 for t in tasks if t.created_at.date() == d)} for d in span]


def by_tag(db: Session) -> list[dict]:
    tasks = _active(db)
    counter: dict[str, dict] = {}
    for t in tasks:
        for tag in t.tags:
            entry = counter.setdefault(tag.name, {"tag": tag.name, "total": 0, "done": 0})
            entry["total"] += 1
            entry["done"] += 1 if t.status == "done" else 0
    return sorted(counter.values(), key=lambda x: -x["total"])


def by_priority(db: Session) -> list[dict]:
    tasks = _active(db)
    return [{"priority": p,
             "todo": sum(1 for t in tasks if t.priority == p and t.status == "todo"),
             "doing": sum(1 for t in tasks if t.priority == p and t.status == "doing"),
             "done": sum(1 for t in tasks if t.priority == p and t.status == "done")}
            for p in ("high", "medium", "low")]


def risk(db: Session, limit: int = 10) -> list[dict]:
    """规则分：逾期 50 起（每满 1 天 +5，至 +20）；2 天内截止且进度<半 30；
    进行中停滞 3 天 20；高优且无截止无排期 15。"""
    now = datetime.now()
    out = []
    for t in _active(db):
        if t.status == "done":
            continue
        score = 0
        if t.due_date and t.due_date < now:
            score = 50 + min(20, int((now - t.due_date).total_seconds() // 86400) * 5)
        elif t.due_date and t.due_date <= now + timedelta(days=2) and t.progress < 50:
            score = 30
        elif t.status == "doing" and now - t.updated_at > timedelta(days=3):
            score = 20
        elif t.priority == "high" and t.due_date is None:
            score = 15
        if score > 0:
            out.append({"task_id": t.id, "title": t.title, "score": score,
                        "due_date": t.due_date.isoformat() if t.due_date else None})
    return sorted(out, key=lambda x: -x["score"])[:limit]
