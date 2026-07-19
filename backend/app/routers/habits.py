from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    HabitCheckRequest,
    HabitCreate,
    HabitLogResponse,
    HabitResponse,
    HabitUpdate,
)
from app.services import habit_service

router = APIRouter(prefix="/habits", tags=["habits"])


def _to_response(habit) -> HabitResponse:
    status_map = habit_service.habit_status(habit)
    return HabitResponse(
        id=habit.id,
        name=habit.name,
        notes=habit.notes,
        period=habit.period,
        target_count=habit.target_count,
        color=habit.color,
        sort_order=habit.sort_order,
        created_at=habit.created_at,
        **status_map,
    )


@router.post("", response_model=HabitResponse, status_code=status.HTTP_201_CREATED)
def create_habit(payload: HabitCreate, db: Session = Depends(get_db)):
    return _to_response(habit_service.create_habit(db, payload))


@router.get("", response_model=list[HabitResponse])
def list_habits(db: Session = Depends(get_db)):
    return [_to_response(h) for h in habit_service.list_habits(db)]


@router.put("/{habit_id}", response_model=HabitResponse)
def update_habit(habit_id: int, payload: HabitUpdate, db: Session = Depends(get_db)):
    habit = habit_service.update_habit(db, habit_id, payload)
    if habit is None:
        raise HTTPException(status_code=404, detail="习惯不存在")
    return _to_response(habit)


@router.delete("/{habit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_habit(habit_id: int, db: Session = Depends(get_db)):
    if not habit_service.soft_delete_habit(db, habit_id):
        raise HTTPException(status_code=404, detail="习惯不存在")


@router.post("/{habit_id}/check", response_model=HabitResponse)
def check_in(habit_id: int, payload: HabitCheckRequest, db: Session = Depends(get_db)):
    habit = habit_service.check_in(db, habit_id, payload.date)
    if habit is None:
        raise HTTPException(status_code=404, detail="习惯不存在")
    return _to_response(habit)


@router.post("/{habit_id}/uncheck", response_model=HabitResponse)
def uncheck(habit_id: int, payload: HabitCheckRequest, db: Session = Depends(get_db)):
    habit = habit_service.uncheck(db, habit_id, payload.date)
    if habit is None:
        raise HTTPException(status_code=404, detail="习惯不存在")
    return _to_response(habit)


@router.get("/{habit_id}/logs", response_model=list[HabitLogResponse])
def list_logs(habit_id: int, days: int = Query(84, ge=1, le=365), db: Session = Depends(get_db)):
    if habit_service.get_habit(db, habit_id) is None:
        raise HTTPException(status_code=404, detail="习惯不存在")
    return habit_service.list_logs(db, habit_id, days)
