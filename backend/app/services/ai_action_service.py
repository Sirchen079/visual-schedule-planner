from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AIPendingAction, AISkill, MCPServer, TaskScheduleEntry
from app.schemas import (
    AISkillCreate,
    AISkillUpdate,
    FileUpdate,
    GoalUpdate,
    HabitUpdate,
    MCPServerCreate,
    MCPServerUpdate,
    ScheduleEntryCreate,
    ScheduleEntryUpdate,
    SubtaskUpdate,
    TaskUpdate,
)
from app.services import (
    ai_skill_service,
    app_setting_service,
    file_service,
    goal_service,
    habit_service,
    mcp_service,
    schedule_service,
    subtask_service,
    task_service,
)

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
    "update_schedule_entry",
    "delete_schedule_entry",
    "bulk_assign_tasks_to_days",
    "auto_plan_tasks",
    "mcp_tool_call",
    "create_skill",
    "create_mcp_server",
    # 阶段 B5：补齐 CRUD 缺口（习惯/目标/提醒/子任务 update/delete + 设置改）
    "update_habit",
    "delete_habit",
    "update_goal",
    "delete_goal",
    "update_reminder",
    "delete_reminder",
    "update_subtask",
    "delete_subtask",
    "update_setting",
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
    if action_type == "update_schedule_entry":
        entry_id = _coerce_int(payload.get("entry_id"))
        entry = _schedule_entry_for_preview(db, entry_id)
        patch = dict(payload.get("patch", {}))
        lines = [
            "操作: 更新日程条目",
            f"字段: {', '.join(sorted(patch)) or '无'}",
        ]
        if entry is None:
            lines.append(_missing_preview_line("日程条目", payload.get("entry_id"), entry_id))
            return lines
        lines.extend(
            [
                f"条目: #{entry.id} {entry.task.title}",
                f"原日期: {entry.date.isoformat()}",
                f"新日期: {patch.get('date', entry.date.isoformat())}",
                f"原备注: {entry.note or '无'}",
                f"新备注: {patch.get('note', entry.note or '无')}",
            ]
        )
        return lines
    if action_type == "delete_schedule_entry":
        entry_id = _coerce_int(payload.get("entry_id"))
        entry = _schedule_entry_for_preview(db, entry_id)
        lines = ["操作: 删除日程条目"]
        if entry is None:
            lines.append(_missing_preview_line("日程条目", payload.get("entry_id"), entry_id))
            return lines
        lines.extend(
            [
                f"条目: #{entry.id} {entry.task.title}",
                f"日期: {entry.date.isoformat()}",
                f"备注: {entry.note or '无'}",
            ]
        )
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
    if action_type in {"bulk_assign_tasks_to_days", "auto_plan_tasks"}:
        assignments = _normalize_schedule_assignments(payload)
        prefix = "操作: 自动排程" if action_type == "auto_plan_tasks" else "操作: 批量安排日程"
        lines = [f"{prefix} {len(assignments)} 项"]
        for item in assignments:
            task = task_service.get_task(db, item["task_id"]) if item["task_id"] is not None else None
            if task is None:
                lines.append(_missing_preview_line("任务", item["task_id"], item["task_id"]))
            else:
                span = ""
                if item.get("start_time"):
                    span = f" {item['start_time']}" + (f"-{item['end_time']}" if item.get("end_time") else "")
                lines.append(f"任务: #{task.id} {task.title} -> {item['date'].isoformat()}{span}")
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
    if action_type == "mcp_tool_call":
        server_id = _coerce_int(payload.get("server_id"))
        tool_name = str(payload.get("tool_name", ""))
        arguments = payload.get("arguments", {})
        server = db.get(MCPServer, server_id) if server_id else None
        server_label = (
            f"#{server.id} {server.name}" if server else _missing_preview_line("MCP 服务器", payload.get("server_id"), server_id)
        )
        args_json = json.dumps(arguments, ensure_ascii=False, default=str)
        if len(args_json) > 500:
            args_json = args_json[:500] + "...[已截断]"
        return [
            "操作: 调用 MCP 工具（外部服务器，可能产生外部副作用）",
            f"服务器: {server_label}",
            f"工具: {tool_name}",
            f"参数: {args_json}",
        ]
    if action_type == "create_skill":
        name = str(payload.get("name", "")).strip() or "(未命名)"
        content = str(payload.get("content", ""))
        preview = content[:120].replace("\n", " ")
        suffix = "..." if len(content) > 120 else ""
        lines = [
            "操作: 创建助手 skill（会注入后续对话的工作规则）",
            f"名称: {name}",
            f"内容预览: {preview}{suffix}",
        ]
        if payload.get("enabled"):
            lines.append("同时启用该 skill")
        return lines
    if action_type == "create_mcp_server":
        return _mcp_server_preview_lines(payload)
    return [f"操作: 不支持的危险操作 {action_type}"]


