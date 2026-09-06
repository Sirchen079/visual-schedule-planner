"""任务排期：task+date 唯一（同日重复 assign = 更新时间）。
day/month/range 聚合视图供前端与AI 排程共用。"""
from __future__ import annotations
import json
from collections import defaultdict
from datetime import date, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from zhishi.domain.models import Task, TaskScheduleEntry
from zhishi.domain.schedule.schemas import ScheduleEntryCreate, ScheduleEntryUpdate


def assign_task_to_day(db: Session, task_id: int, day: date, *,
                       start_time: str | None = None, end_time: str | None = None,
                       source: str = "manual", note: str = "") -> TaskScheduleEntry:
    task = db.get(Task, task_id)
    if task is None or task.deleted_at is not None:
        raise LookupError(f"task {task_id} 不存在")
    entry = db.scalar(select(TaskScheduleEntry)
                      .where(TaskScheduleEntry.task_id == task_id, TaskScheduleEntry.date == day))
    if entry is None:
        entry = TaskScheduleEntry(task_id=task_id, date=day, source=source)
        db.add(entry)
    entry.start_time, entry.end_time = start_time, end_time
    if note:
        entry.note = note
    db.commit()
    db.refresh(entry)
    return entry


def update_entry(db: Session, entry_id: int, patch: ScheduleEntryUpdate) -> TaskScheduleEntry:
    entry = db.get(TaskScheduleEntry, entry_id)
    if entry is None:
        raise LookupError(f"entry {entry_id} 不存在")
    for key, value in patch.model_dump(exclude_none=True).items():
        setattr(entry, key, value)
    db.commit()
    db.refresh(entry)
    return entry


def delete_entry(db: Session, entry_id: int) -> None:
    entry = db.get(TaskScheduleEntry, entry_id)
    if entry is None:
        raise LookupError(f"entry {entry_id} 不存在")
    db.delete(entry)
    db.commit()


def list_entries(db: Session, *, task_id: int | None = None,
                 date_from: date | None = None,
                 date_to: date | None = None) -> list[TaskScheduleEntry]:
    """entries 读取面：默认近 30 天窗口 [今天-29, 今天]；
    只给一端时另一端按 30 天窗推算。不过滤任务软删态——清理/管理工具需要看到全部行。"""
    if date_to is None and date_from is None:
        date_to = date.today()
        date_from = date_to - timedelta(days=29)
    elif date_to is None:
        date_to = date_from + timedelta(days=29)
    elif date_from is None:
        date_from = date_to - timedelta(days=29)
    stmt = select(TaskScheduleEntry).where(TaskScheduleEntry.date.between(date_from, date_to))
    if task_id is not None:
        stmt = stmt.where(TaskScheduleEntry.task_id == task_id)
    return list(db.scalars(stmt.order_by(TaskScheduleEntry.date, TaskScheduleEntry.id)))


def _entries_between(db: Session, start: date, end: date) -> list[tuple[TaskScheduleEntry, Task]]:
    stmt = (select(TaskScheduleEntry)
            .join(Task, Task.id == TaskScheduleEntry.task_id)
            .where(Task.deleted_at.is_(None),
                   TaskScheduleEntry.date >= start, TaskScheduleEntry.date <= end)
            .options(selectinload(TaskScheduleEntry.task).selectinload(Task.tags)))
    return [(e, e.task) for e in db.scalars(stmt)]


def day_schedule(db: Session, day: date) -> dict:
    pairs = _entries_between(db, day, day)
    items = [{"entry_id": e.id, "task_id": t.id, "title": t.title,
              "start_time": e.start_time, "end_time": e.end_time,
              "estimated_minutes": t.estimated_minutes, "source": e.source, "note": e.note}
             for e, t in pairs]
    return {"date": day.isoformat(),
            "tasks": sorted(items, key=lambda x: (x["start_time"] or "99:99")),
            "total_estimated_minutes": sum(i["estimated_minutes"] or 0 for i in items)}


def month_schedule(db: Session, year: int, month: int) -> list[dict]:
    start = date(year, month, 1)
    end = date(year + (month == 12), (month % 12) + 1, 1) - timedelta(days=1)
    by_date: dict[date, int] = defaultdict(int)
    for e, _t in _entries_between(db, start, end):
        by_date[e.date] += 1
    # 独立日程按 RRULE 月窗展开计数（单双周课隔周 +1）
    events_by_date: dict[date, int] = defaultdict(int)
    for item in expand_events_between(db, start, end):
        events_by_date[date.fromisoformat(item["date"])] += 1
    return [{"date": d.isoformat(), "task_count": by_date.get(d, 0),
             "event_count": events_by_date.get(d, 0)}
            for d in _daterange(start, end)]


