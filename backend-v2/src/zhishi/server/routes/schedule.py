from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from zhishi.domain import settingsvc
from zhishi.domain.schedule import conflicts as cf
from zhishi.domain.schedule import service
from zhishi.domain.schedule.schemas import (EventUpdate, ScheduleEntryCreate,
                                            ScheduleEntryUpdate)
from zhishi.server.deps import get_db

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


class EventDetailOut(BaseModel):
    """独立日程详情：date 为 ISO 字符串（与既有消费面一致）；repeat_note 透出。"""
    id: int
    title: str
    date: str
    start_time: str | None
    end_time: str | None
    location: str
    category: str
    recur_rrule: str | None
    notes: str
    repeat_note: str | None = None
    remind_offsets: list[int] = []
    reminder_time: str | None = None


# 只读日程视图的响应模型。

class DayItemOut(BaseModel):
    """统一日视图条目：event（独立日程，含 event_id/date/location/category）
    与 task（任务排期，含 task_id）按 kind 判别；两者字段取并集。"""
    kind: str                      # "event" | "task"
    event_id: int | None = None
    task_id: int | None = None
    title: str
    date: str | None = None        # event 条目携带所属日期（RRULE 展开日）
    start_time: str | None = None
    end_time: str | None = None
    location: str | None = None
    category: str | None = None
    repeat_note: str | None = None  # 人类可读周次规则（如「双周课（第2-16周）」）


class DayViewOut(BaseModel):
    date: str
    items: list[DayItemOut]


class RangeTaskItem(BaseModel):
    task_id: int
    title: str
    start_time: str | None = None
    end_time: str | None = None
    estimated_minutes: int | None = None


class MonthDayOut(BaseModel):
    """month 视图单日条目：task_count=当日任务排期数；
    event_count=当日独立日程 RRULE 展开计数（双周课隔周 +1）。"""
    date: str
    task_count: int
    event_count: int = 0


class RangeDayLoad(BaseModel):
    """range 是任务负载视图（不含独立日程）：日期键 → 当日排期明细与预估总时长。"""
    items: list[RangeTaskItem]
    estimated_minutes: int


class ExpandedEventOut(BaseModel):
    """events/expand：RRULE 展开后的日程出现（含单双周），周视图数据源。"""
    event_id: int
    title: str
    date: str
    start_time: str | None = None
    end_time: str | None = None
    location: str | None = None
    category: str | None = None
    repeat_note: str | None = None  # 人类可读周次规则（可空）


class ConflictItemOut(BaseModel):
    """冲突项：event 展开条目或任务排期条目（字段并集，按存在字段判别）。"""
    event_id: int | None = None
    entry_id: int | None = None
    task_id: int | None = None
    title: str
    date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    location: str | None = None
    category: str | None = None
    estimated_minutes: int | None = None
    source: str | None = None
    note: str | None = None


class ConflictOut(BaseModel):
    date: str
    items: list[ConflictItemOut]


class FreeSlotOut(BaseModel):
    start: str
    end: str
    minutes: int


class ScheduleEntryOut(BaseModel):
    """排期条目本体：列表/创建/更新端点共用同一形状。"""
    id: int
    task_id: int
    date: str                       # YYYY-MM-DD
    start_time: str | None = None
    end_time: str | None = None
    source: str                     # manual/ai/ical
    note: str


@router.get("/entries", response_model=list[ScheduleEntryOut])
def list_entries(task_id: int | None = None, date_from: date | None = None,
                 date_to: date | None = None, db: Session = Depends(get_db)):
    """排期条目列表：默认近 30 天（[今天-29, 今天]），只给一端按 30 天窗推算；
    可按 task_id 过滤。entry_id 不再创建即失联。"""
    return [_entry_dict(e) for e in service.list_entries(
        db, task_id=task_id, date_from=date_from, date_to=date_to)]


