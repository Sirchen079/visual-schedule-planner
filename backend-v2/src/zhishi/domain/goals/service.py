"""OKR：KR 三种进度模式——manual 手动填值；tag_task_count 标签任务完成数；
habit_checkins 习惯打卡数（后两类实时滚动计算）。"""
from __future__ import annotations
from datetime import date, datetime, time as dtime
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from zhishi.domain.models import Goal, Habit, HabitLog, KeyResult, Tag, Task
from zhishi.domain.goals.schemas import GoalCreate, KeyResultCreate


def create_goal(db: Session, payload: GoalCreate) -> Goal:
    goal = Goal(**payload.model_dump())
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def get_goal(db: Session, goal_id: int, include_deleted: bool = False) -> Goal:
    stmt = select(Goal).where(Goal.id == goal_id).options(selectinload(Goal.key_results))
    if not include_deleted:
        stmt = stmt.where(Goal.deleted_at.is_(None))
    goal = db.scalar(stmt)
    if goal is None:
        raise LookupError(f"goal {goal_id} 不存在")
    return goal


def list_goals(db: Session, include_deleted: bool = False) -> list[Goal]:
    """include_deleted 只控制「是否含软删行」——已删行 status 保持原值，以 deleted_at 辨识
    （参数语义由 include_archived 改名对齐，行为不再混入归档含义）。"""
    stmt = select(Goal).options(selectinload(Goal.key_results))
    if not include_deleted:
        stmt = stmt.where(Goal.deleted_at.is_(None))
    return list(db.scalars(stmt.order_by(Goal.sort_order, Goal.id)))


def list_trash(db: Session) -> list[Goal]:
    return list(db.scalars(select(Goal).where(Goal.deleted_at.is_not(None))
                           .options(selectinload(Goal.key_results))
                           .order_by(Goal.deleted_at.desc())))


def update_goal(db: Session, goal_id: int, **fields) -> Goal:
    goal = get_goal(db, goal_id)
    for key, value in fields.items():
        if value is not None:
            setattr(goal, key, value)
    db.commit()
    db.refresh(goal)
    return goal


def delete_goal(db: Session, goal_id: int) -> None:
    get_goal(db, goal_id).deleted_at = datetime.now()
    db.commit()


def restore_goal(db: Session, goal_id: int) -> Goal:
    goal = get_goal(db, goal_id, include_deleted=True)
    goal.deleted_at = None
    db.commit()
    db.refresh(goal)
    return goal


def purge_goal(db: Session, goal_id: int) -> None:
    """硬删目标（对齐 tasks 回收站模式）：仅回收站中的可 purge；
    key_results 随 ORM cascade（all, delete-orphan）级联删除。"""
    goal = get_goal(db, goal_id, include_deleted=True)
    if goal.deleted_at is None:
        raise ValueError("目标不在回收站，须先软删除再 purge")
    db.delete(goal)
    db.commit()


def add_key_result(db: Session, goal_id: int, payload: KeyResultCreate) -> KeyResult:
    get_goal(db, goal_id)
    kr = KeyResult(goal_id=goal_id, **payload.model_dump())
    db.add(kr)
    db.commit()
    db.refresh(kr)
    return kr


def update_kr_progress(db: Session, kr_id: int, *, current_value: float) -> KeyResult:
    kr = db.get(KeyResult, kr_id)
    if kr is None:
        raise LookupError(f"kr {kr_id} 不存在")
    kr.current_value = current_value
    db.commit()
    db.refresh(kr)
    return kr


def delete_key_result(db: Session, kr_id: int) -> None:
    kr = db.get(KeyResult, kr_id)
    if kr is None:
        raise LookupError(f"kr {kr_id} 不存在")
    db.delete(kr)
    db.commit()


def _period_bounds(goal: Goal) -> tuple[datetime, datetime]:
    start = datetime.combine(goal.start_date or date(1970, 1, 1), dtime.min)
    end = datetime.combine(goal.end_date or date(2999, 12, 31), dtime.max)
    return start, end


def kr_progress(db: Session, kr: KeyResult) -> tuple[float, int]:
    """返回 (current_value, progress 0-100)。自动类 KR 实时算。"""
    goal = kr.goal
    if kr.kind == "tag_task_count":
        start, end = _period_bounds(goal)
        stmt = (select(Task.id).join(Task.tags).where(
            Task.deleted_at.is_(None), Task.status == "done",
            Task.completed_at.between(start, end), Tag.name == kr.link))
        current = float(len(db.scalars(stmt).all()))
    elif kr.kind == "habit_checkins":
        current = _habit_checkins(db, kr, goal)
    else:
        current = kr.current_value
    pct = 0 if kr.target_value <= 0 else min(100, round(current / kr.target_value * 100))
    return current, pct


def _habit_checkins(db: Session, kr: KeyResult, goal: Goal) -> float:
    start, end = _period_bounds(goal)
    habit = db.scalar(select(Habit).where(Habit.name == kr.link, Habit.deleted_at.is_(None)))
    if habit is None:
        return 0.0
    logs = db.scalars(select(HabitLog).where(
        HabitLog.habit_id == habit.id,
        HabitLog.date.between(start.date(), end.date()))).all()
    return float(sum(l.count for l in logs))


def goal_progress(db: Session, goal_id: int) -> list[dict]:
    get_goal(db, goal_id)
    # 直接查表：add_key_result 只写外键，同会话早期 selectinload 的集合不会刷新
    krs = list(db.scalars(select(KeyResult).where(KeyResult.goal_id == goal_id)))
    out = []
    for kr in krs:
        current, pct = kr_progress(db, kr)
        out.append({"kr_id": kr.id, "title": kr.title, "kind": kr.kind,
                    "target_value": kr.target_value, "current_value": current,
                    "unit": kr.unit, "progress": pct})
    return out
