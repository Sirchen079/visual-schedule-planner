import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    GoalCreate,
    GoalResponse,
    GoalUpdate,
    KeyResultCreate,
    KeyResultResponse,
    KeyResultUpdate,
)
from app.services import goal_service

router = APIRouter(prefix="/goals", tags=["goals"])


def _kr_response(db: Session, kr, goal) -> KeyResultResponse:
    current, progress = goal_service.kr_progress(db, kr, goal)
    try:
        link = json.loads(kr.link or "{}")
    except (TypeError, json.JSONDecodeError):
        link = {}
    return KeyResultResponse(
        id=kr.id,
        goal_id=kr.goal_id,
        title=kr.title,
        kind=kr.kind,
        target_value=kr.target_value,
        current_value=current,
        unit=kr.unit,
        link=link if isinstance(link, dict) else {},
        progress=progress,
    )


def _goal_response(db: Session, goal) -> GoalResponse:
    return GoalResponse(
        id=goal.id,
        title=goal.title,
        notes=goal.notes,
        status=goal.status,
        start_date=goal.start_date,
        end_date=goal.end_date,
        sort_order=goal.sort_order,
        progress=goal_service.goal_progress(db, goal),
        key_results=[_kr_response(db, kr, goal) for kr in goal.key_results],
        created_at=goal.created_at,
    )


@router.post("", response_model=GoalResponse, status_code=status.HTTP_201_CREATED)
def create_goal(payload: GoalCreate, db: Session = Depends(get_db)):
    return _goal_response(db, goal_service.create_goal(db, payload))


@router.get("", response_model=list[GoalResponse])
def list_goals(
    include_archived: bool = Query(False), db: Session = Depends(get_db)
):
    return [
        _goal_response(db, g) for g in goal_service.list_goals(db, include_archived)
    ]


@router.get("/{goal_id}", response_model=GoalResponse)
def get_goal(goal_id: int, db: Session = Depends(get_db)):
    goal = goal_service.get_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="目标不存在")
    return _goal_response(db, goal)


@router.put("/{goal_id}", response_model=GoalResponse)
def update_goal(goal_id: int, payload: GoalUpdate, db: Session = Depends(get_db)):
    goal = goal_service.update_goal(db, goal_id, payload)
    if goal is None:
        raise HTTPException(status_code=404, detail="目标不存在")
    return _goal_response(db, goal)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(goal_id: int, db: Session = Depends(get_db)):
    if not goal_service.soft_delete_goal(db, goal_id):
        raise HTTPException(status_code=404, detail="目标不存在")


@router.post("/{goal_id}/krs", response_model=KeyResultResponse, status_code=status.HTTP_201_CREATED)
def add_key_result(goal_id: int, payload: KeyResultCreate, db: Session = Depends(get_db)):
    kr = goal_service.add_key_result(db, goal_id, payload)
    if kr is None:
        raise HTTPException(status_code=404, detail="目标不存在")
    goal = goal_service.get_goal(db, goal_id)
    return _kr_response(db, kr, goal)


@router.put("/krs/{kr_id}", response_model=KeyResultResponse)
def update_key_result(kr_id: int, payload: KeyResultUpdate, db: Session = Depends(get_db)):
    kr = goal_service.update_key_result(db, kr_id, payload)
    if kr is None:
        raise HTTPException(status_code=404, detail="关键结果不存在")
    goal = goal_service.get_goal(db, kr.goal_id)
    return _kr_response(db, kr, goal)


@router.delete("/krs/{kr_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_key_result(kr_id: int, db: Session = Depends(get_db)):
    if not goal_service.delete_key_result(db, kr_id):
        raise HTTPException(status_code=404, detail="关键结果不存在")
