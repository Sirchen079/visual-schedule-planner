from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    SubtaskCreate,
    SubtaskResponse,
    SubtaskUpdate,
    TagResponse,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
)
from app.services import subtask_service, task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    return task_service.create_task(db, task)


@router.get("", response_model=list[TaskResponse])
def list_tasks(db: Session = Depends(get_db)):
    return task_service.list_tasks(db)


# 以下静态路径必须在 /{task_id} 之前注册，否则会被当作 task_id 匹配
@router.get("/trash", response_model=list[TaskResponse])
def list_trash(db: Session = Depends(get_db)):
    task_service.purge_expired(db)
    return task_service.list_trash(db)


@router.get("/tags", response_model=list[TagResponse])
def list_tags(db: Session = Depends(get_db)):
    return task_service.list_tags(db)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = task_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, task: TaskUpdate, db: Session = Depends(get_db)):
    updated = task_service.update_task(db, task_id, task)
    if updated is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return updated


@router.post("/{task_id}/restore", response_model=TaskResponse)
def restore_task(task_id: int, db: Session = Depends(get_db)):
    task = task_service.restore_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="回收站中无此任务")
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    if not task_service.soft_delete_task(db, task_id):
        raise HTTPException(status_code=404, detail="任务不存在")


@router.delete("/{task_id}/purge", status_code=status.HTTP_204_NO_CONTENT)
def purge_task(task_id: int, db: Session = Depends(get_db)):
    if not task_service.purge_task(db, task_id):
        raise HTTPException(status_code=404, detail="回收站中无此任务")


# ---- 子任务 ----

@router.post(
    "/{task_id}/subtasks",
    response_model=SubtaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_subtask(task_id: int, sub: SubtaskCreate, db: Session = Depends(get_db)):
    s = subtask_service.create_subtask(db, task_id, sub)
    if s is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return s


@router.put("/{task_id}/subtasks/{subtask_id}", response_model=SubtaskResponse)
def update_subtask(
    task_id: int,
    subtask_id: int,
    patch: SubtaskUpdate,
    db: Session = Depends(get_db),
):
    s = subtask_service.update_subtask(db, task_id, subtask_id, patch)
    if s is None:
        raise HTTPException(status_code=404, detail="子任务不存在")
    return s


@router.delete(
    "/{task_id}/subtasks/{subtask_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_subtask(task_id: int, subtask_id: int, db: Session = Depends(get_db)):
    if not subtask_service.delete_subtask(db, task_id, subtask_id):
        raise HTTPException(status_code=404, detail="子任务不存在")
