# src/zhishi/domain/tasks/service.py
from __future__ import annotations
import json
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from zhishi.domain.models import Tag, Task
from zhishi.domain.tasks.recurrence import advance_occurrence, next_rrule_occurrence
from zhishi.domain.tasks.schemas import SubtaskRead, TaskCreate, TaskRead, TaskUpdate

TAG_COLORS = ["#ef4444", "#f97316", "#eab308", "#22c55e", "#06b6d4", "#6366f1", "#a855f7"]


def _serialize_offsets(values: list[int]) -> str:
    return json.dumps(sorted(set(values)))


def _sync_tags(db: Session, task: Task, names: list[str]) -> None:
    task.tags.clear()
    for name in dict.fromkeys(n for n in names if n.strip()):
        tag = db.scalar(select(Tag).where(Tag.name == name))
        if tag is None:
            tag = Tag(name=name, color=TAG_COLORS[len(db.scalars(select(Tag.id)).all()) % len(TAG_COLORS)])
            db.add(tag)
            db.flush()
        task.tags.append(tag)


def _load(db: Session, task_id: int, include_deleted: bool = False) -> Task:
    task = db.scalar(select(Task).where(Task.id == task_id)
                     .options(selectinload(Task.tags), selectinload(Task.subtasks)))
    if task is None or (task.deleted_at is not None and not include_deleted):
        raise LookupError(f"task {task_id} 不存在")
    return task


def create_task(db: Session, payload: TaskCreate, *, commit: bool = True) -> Task:
    task = Task(
        title=payload.title, notes=payload.notes, due_date=payload.due_date,
        due_time=payload.due_time, remind_offsets=_serialize_offsets(payload.remind_offsets),
        priority=payload.priority, status=payload.status, start_date=payload.start_date,
        recur_rule=payload.recur_rule, recur_interval=payload.recur_interval,
        recur_rrule=payload.recur_rrule, estimated_minutes=payload.estimated_minutes,
    )
    db.add(task)
    db.flush()
    _sync_tags(db, task, payload.tag_names)
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(task)
    return task


def get_task(db: Session, task_id: int) -> Task:
    return _load(db, task_id)


def list_tasks(db: Session, *, status: str | None = None, priority: str | None = None,
               q: str | None = None, tag: str | None = None,
               due_before: datetime | None = None, due_after: datetime | None = None) -> list[Task]:
    stmt = (select(Task).where(Task.deleted_at.is_(None))
            .options(selectinload(Task.tags), selectinload(Task.subtasks)))  # re #B4 预载防 N+1
    if status:
        stmt = stmt.where(Task.status == status)
    if priority:
        stmt = stmt.where(Task.priority == priority)
    if q:
        stmt = stmt.where(Task.title.contains(q))
    if tag:
        stmt = stmt.where(Task.tags.any(Tag.name == tag))
    if due_before:
        stmt = stmt.where(Task.due_date <= due_before)
    if due_after:
        stmt = stmt.where(Task.due_date >= due_after)
    return list(db.scalars(stmt.order_by(Task.sort_order.desc(), Task.id.desc())))


def update_task(db: Session, task_id: int, **fields) -> Task:
    fields = TaskUpdate(**fields).model_dump(exclude_unset=True)
    task = _load(db, task_id)
    was_done = task.status == "done"
    for key, value in fields.items():
        if value is None and key not in ("due_date", "due_time", "start_date", "recur_rrule",
                                          "estimated_minutes"):
            continue
        if key == "remind_offsets":
            task.remind_offsets = _serialize_offsets(value)
        elif key == "tag_names":
            _sync_tags(db, task, value)
        else:
            setattr(task, key, value)
    if fields.get("status") == "done" and not was_done:
        task.completed_at = datetime.now()
        _spawn_next_occurrence(db, task)
    db.commit()
    db.refresh(task)
    return task


def _spawn_next_occurrence(db: Session, task: Task) -> None:
    """为已完成重复任务生成下一实例：复制内容、重置状态、日期按规则偏移。"""
    if task.due_date is None:
        return
    if task.recur_rrule:
        nxt = next_rrule_occurrence(task.recur_rrule, task.due_date)
    else:
        nxt = advance_occurrence(task.due_date, task.recur_rule, task.recur_interval)
    if nxt is None:
        return
    clone = Task(
        title=task.title, notes=task.notes, due_date=nxt, due_time=task.due_time,
        remind_offsets=task.remind_offsets, priority=task.priority, status="todo",
        start_date=None, recur_rule=task.recur_rule, recur_interval=task.recur_interval,
        recur_rrule=task.recur_rrule, estimated_minutes=task.estimated_minutes,
    )
    db.add(clone)
    db.flush()
    _sync_tags(db, clone, [t.name for t in task.tags])


def soft_delete_task(db: Session, task_id: int) -> None:
    _load(db, task_id).deleted_at = datetime.now()
    db.commit()


def list_trash(db: Session) -> list[Task]:
    return list(db.scalars(select(Task).where(Task.deleted_at.is_not(None))
                           .options(selectinload(Task.tags), selectinload(Task.subtasks))
                           .order_by(Task.deleted_at.desc())))


def restore_task(db: Session, task_id: int) -> Task:
    task = _load(db, task_id, include_deleted=True)
    task.deleted_at = None
    db.commit()
    db.refresh(task)
    return task


def purge_task(db: Session, task_id: int) -> None:
    """硬删任务。M3：排期行无 ORM 关系需先显式删除；标签/附件走集合清空
    （ORM 在删任务前删 task_tag/task_file 关联行，FK 不再阻断）；
    子任务随 cascade 删除；计时/通知日志按设计保留（统计靠冗余 task_title
    延续），task_id 置空后随任务一并落库。"""
    from zhishi.domain.models import NotificationLog, TaskScheduleEntry, TimeLog
    task = _load(db, task_id, include_deleted=True)
    db.query(TaskScheduleEntry).filter(
        TaskScheduleEntry.task_id == task_id).delete(synchronize_session=False)
    task.tags.clear()
    task.files.clear()
    for tl in db.scalars(select(TimeLog).where(TimeLog.task_id == task_id)):
        tl.task_id = None
    for nl in db.scalars(select(NotificationLog).where(NotificationLog.task_id == task_id)):
        nl.task_id = None
    db.delete(task)
    db.commit()


def list_tags(db: Session) -> list[Tag]:
    return list(db.scalars(select(Tag).order_by(Tag.name)))


def to_read(task: Task) -> TaskRead:
    # 显式构造：ORM 的 remind_offsets 是 JSON 字符串、tags 是 ORM 对象，属性校验取原值必失败
    return TaskRead(
        id=task.id, title=task.title, notes=task.notes,
        due_date=task.due_date, due_time=task.due_time,
        remind_offsets=task.remind_offset_list,
        priority=task.priority, status=task.status, progress=task.progress,
        start_date=task.start_date, recur_rule=task.recur_rule,
        recur_interval=task.recur_interval, recur_rrule=task.recur_rrule,
        estimated_minutes=task.estimated_minutes,
        tags=[t.name for t in task.tags],
        created_at=task.created_at, updated_at=task.updated_at,
        completed_at=task.completed_at,
        subtasks=[SubtaskRead(id=s.id, title=s.title, done=s.done,
                              estimated_minutes=s.estimated_minutes,
                              completed_at=s.completed_at)
                  for s in task.subtasks],
    )