def range_load(db: Session, start: date, days: int) -> dict[str, dict]:
    """排程负载视图（AI 排程输入）：每日任务明细 + 预估总时长。"""
    end = start + timedelta(days=days - 1)
    by_date: dict[date, list[dict]] = defaultdict(list)
    for e, t in _entries_between(db, start, end):
        by_date[e.date].append({"task_id": t.id, "title": t.title,
                                "start_time": e.start_time, "end_time": e.end_time,
                                "estimated_minutes": t.estimated_minutes})
    return {d.isoformat(): {
        "items": by_date.get(d, []),
        "estimated_minutes": sum(i["estimated_minutes"] or 0 for i in by_date.get(d, [])),
    } for d in _daterange(start, end)}


def _daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


# ---- 独立日程 events ----
from datetime import datetime, time as dtime
from dateutil.rrule import rrulestr
from zhishi.domain.models import Event
from zhishi.domain.schedule.schemas import EventCreate, EventUpdate


def create_event(db: Session, *, commit: bool = True, **fields) -> Event:
    """字段即 EventCreate 字段（title/date/start_time/end_time/location/category/recur_rrule/notes）。"""
    values = EventCreate(**fields).model_dump()
    values['remind_offsets'] = json.dumps(values['remind_offsets'])
    event = Event(**values)
    db.add(event)
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(event)
    return event


def get_event(db: Session, event_id: int) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise LookupError(f"event {event_id} 不存在")
    return event


def update_event(db: Session, event_id: int, patch: EventUpdate) -> Event:
    event = get_event(db, event_id)
    changes = patch.model_dump(exclude_unset=True)
    current = {key: getattr(event, key) for key in EventCreate.model_fields}
    current['remind_offsets'] = event_reminder_offsets(event)
    # Validate the merged state so a partial edit cannot leave an unusable reminder.
    EventCreate(**{**current, **changes})
    if 'remind_offsets' in changes:
        changes['remind_offsets'] = json.dumps(sorted(set(changes['remind_offsets'])))
    for key, value in changes.items():
        setattr(event, key, value)
    db.commit()
    db.refresh(event)
    return event


def event_reminder_offsets(event: Event) -> list[int]:
    try:
        offsets = json.loads(event.remind_offsets or '[]')
        if isinstance(offsets, list):
            return sorted({n for n in offsets if type(n) is int and 0 <= n <= 10080})[:8]
    except (ValueError, TypeError):
        pass
    return []


def delete_event(db: Session, event_id: int) -> None:
    db.delete(get_event(db, event_id))
    db.commit()


def _expand_one(event: Event, start: date, end: date) -> list[date]:
    """单个 event 在 [start,end] 内的出现日期。RRULE 必须限定窗口（防无限展开）。"""
    if not event.recur_rrule:
        return [event.date] if start <= event.date <= end else []
    anchor = datetime.combine(event.date, dtime(0, 0))
    try:
        rule = rrulestr(event.recur_rrule, dtstart=anchor)
    except ValueError:
        return [event.date] if start <= event.date <= end else []
    # inc=True 保留恰好落在窗口起点的出现（RRULE 事件自身的锚点日）；再按日期收口窗口
    return [dt.date() for dt in rule.between(
        datetime.combine(start, dtime(0, 0)),
        datetime.combine(end, dtime(0, 0)) + timedelta(days=1), inc=True)
        if start <= dt.date() <= end]


def expand_events_between(db: Session, start: date, end: date) -> list[dict]:
    out: list[dict] = []
    for event in db.scalars(select(Event)):
        for d in _expand_one(event, start, end):
            out.append({"event_id": event.id, "title": event.title, "date": d.isoformat(),
                        "start_time": event.start_time, "end_time": event.end_time,
                        "location": event.location, "category": event.category,
                        "repeat_note": event.repeat_note})
    return sorted(out, key=lambda x: (x["date"], x["start_time"] or "99:99"))


def unified_day(db: Session, day: date) -> dict:
    """统一日程视图：任务排期 + 独立日程合并（的 list_day_schedule 工具直接复用）。"""
    items = [{"kind": "event", **e} for e in expand_events_between(db, day, day)]
    items += [{"kind": "task", "task_id": i["task_id"], "title": i["title"],
               "start_time": i["start_time"], "end_time": i["end_time"]}
              for i in day_schedule(db, day)["tasks"]]
    items.sort(key=lambda x: (x["start_time"] or "99:99"))
    return {"date": day.isoformat(), "items": items}
