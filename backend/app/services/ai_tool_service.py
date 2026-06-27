from __future__ import annotations

from io import BytesIO

from fastapi import UploadFile
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Task
from app.schemas import TaskCreate
from app.services import file_service, task_service

SAFE_TOOLS = {
    "list_tasks",
    "create_task",
    "list_reminders",
    "create_reminder",
    "list_files",
    "create_note_file",
}
CONFIRMATION_REQUIRED_TOOLS = {
    "update_task",
    "update_file_notes",
    "attach_file_to_task",
    "detach_file_from_task",
}


def execute_tool(db: Session, name: str, args: dict) -> dict:
    if name in CONFIRMATION_REQUIRED_TOOLS:
        return {"ok": False, "error": f"工具需要待确认操作，不能直接执行: {name}"}
    if name not in SAFE_TOOLS:
        return {"ok": False, "error": f"工具不允许直接执行: {name}"}
    args = dict(args or {})
    try:
        if name == "list_tasks":
            return {"ok": True, "tasks": [_task_dict(t) for t in task_service.list_tasks(db)]}
        if name == "create_task":
            task = task_service.create_task(db, TaskCreate(**args))
            return {"ok": True, "task": _task_dict(task)}
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
            task = task_service.create_task(db, TaskCreate(**reminder_args))
            return {"ok": True, "task": _task_dict(task)}
        if name == "list_files":
            return {
                "ok": True,
                "files": [_file_dict(f) for f in file_service.list_files(db, args.get("q"))],
            }
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
    except (ValidationError, KeyError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": "未处理的工具"}


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
        "tags": [t.name for t in task.tags],
    }


def _file_dict(file) -> dict:
    return {
        "id": file.id,
        "original_name": file.original_name,
        "size": file.size,
        "mime_type": file.mime_type,
        "notes": file.notes,
    }
