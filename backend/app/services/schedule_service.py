from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Task, TaskScheduleEntry
from app.schemas import (
    DayScheduleBuckets,
    DayScheduleResponse,
    DayScheduleSummary,
    MonthScheduleDay,
    MonthScheduleResponse,
    ScheduleEntryCreate,
    ScheduleEntryRead,
    ScheduleEntryUpdate,
    ScheduleTaskItem,
    TaskResponse,
)

DONE_STATUS = "\u5b8c\u6210"


class ScheduleTaskNotFound(Exception):
    pass


def create_schedule_entry(
    db: Session, data: ScheduleEntryCreate
) -> TaskScheduleEntry:
    task = _get_active_task(db, data.task_id)
    if task is None:
        raise ScheduleTaskNotFound()

    existing = db.execute(
        select(TaskScheduleEntry).where(
            TaskScheduleEntry.task_id == data.task_id,
            TaskScheduleEntry.date == data.date,
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.source = data.source
        existing.note = data.note
        existing.start_time = data.start_time
        existing.end_time = data.end_time
        db.commit()
        db.refresh(existing)
        return existing

    entry = TaskScheduleEntry(**data.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def update_schedule_entry(
    db: Session, entry_id: int, data: ScheduleEntryUpdate
) -> TaskScheduleEntry | None:
    entry = db.execute(
        _active_entry_stmt().where(TaskScheduleEntry.id == entry_id)
    ).scalar_one_or_none()
    if entry is None:
        return None

    patch = data.model_dump(exclude_unset=True)
    new_date = patch.get("date")
    if new_date is not None:
        duplicate = db.execute(
            select(TaskScheduleEntry).where(
                TaskScheduleEntry.task_id == entry.task_id,
                TaskScheduleEntry.date == new_date,
                TaskScheduleEntry.id != entry.id,
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            _apply_entry_patch(duplicate, patch)
            db.delete(entry)
            db.commit()
            db.refresh(duplicate)
            return duplicate

    _apply_entry_patch(entry, patch)
    db.commit()
    db.refresh(entry)
    return entry


def delete_schedule_entry(db: Session, entry_id: int) -> bool:
    entry = db.get(TaskScheduleEntry, entry_id)
    if entry is None:
        return False
    db.delete(entry)
    db.commit()
    return True


def get_day_schedule(db: Session, target_date: date) -> DayScheduleResponse:
    tasks = _active_tasks(db)
    entries_for_day = _entries_for_date(db, target_date)
    scheduled_task_ids = _scheduled_task_ids(db)
    used_task_ids: set[int] = set()

    must_do: list[ScheduleTaskItem] = []
    planned: list[ScheduleTaskItem] = []
    in_progress_today: list[ScheduleTaskItem] = []
    upcoming_pressure: list[ScheduleTaskItem] = []
    unscheduled: list[ScheduleTaskItem] = []

    for task in tasks:
        due_date = _as_date(task.due_date)
        if due_date is not None and due_date <= target_date:
            must_do.append(_task_item(task, None, "due"))
            used_task_ids.add(task.id)

    for entry in entries_for_day:
        if entry.task_id not in used_task_ids:
            planned.append(_task_item(entry.task, entry, "scheduled"))
            used_task_ids.add(entry.task_id)

    for task in tasks:
        start_date = _as_date(task.start_date)
        end_date = _as_date(task.end_date)
        if (
            task.id not in used_task_ids
            and start_date is not None
            and end_date is not None
            and start_date <= target_date <= end_date
        ):
            in_progress_today.append(_task_item(task, None, "date_range"))
            used_task_ids.add(task.id)

    pressure_cutoff = target_date + timedelta(days=7)
    for task in tasks:
        due_date = _as_date(task.due_date)
        if (
            task.id not in used_task_ids
            and due_date is not None
            and target_date < due_date <= pressure_cutoff
        ):
            upcoming_pressure.append(_task_item(task, None, "upcoming_due"))
            used_task_ids.add(task.id)

    for task in tasks:
        start_date = _as_date(task.start_date)
        end_date = _as_date(task.end_date)
        if (
            task.id not in used_task_ids
            and _as_date(task.due_date) is None
            and not (start_date is not None and end_date is not None)
            and task.id not in scheduled_task_ids
        ):
            unscheduled.append(_task_item(task, None, "unscheduled"))
            used_task_ids.add(task.id)

    buckets = DayScheduleBuckets(
        must_do=must_do,
        planned=planned,
        in_progress_today=in_progress_today,
        upcoming_pressure=upcoming_pressure,
        unscheduled=unscheduled,
    )
    summary = DayScheduleSummary(
        must_do=len(must_do),
        planned=len(planned),
        in_progress_today=len(in_progress_today),
        upcoming_pressure=len(upcoming_pressure),
        unscheduled=len(unscheduled),
        total=sum(
            [
                len(must_do),
                len(planned),
                len(in_progress_today),
                len(upcoming_pressure),
                len(unscheduled),
            ]
        ),
    )
    return DayScheduleResponse(date=target_date, summary=summary, buckets=buckets)


def get_month_schedule(db: Session, year: int, month: int) -> MonthScheduleResponse:
    _, days_in_month = calendar.monthrange(year, month)
    first_day = date(year, month, 1)
    last_day = date(year, month, days_in_month)
    tasks = _active_tasks(db)
    entries_by_date: dict[date, list[TaskScheduleEntry]] = defaultdict(list)
    for entry in _entries_between(db, first_day, last_day):
        entries_by_date[entry.date].append(entry)

    days: list[MonthScheduleDay] = []
    for day_number in range(1, days_in_month + 1):
        current_date = date(year, month, day_number)
        due_ids = {
            task.id for task in tasks if _as_date(task.due_date) == current_date
        }
        overdue_ids = {
            task.id
            for task in tasks
            if (due_date := _as_date(task.due_date)) is not None
            and due_date < current_date
            and current_date <= date.today()
        }
        planned_ids = {entry.task_id for entry in entries_by_date[current_date]}
        in_progress_ids = {
            task.id
            for task in tasks
            if (start_date := _as_date(task.start_date)) is not None
            and (end_date := _as_date(task.end_date)) is not None
            and start_date <= current_date <= end_date
        }
        total_ids = due_ids | overdue_ids | planned_ids | in_progress_ids
        days.append(
            MonthScheduleDay(
                date=current_date,
                due_count=len(due_ids),
                planned_count=len(planned_ids),
                in_progress_count=len(in_progress_ids),
                overdue_count=len(overdue_ids),
                total_count=len(total_ids),
            )
        )

    return MonthScheduleResponse(year=year, month=month, days=days)


def get_range_load(db: Session, start: date, days: int = 7) -> list[dict]:
    """排程负载视图：start 起 days 天内每日已排内容（供 AI 排程使用）。

    与 get_month_schedule 的区别：按任意日期范围取（跨月安全）；
    每日返回任务明细与预估总时长，不只是计数；逾期任务只计入 start 当天。
    """
    tasks = _active_tasks(db)
    end = start + timedelta(days=days - 1)
    entries_by_date: dict[date, list[TaskScheduleEntry]] = defaultdict(list)
    for entry in _entries_between(db, start, end):
        entries_by_date[entry.date].append(entry)

    result: list[dict] = []
    for i in range(days):
        current = start + timedelta(days=i)
        items: list[dict] = []
        seen: set[int] = set()
        for entry in entries_by_date[current]:
            task = entry.task
            if task is None or task.deleted_at is not None or task.status == DONE_STATUS:
                continue
            seen.add(task.id)
            items.append(
                {
                    "task_id": task.id,
                    "title": task.title,
                    "estimated_minutes": task.estimated_minutes,
                    "priority": task.priority,
                }
            )
        for task in tasks:
            due = _as_date(task.due_date)
            if task.id in seen or due is None:
                continue
            # 当天截止计入当天；逾期任务只计入 start 当天（不向后蔓延）
            if due == current or (due < start and current == start):
                items.append(
                    {
                        "task_id": task.id,
                        "title": task.title,
                        "estimated_minutes": task.estimated_minutes,
                        "priority": task.priority,
                    }
                )
        result.append(
            {
                "date": current.isoformat(),
                "weekday": "一二三四五六日"[current.weekday()],
                "count": len(items),
                "total_minutes": sum(it["estimated_minutes"] or 0 for it in items),
                "items": items,
            }
        )
    return result


def _apply_entry_patch(entry: TaskScheduleEntry, patch: dict) -> None:
    for field in ("date", "source", "note", "start_time", "end_time"):
        if field in patch and patch[field] is not None:
            setattr(entry, field, patch[field])


def _get_active_task(db: Session, task_id: int) -> Task | None:
    return db.execute(
        _active_task_stmt().where(Task.id == task_id)
    ).scalar_one_or_none()


def _active_tasks(db: Session) -> list[Task]:
    return list(db.execute(_active_task_stmt().order_by(Task.id)).scalars().all())


def _active_task_stmt():
    return (
        select(Task)
        .options(
            selectinload(Task.files),
            selectinload(Task.tags),
            selectinload(Task.subtasks),
        )
        .where(Task.deleted_at.is_(None), Task.status != DONE_STATUS)
    )


def _entries_for_date(db: Session, target_date: date) -> list[TaskScheduleEntry]:
    return list(
        db.execute(
            _active_entry_stmt()
            .where(TaskScheduleEntry.date == target_date)
            .order_by(TaskScheduleEntry.id)
        )
        .scalars()
        .all()
    )


def _entries_between(
    db: Session, start_date: date, end_date: date
) -> list[TaskScheduleEntry]:
    return list(
        db.execute(
            _active_entry_stmt()
            .where(
                TaskScheduleEntry.date >= start_date,
                TaskScheduleEntry.date <= end_date,
            )
            .order_by(TaskScheduleEntry.date, TaskScheduleEntry.id)
        )
        .scalars()
        .all()
    )


def _active_entry_stmt():
    return (
        select(TaskScheduleEntry)
        .join(Task)
        .options(
            selectinload(TaskScheduleEntry.task).selectinload(Task.files),
            selectinload(TaskScheduleEntry.task).selectinload(Task.tags),
            selectinload(TaskScheduleEntry.task).selectinload(Task.subtasks),
        )
        .where(Task.deleted_at.is_(None), Task.status != DONE_STATUS)
    )


def _scheduled_task_ids(db: Session) -> set[int]:
    return set(
        db.execute(
            select(TaskScheduleEntry.task_id)
            .join(Task)
            .where(Task.deleted_at.is_(None), Task.status != DONE_STATUS)
        ).scalars()
    )


def _task_item(
    task: Task, entry: TaskScheduleEntry | None, reason: str
) -> ScheduleTaskItem:
    return ScheduleTaskItem(
        task=TaskResponse.model_validate(task),
        entry=ScheduleEntryRead.model_validate(entry) if entry is not None else None,
        reason=reason,
    )


def _as_date(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value