@router.post("/entries", status_code=201, response_model=ScheduleEntryOut)
def create_entry(payload: ScheduleEntryCreate, db: Session = Depends(get_db)):
    try:
        e = service.assign_task_to_day(db, payload.task_id, payload.date,
                                       start_time=payload.start_time, end_time=payload.end_time,
                                       source=payload.source, note=payload.note)
    except LookupError:
        raise HTTPException(404, "任务不存在")
    return _entry_dict(e)


@router.patch("/entries/{entry_id}", response_model=ScheduleEntryOut)
def update_entry(entry_id: int, patch: ScheduleEntryUpdate, db: Session = Depends(get_db)):
    try:
        e = service.update_entry(db, entry_id, patch)
    except LookupError:
        raise HTTPException(404, "排期不存在")
    return _entry_dict(e)


@router.delete("/entries/{entry_id}", status_code=204)
def delete_entry(entry_id: int, db: Session = Depends(get_db)) -> None:
    try:
        service.delete_entry(db, entry_id)
    except LookupError:
        raise HTTPException(404, "排期不存在")


@router.get("/day", response_model=DayViewOut)
def day_view(day: date = Query(alias="date"), db: Session = Depends(get_db)):
    return service.unified_day(db, day)


@router.get("/month", response_model=list[MonthDayOut])
def month_view(year: int, month: int, db: Session = Depends(get_db)):
    return service.month_schedule(db, year, month)


@router.get("/range", response_model=dict[str, RangeDayLoad])
def range_view(start: date, days: int = 7, db: Session = Depends(get_db)):
    return service.range_load(db, start, days)


@router.post("/events", status_code=201, response_model=EventDetailOut)
def create_event(body: dict, db: Session = Depends(get_db)):
    try:
        e = service.create_event(db, **body)
    except ValueError as ex:
        raise HTTPException(422, str(ex))
    return _event_dict(e)


@router.get("/events/expand", response_model=list[ExpandedEventOut])
def expand_events(start: date, end: date, db: Session = Depends(get_db)):
    return service.expand_events_between(db, start, end)


@router.get("/events/{event_id}", response_model=EventDetailOut)
def get_event(event_id: int, db: Session = Depends(get_db)):
    try:
        return _event_dict(service.get_event(db, event_id))
    except LookupError:
        raise HTTPException(404, "日程不存在")


@router.patch("/events/{event_id}", response_model=EventDetailOut)
def update_event(event_id: int, patch: EventUpdate, db: Session = Depends(get_db)):
    try:
        return _event_dict(service.update_event(db, event_id, patch))
    except LookupError:
        raise HTTPException(404, "日程不存在")
    except ValueError as ex:
        raise HTTPException(422, str(ex))


@router.delete("/events/{event_id}", status_code=204)
def delete_event(event_id: int, db: Session = Depends(get_db)) -> None:
    try:
        service.delete_event(db, event_id)
    except LookupError:
        raise HTTPException(404, "日程不存在")


@router.get("/conflicts", response_model=list[ConflictOut])
def find_conflicts(start: date, end: date, db: Session = Depends(get_db)):
    return cf.check_conflicts(db, start, end)


@router.get("/free-slots", response_model=list[FreeSlotOut])
def free_slots(day: date = Query(alias="date"), min_minutes: int = 30,
               db: Session = Depends(get_db)):
    working = settingsvc.working_hours(db)
    return cf.find_free_slots(db, day, working=working, min_minutes=min_minutes)


def _entry_dict(e):
    return {"id": e.id, "task_id": e.task_id, "date": e.date.isoformat(),
            "start_time": e.start_time, "end_time": e.end_time,
            "source": e.source, "note": e.note}


def _event_dict(e):
    return {"id": e.id, "title": e.title, "date": e.date.isoformat(),
            "start_time": e.start_time, "end_time": e.end_time,
            "location": e.location, "category": e.category, "recur_rrule": e.recur_rrule,
            "notes": e.notes, "repeat_note": getattr(e, "repeat_note", None),
            "remind_offsets": service.event_reminder_offsets(e), "reminder_time": e.reminder_time}
