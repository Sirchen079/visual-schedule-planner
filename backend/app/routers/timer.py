from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    TimeLogResponse,
    TimeLogStart,
    TimeStatsResponse,
)
from app.services import task_service, timer_service

router = APIRouter(tags=["timer"])


@router.post("/timer/start", response_model=TimeLogResponse, status_code=201)
def start_timer(payload: TimeLogStart, db: Session = Depends(get_db)):
    task = task_service.get_task(db, payload.task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return timer_service.start_timer(db, task, payload.kind)


@router.post("/timer/stop", response_model=TimeLogResponse)
def stop_timer(log_id: int | None = Query(None), db: Session = Depends(get_db)):
    log = timer_service.stop_timer(db, log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="没有运行中的计时")
    return log


@router.get("/timer/current", response_model=TimeLogResponse | None)
def get_current(db: Session = Depends(get_db)):
    return timer_service.current_log(db)


@router.get("/time-logs", response_model=list[TimeLogResponse])
def list_logs(
    days: int = Query(30, ge=1, le=365),
    task_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    return timer_service.list_logs(db, days, task_id)


@router.get("/stats/time", response_model=TimeStatsResponse)
def time_stats(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)):
    return timer_service.time_stats(db, days)
