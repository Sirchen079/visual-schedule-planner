from __future__ import annotations

from io import BytesIO

from fastapi import UploadFile
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Task
from app.schemas import TaskCreate
from app.services import ai_attachment_service, file_service, task_service

SAFE_TOOLS = {
    "list_tasks",
    "create_task",
    "list_reminders",
    "create_reminder",
    "list_files",
    "create_note_file",
    "attach_file_to_task",
    "save_attachment_to_library",
}
CONFIRMATION_REQUIRED_TOOLS = {
    "update_task",
    "update_file_notes",
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
    except (ValidationError, KeyError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": "未处理的工具"}


def _create_task_with_optional_files(db: Session, args: dict) -> dict:
    task_args = dict(args)
    file_ids = _pop_file_ids(task_args)
    attachment_ids = _pop_attachment_ids(task_args)
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
    task = task_service.get_task(db, task.id) or task
    return {"ok": True, "task": _task_dict(task)}


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


def _missing_file_ids(db: Session, file_ids: list[int]) -> list[int]:
    return [file_id for file_id in file_ids if file_service.get_file(db, file_id) is None]


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
        "files": [_file_dict(f) for f in task.files if f.deleted_at is None],
    }


def _file_dict(file) -> dict:
    return {
        "id": file.id,
        "original_name": file.original_name,
        "size": file.size,
        "mime_type": file.mime_type,
        "notes": file.notes,
    }
