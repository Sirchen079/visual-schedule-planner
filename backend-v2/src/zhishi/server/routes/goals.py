# src/zhishi/server/routes/goals.py
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from zhishi.domain.goals import service
from zhishi.domain.goals.schemas import GoalCreate, KeyResultCreate
from zhishi.server.deps import get_db

router = APIRouter(prefix="/api/goals", tags=["goals"])


# ---- typed 响应（re #B1：openapi 从空 schema 变 $ref，字段与实际返回形状一致） ----

class KeyResultOut(BaseModel):
    id: int
    goal_id: int
    title: str
    kind: str                       # manual/tag_task_count/habit_checkins
    target_value: float
    current_value: float
    unit: str
    link: str


class GoalOut(BaseModel):
    id: int
    title: str
    notes: str
    status: str                     # active/paused/done/archived
    start_date: str | None = None   # YYYY-MM-DD
    end_date: str | None = None
    key_results: list[KeyResultOut]
    deleted_at: datetime | None = None   # 回收站语义（re #B2）：已删项透出删除时间


class GoalProgressItemOut(BaseModel):
    """progress 端点条目：自动类 KR 实时计算的 current_value + 0-100 整数进度。"""
    kr_id: int
    title: str
    kind: str
    target_value: float
    current_value: float
    unit: str
    progress: int


@router.post("", status_code=201, response_model=GoalOut)
def create_goal(payload: GoalCreate, db: Session = Depends(get_db)):
    return _goal_dict(service.create_goal(db, payload))


@router.get("", response_model=list[GoalOut])
def list_goals(include_deleted: bool = Query(False, description="包含已删除（回收站）目标"),
               include_archived: bool | None = Query(
                   None, deprecated=True,
                   description="旧参数名（re #B2 改名），等价 include_deleted，兼容保留"),
               db: Session = Depends(get_db)):
    include = include_deleted or bool(include_archived)
    return [_goal_dict(g) for g in service.list_goals(db, include_deleted=include)]


@router.get("/trash", response_model=list[GoalOut])
def list_trash(db: Session = Depends(get_db)):
    """回收站：软删目标列表（含 key_results 与 deleted_at，re #B2）。"""
    return [_goal_dict(g) for g in service.list_trash(db)]


@router.get("/{goal_id}", response_model=GoalOut)
def get_goal(goal_id: int, db: Session = Depends(get_db)):
    try:
        return _goal_dict(service.get_goal(db, goal_id))
    except LookupError:
        raise HTTPException(404, "目标不存在")


@router.patch("/{goal_id}", response_model=GoalOut)
def update_goal(goal_id: int, body: dict, db: Session = Depends(get_db)):
    try:
        return _goal_dict(service.update_goal(db, goal_id, **body))
    except LookupError:
        raise HTTPException(404, "目标不存在")


@router.delete("/{goal_id}", status_code=204)
def delete_goal(goal_id: int, db: Session = Depends(get_db)) -> None:
    try:
        service.delete_goal(db, goal_id)
    except LookupError:
        raise HTTPException(404, "目标不存在")


@router.post("/{goal_id}/restore", response_model=GoalOut)
def restore_goal(goal_id: int, db: Session = Depends(get_db)):
    try:
        return _goal_dict(service.restore_goal(db, goal_id))
    except LookupError:
        raise HTTPException(404, "目标不存在")


@router.delete("/{goal_id}/purge", status_code=204)
def purge_goal(goal_id: int, db: Session = Depends(get_db)) -> None:
    """硬删目标（级联 KR）。仅回收站中的可 purge：未软删 → 409。"""
    try:
        service.purge_goal(db, goal_id)
    except LookupError:
        raise HTTPException(404, "目标不存在")
    except ValueError as ex:
        raise HTTPException(409, str(ex))


@router.post("/{goal_id}/key-results", status_code=201, response_model=KeyResultOut)
def add_key_result(goal_id: int, payload: KeyResultCreate, db: Session = Depends(get_db)):
    try:
        kr = service.add_key_result(db, goal_id, payload)
    except LookupError:
        raise HTTPException(404, "目标不存在")
    return _kr_dict(kr)


@router.patch("/key-results/{kr_id}", response_model=KeyResultOut)
def update_key_result(kr_id: int, body: dict, db: Session = Depends(get_db)):
    try:
        if "current_value" in body and body["current_value"] is not None:
            kr = service.update_kr_progress(db, kr_id, current_value=body["current_value"])
        else:
            kr = db_get_kr(db, kr_id)
            if "title" in body and body["title"]:
                kr.title = body["title"]
            db.commit()
            db.refresh(kr)
    except LookupError:
        raise HTTPException(404, "关键结果不存在")
    return _kr_dict(kr)


@router.delete("/key-results/{kr_id}", status_code=204)
def delete_key_result(kr_id: int, db: Session = Depends(get_db)) -> None:
    try:
        service.delete_key_result(db, kr_id)
    except LookupError:
        raise HTTPException(404, "关键结果不存在")


@router.get("/{goal_id}/progress", response_model=list[GoalProgressItemOut])
def goal_progress(goal_id: int, db: Session = Depends(get_db)):
    try:
        return service.goal_progress(db, goal_id)
    except LookupError:
        raise HTTPException(404, "目标不存在")


def db_get_kr(db: Session, kr_id: int):
    from zhishi.domain.models import KeyResult
    kr = db.get(KeyResult, kr_id)
    if kr is None:
        raise LookupError(f"kr {kr_id} 不存在")
    return kr


def _goal_dict(g):
    return {"id": g.id, "title": g.title, "notes": g.notes, "status": g.status,
            "start_date": g.start_date.isoformat() if g.start_date else None,
            "end_date": g.end_date.isoformat() if g.end_date else None,
            "key_results": [_kr_dict(k) for k in g.key_results],
            "deleted_at": g.deleted_at.isoformat() if g.deleted_at else None}


def _kr_dict(k):
    return {"id": k.id, "goal_id": k.goal_id, "title": k.title, "kind": k.kind,
            "target_value": k.target_value, "current_value": k.current_value,
            "unit": k.unit, "link": k.link}
