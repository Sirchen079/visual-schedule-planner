from __future__ import annotations

from io import BytesIO
from datetime import date as date_type

from fastapi import UploadFile
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Task
from app.schemas import (
    GoalCreate,
    HabitCreate,
    JournalUpsert,
    KeyResultCreate,
    KeyResultUpdate,
    ScheduleEntryCreate,
    ScheduleEntryRead,
    SubtaskCreate,
    TaskCreate,
)
from app.services import (
    ai_attachment_service,
    app_setting_service,
    file_service,
    goal_service,
    habit_service,
    journal_service,
    schedule_service,
    subtask_service,
    task_service,
    timer_service,
)

SAFE_TOOLS = {
    "list_tasks",
    "create_task",
    "list_reminders",
    "create_reminder",
    "list_files",
    "create_note_file",
    "attach_file_to_task",
    "save_attachment_to_library",
    "list_subtasks",
    "create_subtask",
    "create_subtasks",
    "list_day_schedule",
    "list_month_schedule",
    "assign_task_to_day",
    "list_habits",
    "create_habit",
    "check_in_habit",
    "list_journal_entries",
    "write_journal",
    "list_goals",
    "create_goal",
    "update_kr_progress",
    "start_timer",
    "stop_timer",
}
CONFIRMATION_REQUIRED_TOOLS = {
    "update_task",
    "update_file_notes",
    "detach_file_from_task",
}

# 功能开关门控：功能在「功能管理」里被关闭时，对应工具组整体不可用
TOOL_FEATURE_FLAGS = {
    "list_habits": "feature_habits_enabled",
    "create_habit": "feature_habits_enabled",
    "check_in_habit": "feature_habits_enabled",
    "list_journal_entries": "feature_journal_enabled",
    "write_journal": "feature_journal_enabled",
    "list_goals": "feature_goals_enabled",
    "create_goal": "feature_goals_enabled",
    "update_kr_progress": "feature_goals_enabled",
    "start_timer": "feature_timer_enabled",
    "stop_timer": "feature_timer_enabled",
}


