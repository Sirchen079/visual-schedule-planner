from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import AIPendingAction
from app.schemas import FileUpdate, TaskUpdate
from app.services import file_service, task_service

SUPPORTED_ACTION_TYPES = {
    "update_task",
    "update_file_notes",
    "attach_file_to_task",
    "detach_file_from_task",
    "delete_task",
    "delete_file",
    "bulk_update_tasks",
    "bulk_delete_tasks",
    "bulk_delete_files",
    "empty_trash",
    "import_web_resources",
}


def create_pending_action(
    db: Session,
    conversation_id: int | None,
    action_type: str,
    payload: dict,
    summary: str,
    ttl_minutes: int = 10,
) -> AIPendingAction:
    action = AIPendingAction(
        conversation_id=conversation_id,
        action_type=action_type,
        payload=json.dumps(payload, ensure_ascii=False),
        summary=summary,
        expires_at=datetime.now() + timedelta(minutes=ttl_minutes),
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


def action_preview(db: Session, action: AIPendingAction) -> list[str]:
    try:
        payload = json.loads(action.payload)
    except json.JSONDecodeError:
        return ["操作: 无法解析待确认参数"]
    return build_action_preview(db, action.action_type, payload)


def build_action_preview(db: Session, action_type: str, payload: dict) -> list[str]:
    if action_type == "delete_task":
        raw_task_id = payload.get("task_id")
        task_id = _coerce_int(raw_task_id)
        task = task_service.get_task(db, task_id) if task_id is not None else None
        return [
            "操作: 将任务移入回收站",
            (
                f"任务: #{task.id} {task.title}"
                if task
                else _missing_preview_line("任务", raw_task_id, task_id)
            ),
        ]
    if action_type == "delete_file":
        raw_file_id = payload.get("file_id")
        file_id = _coerce_int(raw_file_id)
        db_file = file_service.get_file(db, file_id) if file_id is not None else None
        return [
            "操作: 将资料移入回收站",
            (
                f"资料: #{db_file.id} {db_file.original_name}"
                if db_file
                else _missing_preview_line("资料", raw_file_id, file_id)
            ),
        ]
    if action_type == "update_task":
        task_id = _coerce_int(payload.get("task_id"))
        patch = dict(payload.get("patch", {}))
        lines = [
            "操作: 更新任务",
            f"字段: {', '.join(sorted(patch)) or '无'}",
        ]
        lines.extend(_task_preview_lines(db, [task_id] if task_id is not None else []))
        if task_id is None:
            lines.append(_missing_preview_line("任务", payload.get("task_id"), None))
        return lines
    if action_type == "update_file_notes":
        file_id = _coerce_int(payload.get("file_id"))
        lines = ["操作: 更新资料备注"]
        lines.extend(_file_preview_lines(db, [file_id] if file_id is not None else []))
        if file_id is None:
            lines.append(_missing_preview_line("资料", payload.get("file_id"), None))
        return lines
    if action_type in {"attach_file_to_task", "detach_file_from_task"}:
        task_id = _coerce_int(payload.get("task_id"))
        file_id = _coerce_int(payload.get("file_id"))
        lines = [
            (
                "操作: 将资料关联到任务"
                if action_type == "attach_file_to_task"
                else "操作: 取消任务与资料关联"
            )
        ]
        lines.extend(_task_preview_lines(db, [task_id] if task_id is not None else []))
        if task_id is None:
            lines.append(_missing_preview_line("任务", payload.get("task_id"), None))
        lines.extend(_file_preview_lines(db, [file_id] if file_id is not None else []))
        if file_id is None:
            lines.append(_missing_preview_line("资料", payload.get("file_id"), None))
        return lines
    if action_type == "bulk_update_tasks":
        task_ids = _coerce_int_list(payload.get("task_ids", []))
        patch = dict(payload.get("patch", {}))
        lines = [f"操作: 批量更新 {len(task_ids)} 个任务", f"字段: {', '.join(sorted(patch)) or '无'}"]
        lines.extend(_task_preview_lines(db, task_ids))
        return lines
    if action_type == "bulk_delete_tasks":
        task_ids = _coerce_int_list(payload.get("task_ids", []))
        return [f"操作: 批量将 {len(task_ids)} 个任务移入回收站", *_task_preview_lines(db, task_ids)]
    if action_type == "bulk_delete_files":
        file_ids = _coerce_int_list(payload.get("file_ids", []))
        return [f"操作: 批量将 {len(file_ids)} 个资料移入回收站", *_file_preview_lines(db, file_ids)]
    if action_type == "empty_trash":
        tasks = list(task_service.list_trash(db))
        files = list(file_service.list_trash(db))
        return [
            "操作: 清空回收站，彻底删除且不可恢复",
            f"任务: {len(tasks)} 个",
            f"资料: {len(files)} 个",
        ]
    if action_type == "import_web_resources":
        resources = _web_resources_for_preview(payload)
        lines = [f"操作: 导入 {len(resources)} 条联网资料到资料库"]
        for resource in resources:
            lines.append(
                f"资料: {resource['title']} | {resource['resource_type']} | {resource['url']}"
            )
            task_id = resource.get("task_id")
            if task_id is not None:
                lines.extend(_task_preview_lines(db, [task_id]))
        return lines
    return [f"操作: 不支持的危险操作 {action_type}"]


def is_supported_action_type(action_type: str) -> bool:
    return action_type in SUPPORTED_ACTION_TYPES


def confirm_action(
    db: Session, action_id: int
) -> tuple[AIPendingAction | None, str | None, str | None]:
    action = db.get(AIPendingAction, action_id)
    if action is None:
        return None, None, "待确认操作不存在"
    if action.status != "pending":
        return action, None, "操作不是待确认状态"
    if action.expires_at < datetime.now():
        action.status = "expired"
        db.commit()
        return action, None, "操作已过期"
    action.confirm_token = AIPendingAction.new_token()
    action.status = "confirmed"
    action.confirmed_at = datetime.now()
    db.commit()
    db.refresh(action)
    return action, action.confirm_token, None


def execute_action(db: Session, action_id: int, token: str) -> tuple[bool, str]:
    action = db.get(AIPendingAction, action_id)
    if action is None:
        return False, "待确认操作不存在"
    if action.status != "confirmed":
        return False, "操作尚未完成第一次确认"
    if action.expires_at < datetime.now():
        action.status = "expired"
        db.commit()
        return False, "操作已过期"
    if not action.confirm_token or action.confirm_token != token:
        return False, "确认 token 无效"
    try:
        payload = json.loads(action.payload)
        ok, message = _execute_payload(db, action.action_type, payload)
    except (KeyError, TypeError, ValueError):
        ok, message = False, "待确认操作参数无效"
    if ok:
        action.status = "executed"
        action.executed_at = datetime.now()
    db.commit()
    return ok, message


def _execute_payload(db: Session, action_type: str, payload: dict) -> tuple[bool, str]:
    if action_type == "delete_task":
        ok = task_service.soft_delete_task(db, int(payload["task_id"]))
        return ok, "任务已移入回收站" if ok else "任务不存在"
    if action_type == "delete_file":
        ok = file_service.soft_delete_file(db, int(payload["file_id"]))
        return ok, "资料已移入回收站" if ok else "资料不存在"
    if action_type == "update_task":
        task_id = int(payload["task_id"])
        task = task_service.get_task(db, task_id)
        if task is None:
            return False, "任务不存在"
        updated = task_service.update_task(db, task_id, TaskUpdate(**dict(payload.get("patch", {}))))
        return updated is not None, "任务已更新" if updated else "任务不存在"
    if action_type == "update_file_notes":
        file_id = int(payload["file_id"])
        updated = file_service.update_file(
            db, file_id, FileUpdate(notes=str(payload.get("notes", "")))
        )
        return updated is not None, "资料备注已更新" if updated else "资料不存在"
    if action_type == "attach_file_to_task":
        ok = file_service.attach_to_task(db, int(payload["task_id"]), int(payload["file_id"]))
        return ok, "资料已关联到任务" if ok else "任务或资料不存在"
    if action_type == "detach_file_from_task":
        ok = file_service.detach_from_task(db, int(payload["task_id"]), int(payload["file_id"]))
        return ok, "资料已从任务解绑" if ok else "任务或关联不存在"
    if action_type == "bulk_update_tasks":
        task_ids = [int(task_id) for task_id in payload.get("task_ids", [])]
        missing = _missing_task_ids(db, task_ids)
        if missing:
            return False, f"任务不存在: {', '.join(str(task_id) for task_id in missing)}"
        patch = TaskUpdate(**dict(payload.get("patch", {})))
        updated = 0
        for task_id in task_ids:
            if task_service.update_task(db, task_id, patch) is not None:
                updated += 1
        return updated == len(task_ids), f"已更新 {updated} 个任务"
    if action_type == "bulk_delete_tasks":
        task_ids = [int(task_id) for task_id in payload.get("task_ids", [])]
        missing = _missing_task_ids(db, task_ids)
        if missing:
            return False, f"任务不存在: {', '.join(str(task_id) for task_id in missing)}"
        deleted = 0
        for task_id in task_ids:
            if task_service.soft_delete_task(db, task_id):
                deleted += 1
        return deleted == len(task_ids), f"已将 {deleted} 个任务移入回收站"
    if action_type == "bulk_delete_files":
        file_ids = [int(file_id) for file_id in payload.get("file_ids", [])]
        missing = _missing_file_ids(db, file_ids)
        if missing:
            return False, f"资料不存在: {', '.join(str(file_id) for file_id in missing)}"
        deleted = 0
        for file_id in file_ids:
            if file_service.soft_delete_file(db, file_id):
                deleted += 1
        return deleted == len(file_ids), f"已将 {deleted} 个资料移入回收站"
    if action_type == "empty_trash":
        tasks = list(task_service.list_trash(db))
        files = list(file_service.list_trash(db))
        for task in tasks:
            task_service.purge_task(db, task.id)
        for file in files:
            file_service.purge_file(db, file.id)
        return True, f"已清空回收站：{len(tasks)} 个任务，{len(files)} 个资料"
    if action_type == "import_web_resources":
        return _execute_import_web_resources(db, payload)
    return False, f"不支持的危险操作: {action_type}"


def _execute_import_web_resources(db: Session, payload: dict) -> tuple[bool, str]:
    resources = _normalize_web_resources(payload)
    if not resources:
        return False, "没有可导入的联网资料"
    missing_tasks = _missing_task_ids(
        db,
        sorted(
            {
                int(resource["task_id"])
                for resource in resources
                if resource.get("task_id") is not None
            }
        ),
    )
    if missing_tasks:
        return False, f"任务不存在: {', '.join(str(task_id) for task_id in missing_tasks)}"
    created = []
    for resource in resources:
        db_file = file_service.save_link_resource(
            db,
            title=resource["title"],
            url=resource["url"],
            notes=resource.get("notes", ""),
            resource_type=resource.get("resource_type", "link"),
        )
        task_id = resource.get("task_id")
        if task_id is not None:
            file_service.attach_to_task(db, int(task_id), db_file.id)
        created.append(db_file)
    return True, f"已导入 {len(created)} 条联网资料"


def _missing_task_ids(db: Session, task_ids: list[int]) -> list[int]:
    return [task_id for task_id in task_ids if task_service.get_task(db, task_id) is None]


def _missing_file_ids(db: Session, file_ids: list[int]) -> list[int]:
    return [file_id for file_id in file_ids if file_service.get_file(db, file_id) is None]


def _task_preview_lines(db: Session, task_ids: list[int]) -> list[str]:
    lines = []
    for task_id in task_ids:
        task = task_service.get_task(db, task_id)
        lines.append(f"任务: #{task.id} {task.title}" if task else f"任务: #{task_id} 不存在")
    return lines


def _file_preview_lines(db: Session, file_ids: list[int]) -> list[str]:
    lines = []
    for file_id in file_ids:
        db_file = file_service.get_file(db, file_id)
        lines.append(f"资料: #{db_file.id} {db_file.original_name}" if db_file else f"资料: #{file_id} 不存在")
    return lines


def _coerce_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_int_list(values) -> list[int]:
    if not isinstance(values, list):
        return []
    return [item for item in (_coerce_int(value) for value in values) if item is not None]


def _web_resources_for_preview(payload: dict) -> list[dict]:
    try:
        return _normalize_web_resources(payload, validate_url=False)
    except (TypeError, ValueError):
        return []


def _normalize_web_resources(payload: dict, validate_url: bool = True) -> list[dict]:
    raw_resources = payload.get("resources", [])
    if isinstance(raw_resources, dict):
        raw_resources = [raw_resources]
    if not isinstance(raw_resources, list):
        raise ValueError("resources 必须是数组")
    default_task_id = _coerce_int(payload.get("task_id"))
    resources = []
    seen = set()
    for item in raw_resources:
        if not isinstance(item, dict):
            raise ValueError("resources 每一项必须是对象")
        url = str(item.get("url", "")).strip()
        clean_url = file_service.validate_source_url(url) if validate_url else url
        if not clean_url:
            raise ValueError("联网资料缺少 URL")
        title = str(item.get("title") or item.get("name") or clean_url).strip()
        notes = str(item.get("notes") or item.get("summary") or "").strip()
        resource_type = file_service.normalize_resource_type(item.get("resource_type") or item.get("type"))
        task_id = _coerce_int(item.get("task_id"))
        if task_id is None:
            task_id = default_task_id
        key = clean_url.lower()
        if key in seen:
            continue
        seen.add(key)
        resources.append(
            {
                "title": title[:255] or clean_url,
                "url": clean_url,
                "notes": notes,
                "resource_type": resource_type,
                "task_id": task_id,
            }
        )
    return resources


def _missing_preview_line(label: str, raw_id, parsed_id: int | None) -> str:
    if parsed_id is None:
        return f"{label}: #{raw_id} 参数无效"
    return f"{label}: #{parsed_id} 不存在"