def _mcp_server_preview_lines(payload: dict) -> list[str]:
    name = str(payload.get("name", "")).strip() or "(未命名)"
    transport = str(payload.get("transport", "stdio"))
    lines = [
        "操作: 配置 MCP 工具服务器（stdio 可执行本地命令 / http 访问远程，属高敏感操作）",
        f"名称: {name}",
        f"传输: {transport}",
    ]
    if transport == "http":
        lines.append(f"URL: {payload.get('url', '')}")
        header_keys = list((payload.get("headers") or {}).keys())
        if header_keys:
            lines.append(f"请求头: {', '.join(header_keys)}（值加密保存）")
    else:
        command = str(payload.get("command", ""))
        args = payload.get("args") or []
        arg_text = " ".join(str(a) for a in args)
        lines.append(f"命令: {command} {arg_text}".rstrip())
        env_keys = list((payload.get("env") or {}).keys())
        if env_keys:
            lines.append(f"环境变量: {', '.join(env_keys)}（值加密保存）")
    if payload.get("auto_approve_readonly"):
        lines.append("已勾选：只读工具免确认")
    lines.append("确认后创建；请到 MCP 面板测试连接再决定是否启用")
    return lines


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


def reject_action(
    db: Session, action_id: int
) -> tuple[AIPendingAction | None, str | None]:
    """用户拒绝待确认操作：pending/confirmed（未执行）→ rejected，终态，不可再确认执行。"""
    action = db.get(AIPendingAction, action_id)
    if action is None:
        return None, "待确认操作不存在"
    if action.status not in ("pending", "confirmed"):
        return action, "操作不是待确认状态"
    if action.expires_at < datetime.now():
        action.status = "expired"
        db.commit()
        return action, "操作已过期"
    action.status = "rejected"
    action.confirm_token = None
    db.commit()
    db.refresh(action)
    return action, None


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
    if action_type == "update_schedule_entry":
        entry_id = int(payload["entry_id"])
        patch = payload.get("patch", {})
        updated = schedule_service.update_schedule_entry(
            db, entry_id, ScheduleEntryUpdate(**dict(patch))
        )
        return updated is not None, "日程条目已更新" if updated else "日程条目不存在"
    if action_type == "delete_schedule_entry":
        entry_id = int(payload["entry_id"])
        deleted = schedule_service.delete_schedule_entry(db, entry_id)
        return deleted, "日程条目已删除" if deleted else "日程条目不存在"
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
    if action_type in {"bulk_assign_tasks_to_days", "auto_plan_tasks"}:
        assignments = _normalize_schedule_assignments(payload)
        if not assignments:
            return False, "没有可安排的日程"
        missing_task_ids = _missing_task_ids(db, [item["task_id"] for item in assignments])
        if missing_task_ids:
            return False, f"任务不存在: {', '.join(str(task_id) for task_id in missing_task_ids)}"
        created = 0
        for item in assignments:
            entry = schedule_service.create_schedule_entry(
                db,
                ScheduleEntryCreate(
                    task_id=item["task_id"],
                    date=item["date"],
                    source="ai",
                    note=item.get("note", ""),
                    start_time=item.get("start_time"),
                    end_time=item.get("end_time"),
                ),
            )
            if entry is not None:
                created += 1
        return created == len(assignments), f"已安排 {created} 个日程"
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
    if action_type == "mcp_tool_call":
        return _execute_mcp_tool_call(db, payload)
    if action_type == "create_skill":
        return _execute_create_skill(db, payload)
    if action_type == "create_mcp_server":
        return _execute_create_mcp_server(db, payload)
    # ---- 阶段 B5：补齐 CRUD 缺口 ----
    if action_type == "update_habit":
        habit_id = int(payload["habit_id"])
        updated = habit_service.update_habit(db, habit_id, HabitUpdate(**dict(payload.get("patch", {}))))
        return updated is not None, "习惯已更新" if updated else "习惯不存在"
    if action_type == "delete_habit":
        ok = habit_service.soft_delete_habit(db, int(payload["habit_id"]))
        return ok, "习惯已移入回收站" if ok else "习惯不存在"
    if action_type == "update_goal":
        goal_id = int(payload["goal_id"])
        updated = goal_service.update_goal(db, goal_id, GoalUpdate(**dict(payload.get("patch", {}))))
        return updated is not None, "目标已更新" if updated else "目标不存在"
    if action_type == "delete_goal":
        ok = goal_service.soft_delete_goal(db, int(payload["goal_id"]))
        return ok, "目标已移入回收站" if ok else "目标不存在"
    if action_type == "update_reminder":
        # 提醒=带 due_date 的任务，复用任务更新
        task_id = int(payload["task_id"])
        updated = task_service.update_task(db, task_id, TaskUpdate(**dict(payload.get("patch", {}))))
        return updated is not None, "提醒已更新" if updated else "提醒/任务不存在"
    if action_type == "delete_reminder":
        ok = task_service.soft_delete_task(db, int(payload["task_id"]))
        return ok, "提醒已移入回收站" if ok else "提醒/任务不存在"
    if action_type == "update_subtask":
        task_id = int(payload["task_id"])
        subtask_id = int(payload["subtask_id"])
        updated = subtask_service.update_subtask(
            db, task_id, subtask_id, SubtaskUpdate(**dict(payload.get("patch", {})))
        )
        return updated is not None, "子任务已更新" if updated else "子任务不存在"
    if action_type == "delete_subtask":
        ok = subtask_service.delete_subtask(db, int(payload["task_id"]), int(payload["subtask_id"]))
        return ok, "子任务已删除" if ok else "子任务不存在"
    if action_type == "update_setting":
        key = str(payload.get("key", "")).strip()
        value = str(payload.get("value", ""))
        if not key:
            return False, "设置项键名不能为空"
        app_setting_service.update_settings(db, {key: value})
        return True, f"设置项 {key} 已更新"
    return False, f"不支持的危险操作: {action_type}"