def execute_tool(db: Session, name: str, args: dict) -> dict:
    if name in CONFIRMATION_REQUIRED_TOOLS:
        return {"ok": False, "error": f"工具需要待确认操作，不能直接执行: {name}"}
    if name not in SAFE_TOOLS:
        return {"ok": False, "error": f"工具不允许直接执行: {name}"}
    feature_flag = TOOL_FEATURE_FLAGS.get(name)
    if feature_flag and not app_setting_service.feature_enabled(db, feature_flag):
        return {"ok": False, "error": "该功能已被用户关闭（可在功能管理中开启），请改用其他方式协助用户"}
    args = dict(args or {})
    try:
        if name == "list_tasks":
            return {"ok": True, "tasks": [_task_dict(t) for t in task_service.list_tasks(db)]}
        if name == "create_task":
            return _create_task_with_optional_files(db, args)
        if name == "list_reminders":
            stmt = (
                select(Task)
                .where(Task.deleted_at.is_(None), Task.due_date.is_not(None))
                .order_by(Task.due_date)
            )
            return {
                "ok": True,
                "reminders": [_task_dict(t) for t in db.execute(stmt).scalars().all()],
            }
        if name == "create_reminder":
            reminder_args = dict(args)
            if not reminder_args.get("due_date"):
                return {"ok": False, "error": "创建提醒需要 due_date"}
            tags = reminder_args.get("tags") or []
            if "提醒" not in tags:
                reminder_args["tags"] = [*tags, "提醒"]
            return _create_task_with_optional_files(db, reminder_args)
        if name == "list_files":
            return {
                "ok": True,
                "files": [_file_dict(f) for f in file_service.list_files(db, args.get("q"))],
            }
        if name == "list_subtasks":
            task = task_service.get_task(db, int(args["task_id"]))
            if task is None:
                return {"ok": False, "error": "任务不存在"}
            return {
                "ok": True,
                "task": _task_dict(task),
                "subtasks": [_subtask_dict(s) for s in task.subtasks],
            }
        if name == "create_subtask":
            subtask = subtask_service.create_subtask(
                db, int(args["task_id"]), SubtaskCreate(title=str(args["title"]))
            )
            if subtask is None:
                return {"ok": False, "error": "任务不存在"}
            task = task_service.get_task(db, int(args["task_id"]))
            return {"ok": True, "task": _task_dict(task), "subtask": _subtask_dict(subtask)}
        if name == "create_subtasks":
            return _create_subtasks(db, int(args["task_id"]), _pop_subtask_titles(args))
        if name == "list_day_schedule":
            target_date = _parse_iso_date(args.get("date"))
            if target_date is None:
                return {"ok": False, "error": "list_day_schedule 需要 ISO 格式 date"}
            schedule = schedule_service.get_day_schedule(db, target_date)
            return {"ok": True, "schedule": _dump_model(schedule)}
        if name == "list_month_schedule":
            year = _coerce_int(args.get("year"))
            month = _coerce_int(args.get("month"))
            if year is None or month is None:
                return {"ok": False, "error": "list_month_schedule 需要 year 和 month"}
            if year < 1 or year > 9999 or month < 1 or month > 12:
                return {"ok": False, "error": "year 或 month 超出范围"}
            schedule = schedule_service.get_month_schedule(db, year, month)
            return {"ok": True, "schedule": _dump_model(schedule)}
        if name == "assign_task_to_day":
            return _assign_task_to_day(db, args)
        if name == "create_note_file":
            title = (args.get("title") or "AI 资料笔记").strip()
            content = args.get("content") or ""
            upload = UploadFile(
                filename=f"{title}.txt", file=BytesIO(content.encode("utf-8"))
            )
            db_file = file_service.save_upload(
                db, upload, args.get("notes", "AI 保存的资料笔记")
            )
            return {"ok": True, "file": _file_dict(db_file)}
        if name == "attach_file_to_task":
            task_id = int(args["task_id"])
            file_id = int(args["file_id"])
            ok = file_service.attach_to_task(db, task_id, file_id)
            if not ok:
                return {"ok": False, "error": "任务或资料不存在"}
            task = task_service.get_task(db, task_id)
            db_file = file_service.get_file(db, file_id)
            return {"ok": True, "task": _task_dict(task), "file": _file_dict(db_file)}
        if name == "save_attachment_to_library":
            task_id = int(args["task_id"]) if args.get("task_id") else None
            db_file = ai_attachment_service.save_to_library(
                db,
                str(args["attachment_id"]),
                args.get("notes", "由 AI 从对话附件保存到资料库"),
                task_id,
            )
            result = {"ok": True, "file": _file_dict(db_file)}
            if task_id:
                task = task_service.get_task(db, task_id)
                result["task"] = _task_dict(task)
            return result
        if name == "list_habits":
            return {"ok": True, "habits": [_habit_dict(h) for h in habit_service.list_habits(db)]}
        if name == "create_habit":
            habit = habit_service.create_habit(
                db,
                HabitCreate(
                    name=str(args.get("name") or "").strip() or "新习惯",
                    notes=args.get("notes", ""),
                    period=args.get("period", "daily"),
                    target_count=_coerce_int(args.get("target_count")) or 1,
                ),
            )
            return {"ok": True, "habit": _habit_dict(habit)}
        if name == "check_in_habit":
            day = _parse_iso_date(args.get("date")) if args.get("date") else None
            habit = habit_service.check_in(db, int(args["habit_id"]), day)
            if habit is None:
                return {"ok": False, "error": "习惯不存在"}
            return {"ok": True, "habit": _habit_dict(habit)}
        if name == "list_journal_entries":
            limit = _coerce_int(args.get("limit")) or 10
            entries = journal_service.list_entries(db, limit)
            return {
                "ok": True,
                "entries": [
                    {
                        "date": e.date.isoformat(),
                        "preview": (e.content or "")[:200],
                        "mood": e.mood,
                    }
                    for e in entries
                ],
            }
        if name == "write_journal":
            day = _parse_iso_date(args.get("date")) if args.get("date") else date_type.today()
            content = str(args.get("content") or "")
            if not content.strip():
                return {"ok": False, "error": "write_journal 需要 content"}
            entry = journal_service.upsert_entry(
                db, day, JournalUpsert(content=content, mood=args.get("mood"))
            )
            return {"ok": True, "entry": {"date": entry.date.isoformat(), "mood": entry.mood}}
        if name == "list_goals":
            return {"ok": True, "goals": [_goal_dict(db, g) for g in goal_service.list_goals(db)]}
        if name == "create_goal":
            krs = [
                KeyResultCreate(
                    title=str(kr.get("title") or "").strip() or "关键结果",
                    kind=kr.get("kind", "manual"),
                    target_value=float(kr.get("target_value") or 1),
                    unit=kr.get("unit", ""),
                    link=kr.get("link", {}) if isinstance(kr.get("link"), dict) else {},
                )
                for kr in (args.get("key_results") or [])
                if isinstance(kr, dict)
            ]
            goal = goal_service.create_goal(
                db,
                GoalCreate(
                    title=str(args.get("title") or "").strip() or "新目标",
                    notes=args.get("notes", ""),
                    start_date=_parse_iso_date(args.get("start_date")),
                    end_date=_parse_iso_date(args.get("end_date")),
                    key_results=krs,
                ),
            )
            return {"ok": True, "goal": _goal_dict(db, goal)}
        if name == "update_kr_progress":
            kr = goal_service.update_key_result(
                db,
                int(args["kr_id"]),
                KeyResultUpdate(current_value=float(args["current_value"])),
            )
            if kr is None:
                return {"ok": False, "error": "关键结果不存在"}
            goal = goal_service.get_goal(db, kr.goal_id)
            current, progress = goal_service.kr_progress(db, kr, goal)
            return {
                "ok": True,
                "kr": {"id": kr.id, "title": kr.title, "current_value": current, "progress": progress},
            }
        if name == "start_timer":
            task = task_service.get_task(db, int(args["task_id"]))
            if task is None:
                return {"ok": False, "error": "任务不存在"}
            log = timer_service.start_timer(db, task, args.get("kind", "pomodoro"))
            return {"ok": True, "timer": _timer_dict(log)}
        if name == "stop_timer":
            log = timer_service.stop_timer(db)
            if log is None:
                return {"ok": False, "error": "没有运行中的计时"}
            return {"ok": True, "timer": _timer_dict(log)}
    except (ValidationError, KeyError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": "未处理的工具"}


def _create_task_with_optional_files(db: Session, args: dict) -> dict:
    task_args = dict(args)
    file_ids = _pop_file_ids(task_args)
    attachment_ids = _pop_attachment_ids(task_args)
    subtask_titles = _pop_subtask_titles(task_args)
    missing = _missing_file_ids(db, file_ids)
    if missing:
        return {"ok": False, "error": f"资料不存在: {', '.join(str(i) for i in missing)}"}
    task = task_service.create_task(db, TaskCreate(**task_args))
    for attachment_id in attachment_ids:
        db_file = ai_attachment_service.save_to_library(
            db, attachment_id, "由 AI 从对话附件保存到资料库", task.id
        )
        if db_file.id not in file_ids:
            file_ids.append(db_file.id)
    for file_id in file_ids:
        file_service.attach_to_task(db, task.id, file_id)
    for title in subtask_titles:
        subtask_service.create_subtask(db, task.id, SubtaskCreate(title=title))
    task = task_service.get_task(db, task.id) or task
    return {"ok": True, "task": _task_dict(task)}


def _create_subtasks(db: Session, task_id: int, titles: list[str]) -> dict:
    if not titles:
        return {"ok": False, "error": "创建子任务需要 titles 或 subtasks"}
    created = []
    for title in titles:
        subtask = subtask_service.create_subtask(db, task_id, SubtaskCreate(title=title))
        if subtask is None:
            return {"ok": False, "error": "任务不存在"}
        created.append(subtask)
    task = task_service.get_task(db, task_id)
    return {
        "ok": True,
        "task": _task_dict(task),
        "subtasks": [_subtask_dict(s) for s in created],
    }


def _assign_task_to_day(db: Session, args: dict) -> dict:
    task_id = _coerce_int(args.get("task_id"))
    target_date = _parse_iso_date(args.get("date"))
    if task_id is None:
        return {"ok": False, "error": "assign_task_to_day 需要 task_id"}
    if target_date is None:
        return {"ok": False, "error": "assign_task_to_day 需要 ISO 格式 date"}
    note = str(args.get("note") or "").strip()
    try:
        entry = schedule_service.create_schedule_entry(
            db,
            ScheduleEntryCreate(
                task_id=task_id,
                date=target_date,
                source="ai",
                note=note,
            ),
        )
    except schedule_service.ScheduleTaskNotFound:
        return {"ok": False, "error": "任务不存在或不可安排"}
    schedule = schedule_service.get_day_schedule(db, target_date)
    return {
        "ok": True,
        "entry": _schedule_entry_dict(entry),
        "day_summary": _schedule_summary_dict(schedule.summary),
        "schedule": _dump_model(schedule),
    }


def _pop_file_ids(args: dict) -> list[int]:
    raw = args.pop("file_ids", args.pop("files", []))
    if raw is None or raw == "":
        return []
    if isinstance(raw, (int, str)):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError("file_ids 必须是数字或数字数组")
    ids = []
    for item in raw:
        file_id = int(item)
        if file_id not in ids:
            ids.append(file_id)
    return ids


def _pop_attachment_ids(args: dict) -> list[str]:
    raw = args.pop("attachment_ids", args.pop("attachments", []))
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError("attachment_ids 必须是字符串或字符串数组")
    ids = []
    for item in raw:
        attachment_id = str(item)
        if attachment_id not in ids:
            ids.append(attachment_id)
    return ids


def _pop_subtask_titles(args: dict) -> list[str]:
    raw = args.pop("titles", args.pop("subtask_titles", args.pop("subtasks", [])))
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError("子任务必须是字符串或数组")
    titles = []
    for item in raw:
        if isinstance(item, dict):
            title = str(item.get("title", "")).strip()
        else:
            title = str(item).strip()
        if title and title not in titles:
            titles.append(title)
    return titles


def _missing_file_ids(db: Session, file_ids: list[int]) -> list[int]:
    return [file_id for file_id in file_ids if file_service.get_file(db, file_id) is None]


def _coerce_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_iso_date(value) -> date_type | None:
    try:
        return date_type.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _schedule_entry_dict(entry) -> dict:
    return ScheduleEntryRead.model_validate(entry).model_dump(mode="json")


def _schedule_summary_dict(summary) -> dict:
    if hasattr(summary, "model_dump"):
        return summary.model_dump(mode="json")
    return dict(summary)


def _dump_model(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


def _task_dict(task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "notes": task.notes,
        "status": task.status,
        "priority": task.priority,
        "progress": task.progress,
        "start_date": task.start_date.isoformat() if task.start_date else None,
        "end_date": task.end_date.isoformat() if task.end_date else None,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "due_time": task.due_time,
        "remind_offsets": task.remind_offsets,
        "recur_rule": task.recur_rule,
        "recur_interval": task.recur_interval,
        "tags": [t.name for t in task.tags],
        "files": [_file_dict(f) for f in task.files if f.deleted_at is None],
        "subtasks": [_subtask_dict(s) for s in task.subtasks],
    }


def _habit_dict(habit) -> dict:
    status = habit_service.habit_status(habit)
    return {
        "id": habit.id,
        "name": habit.name,
        "notes": habit.notes,
        "period": habit.period,
        "target_count": habit.target_count,
        **status,
    }


def _goal_dict(db: Session, goal) -> dict:
    krs = []
    for kr in goal.key_results:
        current, progress = goal_service.kr_progress(db, kr, goal)
        krs.append(
            {
                "id": kr.id,
                "title": kr.title,
                "kind": kr.kind,
                "target_value": kr.target_value,
                "current_value": current,
                "unit": kr.unit,
                "progress": progress,
            }
        )
    return {
        "id": goal.id,
        "title": goal.title,
        "status": goal.status,
        "progress": goal_service.goal_progress(db, goal),
        "key_results": krs,
    }


def _timer_dict(log) -> dict:
    return {
        "id": log.id,
        "task_id": log.task_id,
        "task_title": log.task_title,
        "kind": log.kind,
        "started_at": log.started_at.isoformat(),
        "ended_at": log.ended_at.isoformat() if log.ended_at else None,
        "minutes": log.minutes,
    }


def _file_dict(file) -> dict:
    return {
        "id": file.id,
        "original_name": file.original_name,
        "size": file.size,
        "mime_type": file.mime_type,
        "notes": file.notes,
        "source_url": file.source_url,
        "resource_type": file.resource_type,
    }


def _subtask_dict(subtask) -> dict:
    return {
        "id": subtask.id,
        "task_id": subtask.task_id,
        "title": subtask.title,
        "done": subtask.done,
        "completed_at": subtask.completed_at.isoformat() if subtask.completed_at else None,
    }
