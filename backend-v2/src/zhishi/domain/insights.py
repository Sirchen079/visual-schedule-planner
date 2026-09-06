"""幕僚洞察：跨域确定性观察，短句输出（注入系统提示词'幕僚观察'段）。"""
from __future__ import annotations
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from zhishi.domain.models import Task
from zhishi.domain.habits.service import habit_status, list_habits


def compute_insights(db: Session, limit: int = 5) -> list[dict]:
    out: list[dict] = []
    out += _habit_insights(db)
    out += _task_insights(db)
    out.sort(key=lambda x: {"high": 0, "mid": 1, "low": 2}[x["severity"]])
    return out[:limit]


def _habit_insights(db: Session) -> list[dict]:
    out = []
    for habit in list_habits(db):
        st = habit_status(db, habit.id)
        if st["streak"] >= 2 and not st["done_today"]:
            out.append({"kind": "habit_streak_risk", "severity": "mid",
                        "text": f"「{habit.name}」已连续 {st['streak']} 天，今天还没打卡——保住纪录。"})
    return out


def _task_insights(db: Session) -> list[dict]:
    out = []
    soon = datetime.now() + timedelta(days=2)
    tasks = db.scalars(select(Task).where(
        Task.deleted_at.is_(None), Task.status != "done",
        Task.priority == "high", Task.due_date.is_not(None), Task.due_date <= soon)).all()
    for task in tasks:
        has_subs = bool(task.subtasks)
        out.append({"kind": "urgent_unplanned", "severity": "high",
                    "text": f"高优任务「{task.title}」临近截止（{task.due_date:%m-%d}），"
                            f"{'尚无子任务拆解' if not has_subs else '注意检查拆解与排期'}。"})
    return out
