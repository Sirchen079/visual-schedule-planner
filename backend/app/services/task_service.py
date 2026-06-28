from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models import Tag, Task, TaskScheduleEntry
from app.schemas import TaskCreate, TaskUpdate

# 标签柔和调色板，新建标签时循环分配
TAG_COLORS = ["#74ccf2", "#a5f2c1", "#fbbf7a", "#c4a5f2", "#f2a5c4", "#7fd4c4", "#f2d479"]


def _task_query():
    return select(Task).options(
        selectinload(Task.files), selectinload(Task.tags), selectinload(Task.subtasks)
    )


def create_task(db: Session, task: TaskCreate) -> Task:
    data = task.model_dump()
    names = data.pop("tags", [])
    db_task = Task(**data)
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    if names:
        _sync_tags(db, db_task, names)
    return get_task(db, db_task.id) or db_task


def get_task(db: Session, task_id: int) -> Optional[Task]:
    stmt = _task_query().where(Task.id == task_id, Task.deleted_at.is_(None))
    return db.execute(stmt).scalar_one_or_none()


def list_tasks(db: Session) -> list[Task]:
    stmt = (
        _task_query()
        .where(Task.deleted_at.is_(None))
        .order_by(Task.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


def update_task(db: Session, task_id: int, task: TaskUpdate) -> Optional[Task]:
    db_task = get_task(db, task_id)
    if db_task is None:
        return None
    data = task.model_dump(exclude_unset=True)
    names = data.pop("tags", None)
    # progress ↔ status 联动（用户显式值优先；有子任务时进度稍后由完成率覆盖）
    status_set = "status" in data
    progress_set = "progress" in data
    if status_set and data["status"] == "完成" and not progress_set:
        data["progress"] = 100
    if progress_set and data["progress"] == 100 and not status_set:
        data["status"] = "完成"
    for field, value in data.items():
        setattr(db_task, field, value)
    db.commit()
    if names is not None:
        db.refresh(db_task)
        _sync_tags(db, db_task, names)
    # 有子任务时，进度由完成率决定（覆盖手动值）
    db.refresh(db_task)
    sync_progress_from_subtasks(db, db_task)
    return get_task(db, task_id)


def soft_delete_task(db: Session, task_id: int) -> bool:
    db_task = get_task(db, task_id)
    if db_task is None:
        return False
    db_task.deleted_at = datetime.now()
    db.commit()
    return True


# ---- 回收站（软删除可恢复，超期自动清理） ----

def list_trash(db: Session) -> list[Task]:
    stmt = (
        _task_query()
        .where(Task.deleted_at.is_not(None))
        .order_by(Task.deleted_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


def restore_task(db: Session, task_id: int) -> Optional[Task]:
    """把回收站中的任务恢复为正常状态。"""
    stmt = _task_query().where(Task.id == task_id, Task.deleted_at.is_not(None))
    db_task = db.execute(stmt).scalar_one_or_none()
    if db_task is None:
        return None
    db_task.deleted_at = None
    db.commit()
    return get_task(db, task_id)


def purge_task(db: Session, task_id: int) -> bool:
    """彻底删除一个回收站中的任务（不可恢复）。"""
    db_task = db.get(Task, task_id)
    if db_task is None or db_task.deleted_at is None:
        return False
    db.execute(delete(TaskScheduleEntry).where(TaskScheduleEntry.task_id == task_id))
    db.delete(db_task)
    db.commit()
    return True


def purge_expired(db: Session, retain_days: Optional[int] = None) -> int:
    """清理回收站中超过 retain_days 天的任务，返回清理数量。"""
    retain_days = settings.trash_retain_days if retain_days is None else retain_days
    cutoff = datetime.now() - timedelta(days=retain_days)
    rows = list(
        db.execute(
            select(Task).where(Task.deleted_at.is_not(None), Task.deleted_at < cutoff)
        ).scalars().all()
    )
    task_ids = [task.id for task in rows]
    if task_ids:
        db.execute(
            delete(TaskScheduleEntry).where(TaskScheduleEntry.task_id.in_(task_ids))
        )
    for t in rows:
        db.delete(t)
    db.commit()
    return len(rows)


# ---- 标签（按名字 get-or-create，颜色循环分配） ----

def list_tags(db: Session) -> list[Tag]:
    return list(db.execute(select(Tag).order_by(Tag.name)).scalars().all())


def _next_color(db: Session) -> str:
    n = db.execute(select(func.count()).select_from(Tag)).scalar() or 0
    return TAG_COLORS[n % len(TAG_COLORS)]


def _sync_tags(db: Session, task: Task, names: list[str]) -> None:
    """按名字 get-or-create 标签并整体替换任务的标签集合。"""
    clean = list(dict.fromkeys(n.strip() for n in names if n and n.strip()))
    if not clean:
        task.tags = []
        db.commit()
        return
    existing = {
        t.name: t
        for t in db.execute(select(Tag).where(Tag.name.in_(clean))).scalars().all()
    }
    tags = []
    for n in clean:
        if n in existing:
            tags.append(existing[n])
        else:
            t = Tag(name=n, color=_next_color(db))
            db.add(t)
            db.flush()
            tags.append(t)
    task.tags = tags
    db.commit()


def sync_progress_from_subtasks(db: Session, task: Task) -> None:
    """有子任务时按完成率重算进度；全部完成则自动标完成。无子任务则不动。"""
    subs = list(task.subtasks)
    if not subs:
        return
    done = sum(1 for s in subs if s.done)
    task.progress = round(done / len(subs) * 100)
    if task.progress == 100 and task.status != "完成":
        task.status = "完成"
    db.commit()
