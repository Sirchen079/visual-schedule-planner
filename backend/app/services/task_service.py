from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Task
from app.schemas import TaskCreate, TaskUpdate


def _task_query():
    return select(Task).options(selectinload(Task.files))


def create_task(db: Session, task: TaskCreate) -> Task:
    db_task = Task(**task.model_dump())
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
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
    for field, value in task.model_dump(exclude_unset=True).items():
        setattr(db_task, field, value)
    db.commit()
    return get_task(db, task_id)


def soft_delete_task(db: Session, task_id: int) -> bool:
    db_task = get_task(db, task_id)
    if db_task is None:
        return False
    db_task.deleted_at = datetime.now()
    db.commit()
    return True
