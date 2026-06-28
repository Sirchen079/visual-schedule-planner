from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    DayScheduleResponse,
    MonthScheduleResponse,
    ScheduleEntryCreate,
    ScheduleEntryRead,
    ScheduleEntryUpdate,
)
from app.services import schedule_service

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.get("/day", response_model=DayScheduleResponse)
def get_day_schedule(
    target_date: date = Query(..., alias="date"),
    db: Session = Depends(get_db),
):
    return schedule_service.get_day_schedule(db, target_date)


@router.get("/month", response_model=MonthScheduleResponse)
def get_month_schedule(year: int, month: int, db: Session = Depends(get_db)):
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Month must be between 1 and 12")
    return schedule_service.get_month_schedule(db, year, month)


@router.post(
    "/entries",
    response_model=ScheduleEntryRead,
    status_code=status.HTTP_201_CREATED,
)
def create_schedule_entry(
    entry: ScheduleEntryCreate, db: Session = Depends(get_db)
):
    try:
        return schedule_service.create_schedule_entry(db, entry)
    except schedule_service.ScheduleTaskNotFound as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


@router.put("/entries/{entry_id}", response_model=ScheduleEntryRead)
def update_schedule_entry(
    entry_id: int,
    entry: ScheduleEntryUpdate,
    db: Session = Depends(get_db),
):
    updated = schedule_service.update_schedule_entry(db, entry_id, entry)
    if updated is None:
        raise HTTPException(status_code=404, detail="Schedule entry not found")
    return updated


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule_entry(entry_id: int, db: Session = Depends(get_db)):
    if not schedule_service.delete_schedule_entry(db, entry_id):
        raise HTTPException(status_code=404, detail="Schedule entry not found")
