"""子任务 CRUD；每次变更按完成率重算父任务进度，全完成自动标完成。"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from zhishi.domain.models import Subtask, Task
from zhishi.domain.tasks.service import _load


def _resync(db: Session, task_id: int) -> None:
    task = _load(db, task_id, include_deleted=True)
    # 直接查表：create_subtask 只写外键，早期 selectinload 的集合不会刷新
    subs = list(db.scalars(select(Subtask).where(Subtask.task_id == task_id)))
    if not subs:
        return
    done = sum(1 for s in subs if s.done)
    task.progress = round(done * 100 / len(subs))
    if subs and all(s.done for s in subs):
        if task.status != "done":
            task.status = "done"
            task.completed_at = datetime.now()
    elif task.status == "done" and not all(s.done for s in subs):
        task.status, task.completed_at = "doing", None
    # 直接赋值 status 绕开 update_task 完成钩子：子任务联动不触发重复任务生成
    db.commit()


def create_subtask(db: Session, task_id: int, *, title: str,
                   estimated_minutes: int | None = None) -> Subtask:
    task = _load(db, task_id)
    sub = Subtask(task_id=task_id, title=title, estimated_minutes=estimated_minutes)
    db.add(sub)
    db.flush()
    if task.status == "todo":
        task.status = "doing"
    db.commit()
    db.refresh(sub)
    return sub


def update_subtask(db: Session, task_id: int, subtask_id: int, **fields) -> Subtask:
    sub = db.get(Subtask, subtask_id)
    if sub is None or sub.task_id != task_id:
        raise LookupError(f"subtask {subtask_id} 不属于 task {task_id}")
    if "done" in fields and fields["done"] is not None:
        sub.done = fields["done"]
        sub.completed_at = datetime.now() if fields["done"] else None
    if fields.get("title"):
        sub.title = fields["title"]
    if "estimated_minutes" in fields and fields["estimated_minutes"] is not None:
        sub.estimated_minutes = fields["estimated_minutes"]
    db.commit()
    _resync(db, task_id)
    db.refresh(sub)
    return sub


def delete_subtask(db: Session, task_id: int, subtask_id: int) -> None:
    sub = db.get(Subtask, subtask_id)
    if sub is None or sub.task_id != task_id:
        raise LookupError(f"subtask {subtask_id} 不属于 task {task_id}")
    db.delete(sub)
    db.commit()
    _resync(db, task_id)
