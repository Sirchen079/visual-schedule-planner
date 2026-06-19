"""子任务 CRUD。每次增删/勾选后重算父任务进度（有子任务时进度由完成率决定）。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Subtask, Task
from app.schemas import SubtaskCreate, SubtaskUpdate


def _task_with_subtasks(db: Session, task_id: int) -> Optional[Task]:
    return db.execute(
        select(Task)
        .options(selectinload(Task.subtasks))
        .where(Task.id == task_id, Task.deleted_at.is_(None))
    ).scalar_one_or_none()


def create_subtask(db: Session, task_id: int, sub: SubtaskCreate) -> Optional[Subtask]:
    task = _task_with_subtasks(db, task_id)
    if task is None:
        return None
    s = Subtask(task_id=task_id, title=sub.title)
    db.add(s)
    db.commit()
    db.refresh(s)
    _resync(db, task_id)
    return s


def update_subtask(
    db: Session, task_id: int, subtask_id: int, patch: SubtaskUpdate
) -> Optional[Subtask]:
    s = db.get(Subtask, subtask_id)
    if s is None or s.task_id != task_id:
        return None
    data = patch.model_dump(exclude_unset=True)
    # 勾选时记录完成时间，取消勾选则清空
    if "done" in data:
        if data["done"]:
            s.done = True
            s.completed_at = datetime.now()
        else:
            s.done = False
            s.completed_at = None
        del data["done"]
    for field, value in data.items():
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    _resync(db, task_id)
    return s


def delete_subtask(db: Session, task_id: int, subtask_id: int) -> bool:
    s = db.get(Subtask, subtask_id)
    if s is None or s.task_id != task_id:
        return False
    db.delete(s)
    db.commit()
    _resync(db, task_id)
    return True


def _resync(db: Session, task_id: int) -> None:
    """子任务变更后，按完成率重算父任务进度。"""
    # 延迟导入，避免与 task_service 形成循环依赖
    from app.services import task_service

    task = _task_with_subtasks(db, task_id)
    if task is not None:
        task_service.sync_progress_from_subtasks(db, task)
