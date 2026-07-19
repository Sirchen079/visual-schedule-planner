"""OKR 目标管理：目标 CRUD + KR 三种进度模式（手动 / 标签任务完成数 / 习惯打卡数）。"""
from __future__ import annotations

import json
from datetime import date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Goal, HabitLog, KeyResult, Tag, Task
from app.schemas import GoalCreate, GoalUpdate, KeyResultCreate, KeyResultUpdate


def _goal_query():
    return select(Goal).options(selectinload(Goal.key_results))


def create_goal(db: Session, payload: GoalCreate) -> Goal:
    data = payload.model_dump()
    krs = data.pop("key_results", [])
    goal = Goal(**data)
    db.add(goal)
    db.flush()
    for kr in krs:
        _add_kr(db, goal.id, KeyResultCreate(**kr))
    db.commit()
    return get_goal(db, goal.id)


def get_goal(db: Session, goal_id: int) -> Goal | None:
    stmt = _goal_query().where(Goal.id == goal_id, Goal.deleted_at.is_(None))
    return db.execute(stmt).scalar_one_or_none()


def list_goals(db: Session, include_archived: bool = False) -> list[Goal]:
    stmt = _goal_query().where(Goal.deleted_at.is_(None))
    if not include_archived:
        stmt = stmt.where(Goal.status != "archived")
    stmt = stmt.order_by(Goal.sort_order.asc(), Goal.created_at.desc(), Goal.id.desc())
    return list(db.execute(stmt).scalars().all())


def update_goal(db: Session, goal_id: int, payload: GoalUpdate) -> Goal | None:
    goal = get_goal(db, goal_id)
    if goal is None:
        return None
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(goal, field, value)
    db.commit()
    return get_goal(db, goal_id)


def soft_delete_goal(db: Session, goal_id: int) -> bool:
    goal = get_goal(db, goal_id)
    if goal is None:
        return False
    goal.deleted_at = datetime.now()
    db.commit()
    return True


def add_key_result(db: Session, goal_id: int, payload: KeyResultCreate) -> KeyResult | None:
    if get_goal(db, goal_id) is None:
        return None
    kr = _add_kr(db, goal_id, payload)
    db.commit()
    db.refresh(kr)
    return kr


def _add_kr(db: Session, goal_id: int, payload: KeyResultCreate) -> KeyResult:
    data = payload.model_dump()
    data["link"] = json.dumps(data.pop("link", {}) or {}, ensure_ascii=False)
    kr = KeyResult(goal_id=goal_id, **data)
    db.add(kr)
    db.flush()
    return kr


def update_key_result(
    db: Session, kr_id: int, payload: KeyResultUpdate
) -> KeyResult | None:
    kr = db.get(KeyResult, kr_id)
    if kr is None:
        return None
    data = payload.model_dump(exclude_unset=True)
    if "link" in data:
        data["link"] = json.dumps(data["link"] or {}, ensure_ascii=False)
    # current_value 只允许手动类 KR 直接改
    if "current_value" in data and kr.kind != "manual":
        data.pop("current_value")
    for field, value in data.items():
        setattr(kr, field, value)
    db.commit()
    db.refresh(kr)
    return kr


def delete_key_result(db: Session, kr_id: int) -> bool:
    kr = db.get(KeyResult, kr_id)
    if kr is None:
        return False
    db.delete(kr)
    db.commit()
    return True


# ---- 进度计算 ----
def kr_progress(db: Session, kr: KeyResult, goal: Goal | None = None) -> tuple[float, int]:
    """返回 (current_value, progress 0-100)。自动类 KR 实时计算 current。"""
    current = kr.current_value
    if kr.kind == "tag_task_count":
        current = _count_tag_completed(db, kr, goal)
    elif kr.kind == "habit_checkins":
        current = _count_habit_checkins(db, kr, goal)
    target = kr.target_value or 1
    progress = min(100, round(current / target * 100))
    return current, progress


def goal_progress(db: Session, goal: Goal) -> int:
    krs = list(goal.key_results)
    if not krs:
        return 0
    return round(sum(kr_progress(db, kr, goal)[1] for kr in krs) / len(krs))


def _kr_link(kr: KeyResult) -> dict:
    try:
        value = json.loads(kr.link or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _period_bounds(goal: Goal | None) -> tuple[datetime | None, datetime | None]:
    if goal is None:
        return None, None
    start = datetime.combine(goal.start_date, time.min) if goal.start_date else None
    end = datetime.combine(goal.end_date, time.max) if goal.end_date else None
    return start, end


def _count_tag_completed(db: Session, kr: KeyResult, goal: Goal | None) -> float:
    tag_name = str(_kr_link(kr).get("tag") or "").strip()
    if not tag_name:
        return 0
    stmt = (
        select(func.count())
        .select_from(Task)
        .join(Tag, Task.tags)
        .where(Task.deleted_at.is_(None), Task.status == "完成", Tag.name == tag_name)
    )
    start, end = _period_bounds(goal)
    if start:
        stmt = stmt.where(Task.completed_at >= start)
    if end:
        stmt = stmt.where(Task.completed_at <= end)
    return float(db.execute(stmt).scalar() or 0)


def _count_habit_checkins(db: Session, kr: KeyResult, goal: Goal | None) -> float:
    habit_id = _kr_link(kr).get("habit_id")
    if not habit_id:
        return 0
    stmt = select(func.coalesce(func.sum(HabitLog.count), 0)).where(
        HabitLog.habit_id == int(habit_id)
    )
    if goal and goal.start_date:
        stmt = stmt.where(HabitLog.date >= goal.start_date)
    if goal and goal.end_date:
        stmt = stmt.where(HabitLog.date <= goal.end_date)
    return float(db.execute(stmt).scalar() or 0)
