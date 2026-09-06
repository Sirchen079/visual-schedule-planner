# src/zhishi/server/routes/habits.py
# Date 别名：类体内 `date: Date | None` 避开字段名 date 遮蔽类型的求值坑（同 schedule/schemas.py）
from datetime import date, date as Date
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from zhishi.domain.habits import service
from zhishi.domain.habits.schemas import HabitCreate
from zhishi.server.deps import get_db

router = APIRouter(prefix="/api/habits", tags=["habits"])


# ---- typed 响应（re #B1：openapi 从空 schema 变 $ref，字段与实际返回形状一致） ----

class HabitStatusOut(BaseModel):
    """实时状态（仅列表端点携带）：streak 今天未达标不打断（算到昨天）。"""
    today_count: int
    period_count: int
    streak: int
    done_today: bool


class HabitOut(BaseModel):
    id: int
    name: str
    notes: str
    period: str                     # daily/weekly
    target_count: int
    color: str
    status: HabitStatusOut | None = None   # 创建返回不带，列表携带


class CheckInOut(BaseModel):
    id: int
    habit_id: int
    date: str                       # YYYY-MM-DD
    count: int


class UncheckOut(BaseModel):
    ok: bool


class HabitLogOut(BaseModel):
    date: str
    count: int


class UncheckBody(BaseModel):
    """re #B3：date 可省略（缺省=今天），与 check_in 的 day=None 语义一致。"""
    date: Date | None = None


@router.post("", status_code=201, response_model=HabitOut,
             response_model_exclude_none=True)   # 创建返回不带 status（载荷与既有形状一致）
def create_habit(payload: HabitCreate, db: Session = Depends(get_db)):
    return _habit_dict(service.create_habit(db, payload))


@router.get("", response_model=list[HabitOut])
def list_habits(db: Session = Depends(get_db)):
    out = []
    for h in service.list_habits(db):
        item = _habit_dict(h)
        item["status"] = service.habit_status(db, h.id)
        out.append(item)
    return out


@router.post("/{habit_id}/check-in", response_model=CheckInOut)
def check_in(habit_id: int, body: dict | None = None, db: Session = Depends(get_db)):
    try:
        day = body.get("date") if body else None
        log = service.check_in(db, habit_id, date.fromisoformat(day) if day else None)
    except LookupError:
        raise HTTPException(404, "习惯不存在")
    return {"id": log.id, "habit_id": log.habit_id, "date": log.date.isoformat(),
            "count": log.count}


@router.post("/{habit_id}/uncheck", response_model=UncheckOut)
def uncheck(habit_id: int, body: UncheckBody | None = None,
            db: Session = Depends(get_db)):
    """撤销一笔打卡：date 缺省=今天（re #B3，openapi schema 与实现对齐）。"""
    try:
        day = body.date if body else None
        service.uncheck(db, habit_id, day or date.today())
    except (LookupError, ValueError):
        raise HTTPException(422, "日期无效或习惯不存在")
    return {"ok": True}


@router.get("/{habit_id}/logs", response_model=list[HabitLogOut])
def list_logs(habit_id: int, days: int = 30, db: Session = Depends(get_db)):
    return [{"date": l.date.isoformat(), "count": l.count}
            for l in service.list_logs(db, habit_id, days=days)]


@router.delete("/{habit_id}", status_code=204)
def delete_habit(habit_id: int, db: Session = Depends(get_db)) -> None:
    try:
        service.delete_habit(db, habit_id)
    except LookupError:
        raise HTTPException(404, "习惯不存在")


def _habit_dict(h):
    return {"id": h.id, "name": h.name, "notes": h.notes, "period": h.period,
            "target_count": h.target_count, "color": h.color}