def _execute_create_skill(db: Session, payload: dict) -> tuple[bool, str]:
    name = str(payload.get("name", "")).strip()
    content = str(payload.get("content", "")).strip()
    if not name or not content:
        return False, "create_skill 需要 name 和 content"
    if len(content) > 20000:
        return False, "skill 内容超过 20000 字上限，请精简后重试"
    description = str(payload.get("description", "")).strip()
    existing = db.execute(
        select(AISkill)
        .where(AISkill.name == name)
        .order_by(AISkill.updated_at.desc(), AISkill.id.desc())
        .limit(1)
    ).scalars().first()
    if existing is not None and existing.is_builtin:
        return False, f"「{name}」是系统内置 skill 名称，请换一个名称"
    if existing is None:
        skill = ai_skill_service.create_skill(
            db,
            AISkillCreate(name=name[:100], description=description, content=content),
        )
        action = "创建"
    else:
        skill = ai_skill_service.update_skill(
            db, existing.id, AISkillUpdate(description=description, content=content)
        )
        if skill is None:
            # 极小概率：select 与 update 之间被删除。graceful 失败而非 AttributeError→500
            return False, f"skill「{name}」已被删除，请重试"
        action = "更新"
    if payload.get("enabled"):
        ai_skill_service.enable_skill(db, skill.id)
    return True, f"已{action} skill「{name}」"


