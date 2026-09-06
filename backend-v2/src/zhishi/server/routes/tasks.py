from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from zhishi.domain import subtasks
from zhishi.domain.tasks import service
from zhishi.domain.tasks.schemas import SubtaskRead, TagOut, TaskCreate, TaskRead, TaskUpdate
from zhishi.server.deps import get_db

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class SubtaskWriteOut(SubtaskRead):
    """子任务写端点响应：SubtaskRead + task_id（写返回历来带归属，载荷守恒）。"""
    task_id: int


@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> TaskRead:
    return service.to_read(service.create_task(db, payload))


@router.get("")
def list_tasks(q: str | None = None, task_status: str | None = Query(default=None, alias="status"),
               priority: str | None = None, tag: str | None = None, due_before: datetime | None = None,
               due_after: datetime | None = None,
               db: Session = Depends(get_db)) -> list[TaskRead]:
    return [service.to_read(t) for t in service.list_tasks(
        db, status=task_status, priority=priority, q=q, tag=tag,
        due_before=due_before, due_after=due_after)]


@router.get("/trash")
def list_trash(db: Session = Depends(get_db)) -> list[TaskRead]:
    return [service.to_read(t) for t in service.list_trash(db)]


@router.get("/tags", response_model=list[TagOut])
def list_tags(db: Session = Depends(get_db)):
    return [{"id": t.id, "name": t.name, "color": t.color} for t in service.list_tags(db)]


@router.get("/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db)) -> TaskRead:
    try:
        return service.to_read(service.get_task(db, task_id))
    except LookupError:
        raise HTTPException(404, "任务不存在")


@router.patch("/{task_id}")
def update_task(task_id: int, patch: TaskUpdate, db: Session = Depends(get_db)) -> TaskRead:
    try:
        return service.to_read(service.update_task(db, task_id, **patch.model_dump(exclude_unset=True)))
    except LookupError:
        raise HTTPException(404, "任务不存在")


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: int, db: Session = Depends(get_db)) -> None:
    try:
        service.soft_delete_task(db, task_id)
    except LookupError:
        raise HTTPException(404, "任务不存在")


@router.post("/{task_id}/restore")
def restore_task(task_id: int, db: Session = Depends(get_db)) -> TaskRead:
    try:
        return service.to_read(service.restore_task(db, task_id))
    except LookupError:
        raise HTTPException(404, "任务不存在")


@router.delete("/{task_id}/purge", status_code=204)
def purge_task(task_id: int, db: Session = Depends(get_db)) -> None:
    try:
        service.purge_task(db, task_id)
    except LookupError:
        raise HTTPException(404, "任务不存在")


@router.post("/{task_id}/subtasks", status_code=201, response_model=SubtaskWriteOut)
def create_subtask(task_id: int, body: dict, db: Session = Depends(get_db)):
    try:
        sub = subtasks.create_subtask(db, task_id, title=body["title"],
                                      estimated_minutes=body.get("estimated_minutes"))
    except LookupError:
        raise HTTPException(404, "任务不存在")
    return {"id": sub.id, "task_id": sub.task_id, "title": sub.title, "done": sub.done,
            "completed_at": sub.completed_at, "estimated_minutes": sub.estimated_minutes}


@router.patch("/{task_id}/subtasks/{subtask_id}", response_model=SubtaskWriteOut)
def update_subtask(task_id: int, subtask_id: int, body: dict, db: Session = Depends(get_db)):
    try:
        sub = subtasks.update_subtask(db, task_id, subtask_id, **body)
    except LookupError:
        raise HTTPException(404, "子任务不存在")
    return {"id": sub.id, "task_id": sub.task_id, "title": sub.title, "done": sub.done,
            "completed_at": sub.completed_at, "estimated_minutes": sub.estimated_minutes}


@router.delete("/{task_id}/subtasks/{subtask_id}", status_code=204)
def delete_subtask(task_id: int, subtask_id: int, db: Session = Depends(get_db)) -> None:
    try:
        subtasks.delete_subtask(db, task_id, subtask_id)
    except LookupError:
        raise HTTPException(404, "子任务不存在")
