# src/zhishi/server/routes/focus.py
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from zhishi.domain.focus import service
from zhishi.domain.focus.schemas import TimerStart
from zhishi.domain.models import TimeLog
from zhishi.server.deps import get_db

router = APIRouter(prefix="/api/focus", tags=["focus"])


# ---- typed 响应（re #047：前端 FocusLog/FocusStats 手写收敛依据；
# started_at/ended_at 序列化为本地 naive ISO 串，与既有回包一致） ----

class TimeLogOut(BaseModel):
    id: int
    task_id: int | None = None
    task_title: str
    kind: str                    # focus/break
    started_at: datetime
    ended_at: datetime | None = None
    minutes: int


class FocusStopMissOut(BaseModel):
    """stop 落空（无进行中计时或目标已结账）的回包；extra=forbid 保证
    stop 端点 TimeLogOut | FocusStopMissOut 二选一互不误配。"""
    model_config = ConfigDict(extra="forbid")
    ok: bool = False
    stopped: None = None


class ByDayItem(BaseModel):
    date: str                    # YYYY-MM-DD
    minutes: int


class ByTaskItem(BaseModel):
    task_title: str
    minutes: int


class FocusStatsOut(BaseModel):
    by_day: list[ByDayItem]
    by_task: list[ByTaskItem]
    total_minutes: int


@router.post("/start", status_code=201, response_model=TimeLogOut)
def start(payload: TimerStart, db: Session = Depends(get_db)):
    return _log_dict(service.start_timer(db, payload))


@router.post("/stop", response_model=TimeLogOut | FocusStopMissOut)
def stop(body: dict | None = None, db: Session = Depends(get_db)):
    log_id = body.get("log_id") if body else None
    log = service.stop_timer(db, log_id)
    return _log_dict(log) if log is not None else {"ok": False, "stopped": None}


@router.get("/current", response_model=TimeLogOut | None)
def current(db: Session = Depends(get_db)):
    log = service.current_log(db)
    return _log_dict(log) if log is not None else None


@router.get("/logs", response_model=list[TimeLogOut])
def logs(days: int = 7, task_id: int | None = None, db: Session = Depends(get_db)):
    return [_log_dict(l) for l in service.list_logs(db, days=days, task_id=task_id)]


@router.get("/stats", response_model=FocusStatsOut)
def stats(days: int = 7, db: Session = Depends(get_db)):
    return service.time_stats(db, days=days)


@router.delete("/logs/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_log(log_id: int, db: Session = Depends(get_db)) -> None:
    """删除一条已结束的计时记录（re k3#048 残留清理诉求）。
    运行中的计时不可直接删（先停后删），409 防误删破坏 current 指针语义。"""
    log = db.get(TimeLog, log_id)
    if log is None:
        raise HTTPException(404, "计时记录不存在")
    if log.ended_at is None:
        raise HTTPException(409, "运行中的计时不能删除，请先停止")
    db.delete(log)
    db.commit()


def _log_dict(l):
    return {"id": l.id, "task_id": l.task_id, "task_title": l.task_title, "kind": l.kind,
            "started_at": l.started_at, "ended_at": l.ended_at, "minutes": l.minutes}
