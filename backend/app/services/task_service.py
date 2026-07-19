from datetime import datetime, timedelta
import calendar
import json
from typing import Optional

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models import Subtask, Tag, Task, TaskScheduleEntry
from app.schemas import TaskCreate, TaskUpdate

# 标签柔和调色板，新建标签时循环分配
TAG_COLORS = ["#74ccf2", "#a5f2c1", "#fbbf7a", "#c4a5f2", "#f2a5c4", "#7fd4c4", "#f2d479"]


def _task_query():
    return select(Task).options(
        selectinload(Task.files), selectinload(Task.tags), selectinload(Task.subtasks)
    )


def _serialize_remind_offsets(value: object) -> str:
    """提醒偏移分钟列表 → 去重排序后的 JSON 字符串（入库格式）。"""
    clean: set[int] = set()
    if isinstance(value, (list, tuple)):
        for v in value:
            try:
                clean.add(max(0, int(v)))
            except (TypeError, ValueError):
                continue
    return json.dumps(sorted(clean))


def create_task(db: Session, task: TaskCreate) -> Task:
    data = task.model_dump()
    names = data.pop("tags", [])
    data["remind_offsets_json"] = _serialize_remind_offsets(data.pop("remind_offsets", []))
    db_task = Task(**data)
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    if names:
        _sync_tags(db, db_task, names)
    # 直接以「完成」状态创建的任务同样视为进入完成态（打点 + 重复任务生成）
    if db_task.status == "完成" and db_task.completed_at is None:
        _on_task_completed(db, db_task)
    return get_task(db, db_task.id) or db_task


def get_task(db: Session, task_id: int) -> Optional[Task]:
    stmt = _task_query().where(Task.id == task_id, Task.deleted_at.is_(None))
    return db.execute(stmt).scalar_one_or_none()


def list_tasks(
    db: Session,
    q: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    tag: Optional[str] = None,
    due_before: Optional[datetime] = None,
    due_after: Optional[datetime] = None,
    sort: str = "created_at",
    order: str = "desc",
) -> list[Task]:
    """任务列表；全部参数可选，不传时行为与旧版一致（按创建时间倒序）。"""
    stmt = _task_query().where(Task.deleted_at.is_(None))
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Task.title.ilike(like), Task.notes.ilike(like)))
    if status:
        stmt = stmt.where(Task.status == status)
    if priority:
        stmt = stmt.where(Task.priority == priority)
    if tag:
        stmt = stmt.where(Task.tags.any(Tag.name == tag))
    if due_before is not None:
        stmt = stmt.where(Task.due_date.is_not(None), Task.due_date <= due_before)
    if due_after is not None:
        stmt = stmt.where(Task.due_date.is_not(None), Task.due_date >= due_after)
    if sort == "created_at":
        # 默认序：手动排序权重升序优先（0 为未排序），再按创建时间，id 决胜保确定
        stmt = stmt.order_by(
            Task.sort_order.asc(),
            Task.created_at.desc() if order == "desc" else Task.created_at.asc(),
            Task.id.desc() if order == "desc" else Task.id.asc(),
        )
        return list(db.execute(stmt).scalars().all())
    sort_col = {
        "due_date": Task.due_date,
        "priority": Task.priority,
    }.get(sort, Task.created_at)
    stmt = stmt.order_by(sort_col.asc() if order == "asc" else sort_col.desc())
    return list(db.execute(stmt).scalars().all())


def update_task(db: Session, task_id: int, task: TaskUpdate) -> Optional[Task]:
    db_task = get_task(db, task_id)
    if db_task is None:
        return None
    data = task.model_dump(exclude_unset=True)
    names = data.pop("tags", None)
    if "remind_offsets" in data:
        data["remind_offsets_json"] = _serialize_remind_offsets(
            data.pop("remind_offsets")
        )
    was_completed = db_task.status == "完成"
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
    db.refresh(db_task)
    # 完成态迁移：进入完成 → 打点（重复任务生成下一实例）；重新打开 → 清空
    if db_task.status == "完成" and not was_completed and db_task.completed_at is None:
        _on_task_completed(db, db_task)
    elif db_task.status != "完成" and was_completed:
        db_task.completed_at = None
        db.commit()
    return get_task(db, task_id)


# ---- 重复任务（完成时惰性生成下一实例，不预生成未来序列） ----


def next_occurrence(
    due: datetime, rule: str, interval: int = 1, after: Optional[datetime] = None
) -> Optional[datetime]:
    """按重复规则推进截止时间。

    从原截止时间推进；若结果落在 after（默认今天 0 点）之前则继续推进，
    避免补完逾期任务时生成一个已经逾期的新实例。
    """
    interval = max(1, int(interval or 1))
    candidate = _advance(due, rule, interval)
    if candidate is None:
        return None
    floor = (after or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    guard = 0
    while candidate < floor and guard < 500:
        stepped = _advance(candidate, rule, interval)
        if stepped is None or stepped <= candidate:
            break
        candidate = stepped
        guard += 1
    return candidate


def _advance(due: datetime, rule: str, interval: int) -> Optional[datetime]:
    if rule == "daily":
        return due + timedelta(days=interval)
    if rule == "weekdays":
        current, remaining = due, interval
        while remaining > 0:
            current += timedelta(days=1)
            if current.weekday() < 5:
                remaining -= 1
        return current
    if rule == "weekly":
        return due + timedelta(weeks=interval)
    if rule == "monthly":
        month_index = due.month - 1 + interval
        year = due.year + month_index // 12
        month = month_index % 12 + 1
        day = min(due.day, calendar.monthrange(year, month)[1])
        return due.replace(year=year, month=month, day=day)
    return None


def _on_task_completed(db: Session, task: Task) -> None:
    """任务进入完成态：打完成时间戳；重复任务惰性生成下一实例。"""
    task.completed_at = datetime.now()
    db.commit()
    if task.recur_rule and task.recur_rule != "none" and task.due_date:
        spawn_next_occurrence(db, task)


def spawn_next_occurrence(db: Session, task: Task) -> Optional[Task]:
    """为已完成重复任务生成下一实例：复制内容、重置状态、日期按规则偏移。"""
    if not task.due_date:
        return None
    next_due = next_occurrence(task.due_date, task.recur_rule, task.recur_interval)
    if next_due is None:
        return None
    delta = next_due - task.due_date
    new_task = Task(
        title=task.title,
        notes=task.notes,
        due_date=next_due,
        due_time=task.due_time,
        remind_offsets_json=task.remind_offsets_json,
        recur_rule=task.recur_rule,
        recur_interval=task.recur_interval,
        priority=task.priority,
        status="待办",
        progress=0,
        start_date=task.start_date + delta if task.start_date else None,
        end_date=task.end_date + delta if task.end_date else None,
    )
    db.add(new_task)
    db.flush()
    new_task.tags = list(task.tags)
    for sub in task.subtasks:
        db.add(Subtask(task_id=new_task.id, title=sub.title, done=False))
    db.commit()
    return new_task


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
        # 子任务全勾导致的完成同样算「进入完成态」：打点 + 重复任务生成
        if task.completed_at is None:
            _on_task_completed(db, task)
        return
    db.commit()
