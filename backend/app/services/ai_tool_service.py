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
    ai_report_service,
    app_setting_service,
    file_service,
    goal_service,
    habit_service,
    journal_service,
    mcp_service,
    notification_service,
    schedule_service,
    subtask_service,
    task_service,
    timer_service,
)
from app.services.tool_registry import (
    confirm_names as _registry_confirm_names,
    feature_flags as _registry_feature_flags,
    safe_names as _registry_safe_names,
)

# 白名单/确认集/功能开关统一从 tool_registry 派生（单一数据源）；
# execute_tool 的 if 执行体仍按原 name 分派，引用这些集合做门控。
SAFE_TOOLS = _registry_safe_names()
CONFIRMATION_REQUIRED_TOOLS = _registry_confirm_names()
TOOL_FEATURE_FLAGS = _registry_feature_flags()


def execute_tool(db: Session, name: str, args: dict) -> dict:
    # MCP 工具（mcp__ 前缀）：仅服务器开启「只读免确认」且工具带 readOnlyHint 时可直接执行，
    # 其余一律要求走 dangerous_actions 的 mcp_tool_call 两段确认（安全红线 2.6）。
    if name.startswith("mcp__"):
        return _execute_mcp_tool(db, name, args)
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
        if name == "get_time_stats":
            days = min(max(int(args.get("days") or 30), 1), 90)
            stats = timer_service.time_stats(db, days)
            for item in stats["daily"]:
                item["date"] = item["date"].isoformat()
            return {"ok": True, "stats": stats}
        # ---- 阶段 B5：补齐 safe 工具缺口 ----
        if name == "toggle_subtask":
            task_id = int(args["task_id"])
            subtask_id = int(args["subtask_id"])
            task = task_service.get_task(db, task_id)
            if task is None:
                return {"ok": False, "error": "任务不存在"}
            sub = next((s for s in task.subtasks if s.id == subtask_id), None)
            if sub is None:
                return {"ok": False, "error": "子任务不存在"}
            # 复用 update_subtask 翻转 done（与现有 subtask_service 口径一致）
            from app.schemas import SubtaskUpdate
            new_done = not bool(getattr(sub, "done", False))
            subtask_service.update_subtask(db, task_id, subtask_id, SubtaskUpdate(done=new_done))
            return {"ok": True, "subtask_id": subtask_id, "done": new_done}
        if name == "restore_from_trash":
            item_type = str(args.get("item_type", ""))
            item_id = int(args["item_id"])
            if item_type == "task":
                restored = task_service.restore_task(db, item_id)
                return ({"ok": True, "task": _task_dict(restored)} if restored
                        else {"ok": False, "error": "任务不存在或不在回收站"})
            if item_type == "file":
                restored = file_service.restore_file(db, item_id)
                return ({"ok": True, "file": _file_dict(restored)} if restored
                        else {"ok": False, "error": "资料不存在或不在回收站"})
            return {"ok": False, "error": "item_type 必须是 task 或 file"}
        if name == "mark_notifications_read":
            nid = args.get("notification_id")
            if nid is not None:
                updated = notification_service.mark_read(db, int(nid))
                return ({"ok": True, "notification_id": int(nid)} if updated
                        else {"ok": False, "error": "通知不存在"})
            count = notification_service.mark_all_read(db)
            return {"ok": True, "marked_count": count}
        if name == "get_settings":
            return {"ok": True, "settings": app_setting_service.list_settings(db)}
        if name == "generate_report":
            # 报告生成需 AI config（异步），此处同步收集报告数据供 agent 总结，
            # 避免在同步 execute_tool 中触发异步 provider 调用。
            kind = str(args.get("kind", "daily"))
            report_type = "weekly" if kind == "weekly" else "daily"
            from datetime import date as _date
            target = None
            if args.get("date"):
                target = _date.fromisoformat(str(args["date"]))
            data = ai_report_service.collect_report_data(db, report_type, target, task_limit=50)
            return {"ok": True, "kind": report_type, "report_data": data}
        # 阶段 C1/C2：plan 模式收尾 + 工作清单（不操作业务数据，结果由 agent 循环捕获）
        if name == "propose_plan":
            # 计划卡片：原样回传，由 _dispatch_native_tool_call / 循环写入消息 meta
            return {"ok": True, "plan_card": {
                "title": str(args.get("title", "")),
                "steps": args.get("steps") or [],
                "affected_days": args.get("affected_days") or [],
                "status": "pending",
            }}
        if name == "update_work_plan":
            # 工作清单：原样回传，由流式循环作为 work_plan 事件推送 + 落库 meta
            items = args.get("items") or []
            return {"ok": True, "work_plan": items}
    except (ValidationError, KeyError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": "未处理的工具"}


def _execute_mcp_tool(db: Session, name: str, args: dict) -> dict:
    """MCP 工具直接执行闸门：仅「只读免确认」服务器上的只读工具可直接调用。

    其余一律拒绝直接执行，要求模型改走 dangerous_actions 的 mcp_tool_call 两段确认，
    以落实安全红线（MCP 工具默认经确认管道执行）。
    """
    parsed = mcp_service.parse_namespaced(name)
    if parsed is None:
        return {"ok": False, "error": f"MCP 工具名格式无效: {name}"}
    server_id, fallback_name = parsed
    # is_auto_approved 按 namespaced 形态匹配（兼容截断名）；call_tool 需原始名
    if not mcp_service.is_auto_approved(db, server_id, name):
        return {
            "ok": False,
            "error": (
                f"MCP 工具 {name} 需要用户确认。请改放入 dangerous_actions："
                f'{{"action_type":"mcp_tool_call","payload":{{"server_id":{server_id},'
                f'"tool_name":"{mcp_service.resolve_tool_name(db, server_id, name) or fallback_name}",'
                f'"arguments":<参数>}},"summary":"<说明>"}}'
            ),
        }
    original = mcp_service.resolve_tool_name(db, server_id, name) or fallback_name
    outcome = mcp_service.call_tool(db, server_id, original, args)
    if outcome.get("ok"):
        return {"ok": True, "text": str(outcome.get("text", ""))}
    return {"ok": False, "error": str(outcome.get("error", "MCP 调用失败"))}


def _create_task_with_optional_files(db: Session, args: dict) -> dict:
    task_args = dict(args)
    file_ids = _pop_file_ids(task_args)
    attachment_ids = _pop_attachment_ids(task_args)
    subtask_items = _pop_subtask_titles(task_args)
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
    for sub in subtask_items:
        subtask_service.create_subtask(
            db, task.id, SubtaskCreate(title=sub["title"], estimated_minutes=sub.get("estimated_minutes"))
        )
    task = task_service.get_task(db, task.id) or task
    return {"ok": True, "task": _task_dict(task)}


def _create_subtasks(db: Session, task_id: int, items: list[dict]) -> dict:
    if not items:
        return {"ok": False, "error": "创建子任务需要 titles 或 subtasks"}
    created = []
    for item in items:
        subtask = subtask_service.create_subtask(
            db,
            task_id,
            SubtaskCreate(title=item["title"], estimated_minutes=item.get("estimated_minutes")),
        )
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
    start_time = args.get("start_time")
    end_time = args.get("end_time")
    try:
        entry = schedule_service.create_schedule_entry(
            db,
            ScheduleEntryCreate(
                task_id=task_id,
                date=target_date,
                source="ai",
                note=note,
                start_time=start_time,
                end_time=end_time,
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


def _pop_subtask_titles(args: dict) -> list[dict]:
    """提取子任务列表为 [{title, estimated_minutes}]；支持纯字符串或对象项。

    去重（按 title）；estimated_minutes 仅在对象项中给出时保留。
    """
    raw = args.pop("titles", args.pop("subtask_titles", args.pop("subtasks", [])))
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError("子任务必须是字符串或数组")
    items: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, dict):
            title = str(item.get("title", "")).strip()
            estimated = item.get("estimated_minutes")
        else:
            title = str(item).strip()
            estimated = None
        if title and title not in seen:
            seen.add(title)
            entry = {"title": title}
            if isinstance(estimated, (int, float)) and estimated >= 0:
                entry["estimated_minutes"] = int(estimated)
            items.append(entry)
    return items


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
        "estimated_minutes": task.estimated_minutes,
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
        "estimated_minutes": subtask.estimated_minutes,
        "completed_at": subtask.completed_at.isoformat() if subtask.completed_at else None,
    }