def _execute_create_mcp_server(db: Session, payload: dict) -> tuple[bool, str]:
    name = str(payload.get("name", "")).strip()
    if not name:
        return False, "create_mcp_server 需要 name"
    transport = str(payload.get("transport", "stdio")).strip()
    if transport not in {"stdio", "http"}:
        return False, "transport 只允许 stdio 或 http"
    # enabled / auto_approve_readonly 显式传入才写；更新时省略表示保留现值，
    # 避免省略字段静默把用户已停用 / 已关闭只读免确认的服务器改回去。
    enabled_given = payload.get("enabled")
    auto_approve_given = payload.get("auto_approve_readonly")
    server_data = {
        "name": name[:100],
        "transport": transport,
        "command": payload.get("command"),
        "args": list(payload.get("args") or []),
        "env": dict(payload.get("env") or {}),
        "url": payload.get("url"),
        "headers": dict(payload.get("headers") or {}),
        "timeout_sec": _coerce_int(payload.get("timeout_sec")) or 30,
        "enabled": bool(enabled_given) if enabled_given is not None else True,
        "auto_approve_readonly": bool(auto_approve_given) if auto_approve_given is not None else False,
    }
    try:
        create_payload = MCPServerCreate(**server_data)  # 触发传输字段校验
    except ValueError as exc:
        return False, f"MCP 配置无效: {exc}"
    existing = db.execute(select(MCPServer).where(MCPServer.name == name)).scalar_one_or_none()
    if existing is None:
        mcp_service.create_server(db, create_payload)
        action = "创建"
    else:
        update_data = dict(server_data)
        if enabled_given is None:
            update_data.pop("enabled", None)  # 保留现值
        if auto_approve_given is None:
            update_data.pop("auto_approve_readonly", None)  # 保留现值
        mcp_service.update_server(db, existing.id, MCPServerUpdate(**update_data))
        action = "更新"
    return True, f"已{action} MCP 服务器「{name}」，请到 MCP 面板测试连接"


def _execute_mcp_tool_call(db: Session, payload: dict) -> tuple[bool, str]:
    """确认后执行 MCP 工具调用，返回工具文本结果（超长截断）。"""
    server_id = _coerce_int(payload.get("server_id"))
    tool_name = str(payload.get("tool_name", "")).strip()
    arguments = payload.get("arguments", {})
    if server_id is None:
        return False, "MCP 工具调用缺少 server_id"
    if not tool_name:
        return False, "MCP 工具调用缺少 tool_name"
    if not isinstance(arguments, dict):
        return False, "MCP 工具参数 arguments 必须是对象"
    # tool_name 可能是原始名，也可能（截断场景下）是 namespaced 形态：按 namespaced 还原
    resolved = mcp_service.resolve_tool_name(db, server_id, tool_name)
    outcome = mcp_service.call_tool(db, server_id, resolved or tool_name, arguments)
    if outcome.get("ok"):
        text = str(outcome.get("text", ""))
        if len(text) > 2000:
            text = text[:2000] + "...[已截断]"
        return True, text or "(工具未返回文本内容)"
    return False, str(outcome.get("error", "MCP 调用失败"))


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


def _schedule_entry_for_preview(db: Session, entry_id: int | None):
    if entry_id is None:
        return None
    return db.get(TaskScheduleEntry, entry_id)


def _normalize_schedule_assignments(payload: dict) -> list[dict]:
    raw = payload.get("assignments", [])
    if not isinstance(raw, list):
        return []
    assignments = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        task_id = _coerce_int(item.get("task_id"))
        date_value = item.get("date")
        try:
            schedule_date = datetime.fromisoformat(str(date_value)).date()
        except (TypeError, ValueError):
            continue
        if task_id is None:
            continue
        key = (task_id, schedule_date)
        if key in seen:
            continue
        seen.add(key)
        assignments.append(
            {
                "task_id": task_id,
                "date": schedule_date,
                "note": str(item.get("note") or "").strip(),
                "start_time": item.get("start_time"),
                "end_time": item.get("end_time"),
            }
        )
    return assignments


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
