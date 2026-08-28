"""内置工具注册表（单一数据源）。

原生 function-calling 的工具清单、白名单/确认集、功能开关门控、危险动作映射
统一从这里派生。MCP 工具不在本表内（由 mcp_service 单独装配，schema 同构）。

设计要点：
- BUILTIN_TOOLS 是静态数据（不含 db），feature flag 过滤在 all_tool_defs/provider_tools 里做。
- safety="confirm" 的工具名 == ai_action_service 的 action_type（恒等映射，无翻译层）。
- attach_file_to_task 同时是 safe 工具与历史 action_type 通道：这里只进 safe 集，
  不重复进 confirm 集；ai_action_service.SUPPORTED_ACTION_TYPES 保留同名历史通道不动。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    input_schema: dict[str, Any]
    safety: str  # "safe" | "confirm"
    feature_flag: str | None = None
    confirm_action_type: str | None = None  # safety="confirm" 时必填，= 现有 action_type
    # 阶段 B4 / C1：是否只读（不写业务数据）。用于并行执行（只读可并发，各自独立 session）
    # 与 plan 模式工具过滤（plan 模式只暴露只读 + propose_plan）。默认 False。
    readonly: bool = False


# region ---- 共用 schema 片段 ----

_PRIORITY_ENUM = {"高", "中", "低"}
_STATUS_ENUM = {"待办", "进行中", "完成"}
_RECUR_ENUM = {"none", "daily", "weekdays", "weekly", "monthly"}
_KR_KIND_ENUM = {"manual", "tag_task_count", "habit_checkins"}
_RESOURCE_TYPE_ENUM = {"video", "webpage", "article", "paper", "course", "link"}

# 任务可写字段（create_task / create_reminder 共用；不含内部 sort_order）
_TASK_WRITABLE_PROPS: dict[str, dict[str, Any]] = {
    "title": {"type": "string", "minLength": 1, "maxLength": 200, "description": "任务标题"},
    "notes": {"type": "string", "description": "任务备注（Markdown）"},
    "due_date": {
        "type": "string",
        "format": "date-time",
        "description": "截止/提醒时间，ISO 8601 如 2026-07-04T09:00:00",
    },
    "priority": {"type": "string", "enum": sorted(_PRIORITY_ENUM), "description": "优先级"},
    "status": {"type": "string", "enum": sorted(_STATUS_ENUM), "description": "状态"},
    "progress": {"type": "integer", "minimum": 0, "maximum": 100, "description": "进度百分比 0-100"},
    "start_date": {"type": "string", "format": "date-time", "description": "开始时间 ISO 8601"},
    "end_date": {"type": "string", "format": "date-time", "description": "结束时间 ISO 8601"},
    "tags": {
        "type": "array",
        "items": {"type": "string"},
        "description": "标签名数组，后端按名字 get-or-create",
    },
    "due_time": {
        "type": "string",
        "pattern": r"^([01]\d|2[0-3]):[0-5]\d$",
        "description": "截止时刻 HH:MM，需配合 due_date",
    },
    "remind_offsets": {
        "type": "array",
        "items": {"type": "integer"},
        "description": "提前提醒分钟数组，如 [0,30,1440] 表示截止时/提前30分/提前1天",
    },
    "recur_rule": {
        "type": "string",
        "enum": sorted(_RECUR_ENUM),
        "description": "重复规则：none/daily/weekdays/weekly/monthly",
    },
    "recur_interval": {"type": "integer", "minimum": 1, "maximum": 99, "description": "重复间隔数（默认 1）"},
    "estimated_minutes": {"type": "integer", "minimum": 0, "description": "预估耗时（分钟）"},
}

# 任务更新补丁（update_task / bulk_update_tasks 的 patch 字段，全部可选）
_TASK_PATCH_PROPS: dict[str, dict[str, Any]] = {
    key: {**value, **({"description": value["description"] + "（可选）"} if "description" in value else {})}
    for key, value in _TASK_WRITABLE_PROPS.items()
}


def _task_create_schema(*, require_due_date: bool) -> dict[str, Any]:
    props = dict(_TASK_WRITABLE_PROPS)
    props["file_ids"] = {
        "type": "array",
        "items": {"type": "integer"},
        "description": "已有资料 ID 数组，后端自动关联到新任务",
    }
    props["attachment_ids"] = {
        "type": "array",
        "items": {"type": "string"},
        "description": "对话附件 ID 数组，后端自动保存到资料库并关联",
    }
    props["subtask_titles"] = {
        "type": "array",
        "items": {"type": "string"},
        "description": "子任务标题数组，创建任务时一并建子任务",
    }
    required = ["title"] + (["due_date"] if require_due_date else [])
    return {
        "type": "object",
        "properties": props,
        "required": required,
    }


def _task_patch_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": dict(_TASK_PATCH_PROPS),
        "description": "要更新的任务字段，只传需要改的字段",
    }


def _schedule_assignments_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "assignments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "integer", "description": "任务 ID"},
                        "date": {"type": "string", "format": "date", "description": "目标日期 ISO 日期"},
                        "note": {"type": "string", "description": "安排备注（可选）"},
                        "start_time": {"type": "string", "description": "可选，开始时刻 HH:MM"},
                        "end_time": {"type": "string", "description": "可选，结束时刻 HH:MM"},
                    },
                    "required": ["task_id", "date"],
                },
                "description": "安排项数组",
            },
        },
        "required": ["assignments"],
    }


# endregion


# region ---- 内置工具定义 ----

BUILTIN_TOOLS: list[ToolDef] = [
    # ---- 查询类（safe）----
    ToolDef(
        name="list_tasks",
        description="列出当前所有未删除任务（含状态、优先级、进度、标签、子任务）。",
        input_schema={"type": "object", "properties": {}},
        safety="safe",
        readonly=True,
    ),
    ToolDef(
        name="list_reminders",
        description="列出所有带截止时间的任务（提醒）。",
        input_schema={"type": "object", "properties": {}},
        safety="safe",
        readonly=True,
    ),
    ToolDef(
        name="list_files",
        description="列出资料库中的资料，可按关键词 q 模糊搜索。",
        input_schema={
            "type": "object",
            "properties": {"q": {"type": "string", "description": "搜索关键词（可选）"}},
        },
        safety="safe",
        readonly=True,
    ),
    ToolDef(
        name="list_subtasks",
        description="查看指定任务的子任务列表。",
        input_schema={
            "type": "object",
            "properties": {"task_id": {"type": "integer", "description": "任务 ID"}},
            "required": ["task_id"],
        },
        safety="safe",
        readonly=True,
    ),
    ToolDef(
        name="list_day_schedule",
        description="查看某天的日程安排与压力摘要。",
        input_schema={
            "type": "object",
            "properties": {"date": {"type": "string", "format": "date", "description": "ISO 日期如 2026-07-22"}},
            "required": ["date"],
        },
        safety="safe",
        readonly=True,
    ),
    ToolDef(
        name="list_month_schedule",
        description="查看某年某月的整月日程压力分布。",
        input_schema={
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "年，如 2026"},
                "month": {"type": "integer", "minimum": 1, "maximum": 12, "description": "月 1-12"},
            },
            "required": ["year", "month"],
        },
        safety="safe",
        readonly=True,
    ),
    ToolDef(
        name="get_time_stats",
        description="查询最近 N 天的专注时间统计：每日投入分钟、任务排行、标签分布、预估 vs 实际。做复盘或排程建议前使用。",
        input_schema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "统计天数，默认 30，最大 90"},
            },
        },
        safety="safe",
        feature_flag="feature_timer_enabled",
        readonly=True,
    ),
    ToolDef(
        name="list_habits",
        description="列出所有习惯及其今日/本周打卡状态与连续纪录。",
        input_schema={"type": "object", "properties": {}},
        safety="safe",
        readonly=True,
        feature_flag="feature_habits_enabled",
    ),
    ToolDef(
        name="list_journal_entries",
        description="查看最近的日记条目（日期、预览、心情）。",
        input_schema={
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "description": "返回条数（可选，默认 10）"}},
        },
        safety="safe",
        readonly=True,
        feature_flag="feature_journal_enabled",
    ),
    ToolDef(
        name="list_goals",
        description="列出进行中的目标(OKR)及其关键结果与进度。",
        input_schema={"type": "object", "properties": {}},
        safety="safe",
        readonly=True,
        feature_flag="feature_goals_enabled",
    ),
    # ---- 创建类（safe）----
    ToolDef(
        name="create_task",
        description="创建一个新任务，可带标签、提醒、重复规则、关联资料、子任务。",
        input_schema=_task_create_schema(require_due_date=False),
        safety="safe",
    ),
    ToolDef(
        name="create_reminder",
        description="创建一个带截止时间的提醒任务（自动加「提醒」标签），需提供 due_date。",
        input_schema=_task_create_schema(require_due_date=True),
        safety="safe",
    ),
    ToolDef(
        name="create_note_file",
        description="把一段文本保存为资料库中的笔记文件（.txt）。",
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "笔记标题（默认「AI 资料笔记」）"},
                "content": {"type": "string", "description": "笔记正文"},
                "notes": {"type": "string", "description": "资料备注（可选）"},
            },
        },
        safety="safe",
    ),
    ToolDef(
        name="create_subtask",
        description="为已有任务添加单个子任务。",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "所属任务 ID"},
                "title": {"type": "string", "minLength": 1, "description": "子任务标题"},
            },
            "required": ["task_id", "title"],
        },
        safety="safe",
    ),
    ToolDef(
        name="create_subtasks",
        description="为已有任务批量添加多个子任务。",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "所属任务 ID"},
                "titles": {
                    "type": "array",
                    "items": {
                        "anyOf": [
                            {"type": "string"},
                            {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "estimated_minutes": {"type": "integer"},
                                },
                                "required": ["title"],
                            },
                        ]
                    },
                    "description": "子任务数组：纯标题字符串，或 {title, estimated_minutes} 对象",
                },
            },
            "required": ["task_id", "titles"],
        },
        safety="safe",
    ),
    ToolDef(
        name="create_habit",
        description="新建一个习惯（每日/每周打卡目标）。",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "习惯名称"},
                "notes": {"type": "string", "description": "备注（可选）"},
                "period": {"type": "string", "enum": ["daily", "weekly"], "description": "周期"},
                "target_count": {"type": "integer", "minimum": 1, "description": "周期内目标次数"},
            },
        },
        safety="safe",
        feature_flag="feature_habits_enabled",
    ),
    ToolDef(
        name="create_goal",
        description="新建一个目标(OKR)，可带关键结果数组。",
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "目标标题"},
                "notes": {"type": "string", "description": "目标备注（可选）"},
                "start_date": {"type": "string", "format": "date", "description": "开始日期（可选）"},
                "end_date": {"type": "string", "format": "date", "description": "结束日期（可选）"},
                "key_results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "关键结果标题"},
                            "kind": {
                                "type": "string",
                                "enum": sorted(_KR_KIND_ENUM),
                                "description": "manual=手动更新；tag_task_count=按标签任务数；habit_checkins=按习惯打卡",
                            },
                            "target_value": {"type": "number", "exclusiveMinimum": 0, "description": "目标值"},
                            "unit": {"type": "string", "description": "单位"},
                            "link": {"type": "object", "description": "自动类 KR 的关联配置"},
                        },
                        "required": ["title"],
                    },
                    "description": "关键结果数组",
                },
            },
        },
        safety="safe",
        feature_flag="feature_goals_enabled",
    ),
    ToolDef(
        name="write_journal",
        description="写/更新一篇日记（按日期 upsert），可记录心情。",
        input_schema={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "日记正文（Markdown）"},
                "date": {"type": "string", "format": "date", "description": "日期（可选，默认今天）"},
                "mood": {"type": "string", "description": "心情标签（可选）"},
            },
            "required": ["content"],
        },
        safety="safe",
        feature_flag="feature_journal_enabled",
    ),
    # ---- 关联/操作类（safe）----
    ToolDef(
        name="attach_file_to_task",
        description="把资料库中的资料关联到指定任务。",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "任务 ID"},
                "file_id": {"type": "integer", "description": "资料 ID"},
            },
            "required": ["task_id", "file_id"],
        },
        safety="safe",
    ),
    ToolDef(
        name="save_attachment_to_library",
        description="把对话附件保存到资料库，可选关联到任务。",
        input_schema={
            "type": "object",
            "properties": {
                "attachment_id": {"type": "string", "description": "对话附件 ID"},
                "notes": {"type": "string", "description": "资料备注（可选）"},
                "task_id": {"type": "integer", "description": "关联任务 ID（可选）"},
            },
            "required": ["attachment_id"],
        },
        safety="safe",
    ),
    ToolDef(
        name="assign_task_to_day",
        description="把单个任务安排到某天，写入日程（source=ai）。",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "任务 ID"},
                "date": {"type": "string", "format": "date", "description": "目标日期 ISO 日期"},
                "note": {"type": "string", "description": "安排备注（可选）"},
                "start_time": {"type": "string", "description": "可选，开始时刻 HH:MM"},
                "end_time": {"type": "string", "description": "可选，结束时刻 HH:MM"},
            },
            "required": ["task_id", "date"],
        },
        safety="safe",
    ),
    ToolDef(
        name="check_in_habit",
        description="为习惯打卡（默认今天，可指定日期）。",
        input_schema={
            "type": "object",
            "properties": {
                "habit_id": {"type": "integer", "description": "习惯 ID"},
                "date": {"type": "string", "format": "date", "description": "打卡日期（可选，默认今天）"},
            },
            "required": ["habit_id"],
        },
        safety="safe",
        feature_flag="feature_habits_enabled",
    ),
    ToolDef(
        name="update_kr_progress",
        description="更新手动类关键结果的当前值进度。",
        input_schema={
            "type": "object",
            "properties": {
                "kr_id": {"type": "integer", "description": "关键结果 ID"},
                "current_value": {"type": "number", "description": "当前值"},
            },
            "required": ["kr_id", "current_value"],
        },
        safety="safe",
        feature_flag="feature_goals_enabled",
    ),
    ToolDef(
        name="start_timer",
        description="为任务开始专注/番茄钟计时。",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "任务 ID"},
                "kind": {"type": "string", "enum": ["pomodoro", "stopwatch"], "description": "计时类型（默认 pomodoro）"},
            },
            "required": ["task_id"],
        },
        safety="safe",
        feature_flag="feature_timer_enabled",
    ),
    ToolDef(
        name="stop_timer",
        description="停止当前运行中的计时。",
        input_schema={"type": "object", "properties": {}},
        safety="safe",
        feature_flag="feature_timer_enabled",
    ),
    # ---- 确认类（confirm，工具名 = action_type）----
    ToolDef(
        name="update_task",
        description="修改既有任务的字段。修改类操作需用户确认后才生效。",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "任务 ID"},
                "patch": _task_patch_schema(),
            },
            "required": ["task_id", "patch"],
        },
        safety="confirm",
        confirm_action_type="update_task",
    ),
    ToolDef(
        name="update_file_notes",
        description="修改资料备注。需用户确认后才生效。",
        input_schema={
            "type": "object",
            "properties": {
                "file_id": {"type": "integer", "description": "资料 ID"},
                "notes": {"type": "string", "description": "新的资料备注"},
            },
            "required": ["file_id", "notes"],
        },
        safety="confirm",
        confirm_action_type="update_file_notes",
    ),
    ToolDef(
        name="detach_file_from_task",
        description="取消资料与任务的关联。需用户确认后才生效。",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "任务 ID"},
                "file_id": {"type": "integer", "description": "资料 ID"},
            },
            "required": ["task_id", "file_id"],
        },
        safety="confirm",
        confirm_action_type="detach_file_from_task",
    ),
    ToolDef(
        name="delete_task",
        description="把任务移入回收站。需用户确认后才生效。",
        input_schema={
            "type": "object",
            "properties": {"task_id": {"type": "integer", "description": "任务 ID"}},
            "required": ["task_id"],
        },
        safety="confirm",
        confirm_action_type="delete_task",
    ),
    ToolDef(
        name="delete_file",
        description="把资料移入回收站。需用户确认后才生效。",
        input_schema={
            "type": "object",
            "properties": {"file_id": {"type": "integer", "description": "资料 ID"}},
            "required": ["file_id"],
        },
        safety="confirm",
        confirm_action_type="delete_file",
    ),
    ToolDef(
        name="bulk_update_tasks",
        description="批量修改多个任务的字段。需用户确认后才生效。",
        input_schema={
            "type": "object",
            "properties": {
                "task_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "任务 ID 数组",
                },
                "patch": _task_patch_schema(),
            },
            "required": ["task_ids", "patch"],
        },
        safety="confirm",
        confirm_action_type="bulk_update_tasks",
    ),
    ToolDef(
        name="bulk_delete_tasks",
        description="批量把多个任务移入回收站。需用户确认后才生效。",
        input_schema={
            "type": "object",
            "properties": {
                "task_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "任务 ID 数组",
                },
            },
            "required": ["task_ids"],
        },
        safety="confirm",
        confirm_action_type="bulk_delete_tasks",
    ),
    ToolDef(
        name="bulk_delete_files",
        description="批量把多个资料移入回收站。需用户确认后才生效。",
        input_schema={
            "type": "object",
            "properties": {
                "file_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "资料 ID 数组",
                },
            },
            "required": ["file_ids"],
        },
        safety="confirm",
        confirm_action_type="bulk_delete_files",
    ),
    ToolDef(
        name="empty_trash",
        description="清空回收站，彻底删除其中所有任务和资料，不可恢复。需用户确认后才生效。",
        input_schema={"type": "object", "properties": {}},
        safety="confirm",
        confirm_action_type="empty_trash",
    ),
    ToolDef(
        name="import_web_resources",
        description="把联网搜索到的外部资料作为链接资料导入资料库。需用户确认后才生效。",
        input_schema={
            "type": "object",
            "properties": {
                "resources": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "资料标题"},
                            "url": {"type": "string", "format": "uri", "description": "资料链接"},
                            "resource_type": {
                                "type": "string",
                                "enum": sorted(_RESOURCE_TYPE_ENUM),
                                "description": "资料类型",
                            },
                            "notes": {"type": "string", "description": "为什么有用（可选）"},
                            "task_id": {"type": "integer", "description": "关联任务 ID（可选）"},
                        },
                        "required": ["title", "url"],
                    },
                    "description": "要导入的资源数组",
                },
                "task_id": {"type": "integer", "description": "统一关联的任务 ID（可选）"},
            },
            "required": ["resources"],
        },
        safety="confirm",
        confirm_action_type="import_web_resources",
    ),
    ToolDef(
        name="update_schedule_entry",
        description="修改日程条目的日期或备注。需用户确认后才生效。",
        input_schema={
            "type": "object",
            "properties": {
                "entry_id": {"type": "integer", "description": "日程条目 ID"},
                "patch": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "format": "date", "description": "新日期"},
                        "note": {"type": "string", "description": "新备注"},
                    },
                    "description": "要更新的字段",
                },
            },
            "required": ["entry_id", "patch"],
        },
        safety="confirm",
        confirm_action_type="update_schedule_entry",
    ),
    ToolDef(
        name="delete_schedule_entry",
        description="删除日程条目（取消该任务的当天安排）。需用户确认后才生效。",
        input_schema={
            "type": "object",
            "properties": {"entry_id": {"type": "integer", "description": "日程条目 ID"}},
            "required": ["entry_id"],
        },
        safety="confirm",
        confirm_action_type="delete_schedule_entry",
    ),
    ToolDef(
        name="bulk_assign_tasks_to_days",
        description="批量把多个任务安排到指定日期。需用户确认后才生效。",
        input_schema=_schedule_assignments_schema(),
        safety="confirm",
        confirm_action_type="bulk_assign_tasks_to_days",
    ),
    ToolDef(
        name="auto_plan_tasks",
        description="按自动排程结果批量安排任务到日期。需用户确认后才生效。",
        input_schema=_schedule_assignments_schema(),
        safety="confirm",
        confirm_action_type="auto_plan_tasks",
    ),
    # ---- skill / MCP 自助配置（confirm）----
    ToolDef(
        name="create_skill",
        description="根据用户提供的文档或信息整理成一条助手 skill（工作规则），确认后创建。会注入后续对话。",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "skill 名称"},
                "description": {"type": "string", "description": "一句话说明（可选）"},
                "content": {"type": "string", "description": "skill 正文（工作规则，Markdown）"},
                "enabled": {"type": "boolean", "description": "是否同时启用（可选，默认否）"},
            },
            "required": ["name", "content"],
        },
        safety="confirm",
        confirm_action_type="create_skill",
    ),
    ToolDef(
        name="create_mcp_server",
        description="根据用户提供的信息配置一个 MCP 工具服务器（stdio 本地命令或 http 远程），确认后创建。stdio 可执行本地命令，属高敏感操作。",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "服务器名称"},
                "transport": {"type": "string", "enum": ["stdio", "http"], "description": "传输类型"},
                "command": {"type": "string", "description": "stdio：可执行命令，如 npx/uvx/python"},
                "args": {"type": "array", "items": {"type": "string"}, "description": "stdio：参数数组"},
                "env": {
                    "type": "object",
                    "description": "stdio：环境变量（键值对，值加密保存）",
                    "additionalProperties": {"type": "string"},
                },
                "url": {"type": "string", "description": "http：服务器地址，仅 http(s)://"},
                "headers": {
                    "type": "object",
                    "description": "http：请求头（键值对，值加密保存）",
                    "additionalProperties": {"type": "string"},
                },
                "timeout_sec": {"type": "integer", "minimum": 5, "maximum": 120, "description": "超时秒数（默认 30）"},
                "auto_approve_readonly": {"type": "boolean", "description": "只读工具免确认（默认 false）"},
                "enabled": {"type": "boolean", "description": "是否启用（默认 true）"},
            },
            "required": ["name", "transport"],
        },
        safety="confirm",
        confirm_action_type="create_mcp_server",
    ),
    # ---- 阶段 B5：工具覆盖度补齐（agent 能力面 ≥ UI 能力面） ----
    # 习惯 update/delete（confirm：改习惯会影响 KR 关联进度）
    ToolDef(
        name="update_habit",
        description="修改既有习惯的名称/目标次数/周期等。注意：改目标次数会影响关联 KR 的进度统计，需用户确认后生效。",
        input_schema={
            "type": "object",
            "properties": {
                "habit_id": {"type": "integer", "description": "习惯 ID"},
                "patch": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "minLength": 1, "maxLength": 100, "description": "习惯名称"},
                        "notes": {"type": "string", "description": "备注"},
                        "period": {"type": "string", "enum": ["daily", "weekly"], "description": "周期"},
                        "target_count": {"type": "integer", "minimum": 1, "maximum": 99, "description": "周期内目标次数"},
                        "color": {"type": "string", "description": "颜色标识"},
                    },
                    "description": "要修改的字段（全部可选，只传需要改的）",
                },
            },
            "required": ["habit_id", "patch"],
        },
        safety="confirm",
        confirm_action_type="update_habit",
        feature_flag="feature_habits_enabled",
    ),
    ToolDef(
        name="delete_habit",
        description="删除一个习惯（软删除，移入回收站）。注意：关联该习惯的 KR（habit_checkins 类）将不再自动累计进度，需用户确认后生效。",
        input_schema={
            "type": "object",
            "properties": {"habit_id": {"type": "integer", "description": "习惯 ID"}},
            "required": ["habit_id"],
        },
        safety="confirm",
        confirm_action_type="delete_habit",
        feature_flag="feature_habits_enabled",
    ),
    # 目标 update/delete（confirm）
    ToolDef(
        name="update_goal",
        description="修改既有目标或其关键结果文本。需用户确认后生效。",
        input_schema={
            "type": "object",
            "properties": {
                "goal_id": {"type": "integer", "description": "目标 ID"},
                "patch": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "minLength": 1, "description": "目标标题"},
                        "notes": {"type": "string", "description": "目标备注"},
                        "start_date": {"type": "string", "format": "date", "description": "开始日期"},
                        "end_date": {"type": "string", "format": "date", "description": "结束日期"},
                    },
                    "description": "要修改的字段（全部可选）",
                },
            },
            "required": ["goal_id", "patch"],
        },
        safety="confirm",
        confirm_action_type="update_goal",
        feature_flag="feature_goals_enabled",
    ),
    ToolDef(
        name="delete_goal",
        description="删除一个目标及其关键结果（软删除，移入回收站）。需用户确认后生效。",
        input_schema={
            "type": "object",
            "properties": {"goal_id": {"type": "integer", "description": "目标 ID"}},
            "required": ["goal_id"],
        },
        safety="confirm",
        confirm_action_type="delete_goal",
        feature_flag="feature_goals_enabled",
    ),
    # 提醒 update/delete（confirm；提醒本质是带 due_date 的任务，复用任务改/删）
    ToolDef(
        name="update_reminder",
        description="修改既有提醒的时刻或字段（提醒=带截止时间的任务）。需用户确认后生效。",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "提醒对应的任务 ID"},
                "patch": _task_patch_schema(),
            },
            "required": ["task_id", "patch"],
        },
        safety="confirm",
        confirm_action_type="update_reminder",
    ),
    ToolDef(
        name="delete_reminder",
        description="删除一个提醒（把对应任务移入回收站）。需用户确认后生效。",
        input_schema={
            "type": "object",
            "properties": {"task_id": {"type": "integer", "description": "提醒对应的任务 ID"}},
            "required": ["task_id"],
        },
        safety="confirm",
        confirm_action_type="delete_reminder",
    ),
    # 子任务 toggle/update/delete（toggle=safe，update/delete=confirm）
    ToolDef(
        name="toggle_subtask",
        description="勾选/取消勾选一个子任务（切换完成状态）。",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "父任务 ID"},
                "subtask_id": {"type": "integer", "description": "子任务 ID"},
            },
            "required": ["task_id", "subtask_id"],
        },
        safety="safe",
    ),
    ToolDef(
        name="update_subtask",
        description="修改子任务标题或完成状态。需用户确认后生效。",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "父任务 ID"},
                "subtask_id": {"type": "integer", "description": "子任务 ID"},
                "patch": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "minLength": 1, "description": "子任务标题"},
                        "done": {"type": "boolean", "description": "是否完成"},
                    },
                    "description": "要修改的字段（全部可选）",
                },
            },
            "required": ["task_id", "subtask_id", "patch"],
        },
        safety="confirm",
        confirm_action_type="update_subtask",
    ),
    ToolDef(
        name="delete_subtask",
        description="删除一个子任务。需用户确认后生效。",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "父任务 ID"},
                "subtask_id": {"type": "integer", "description": "子任务 ID"},
            },
            "required": ["task_id", "subtask_id"],
        },
        safety="confirm",
        confirm_action_type="delete_subtask",
    ),
    # 回收站恢复（safe；只读性质的反向操作，不破坏数据）
    ToolDef(
        name="restore_from_trash",
        description="从回收站恢复一个任务或资料（撤销软删除）。",
        input_schema={
            "type": "object",
            "properties": {
                "item_type": {"type": "string", "enum": ["task", "file"], "description": "恢复对象类型"},
                "item_id": {"type": "integer", "description": "任务或资料 ID"},
            },
            "required": ["item_type", "item_id"],
        },
        safety="safe",
    ),
    # 通知已读（safe）
    ToolDef(
        name="mark_notifications_read",
        description="把通知标记为已读：传 notification_id 标记单条；不传则标记全部已读。",
        input_schema={
            "type": "object",
            "properties": {
                "notification_id": {"type": "integer", "description": "单条通知 ID（可选；不传=全部已读）"},
            },
        },
        safety="safe",
    ),
    # 设置读/改（get=safe，update=confirm；改设置影响应用行为）
    ToolDef(
        name="get_settings",
        description="读取当前应用设置（功能开关、提醒、外观等偏好）。只读，不修改任何数据。",
        input_schema={"type": "object", "properties": {}},
        safety="safe",
        readonly=True,
    ),
    ToolDef(
        name="update_setting",
        description="修改单个应用设置项（如功能开关、提醒偏好）。需用户确认后生效。",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "设置项键名，如 feature_habits_enabled / theme"},
                "value": {"type": "string", "description": "设置项新值"},
            },
            "required": ["key", "value"],
        },
        safety="confirm",
        confirm_action_type="update_setting",
    ),
    # 报告生成（safe；触发一次性生成，不直接改业务数据）
    ToolDef(
        name="generate_report",
        description="生成日报或周报（调用 AI 报告服务，基于任务/专注/习惯数据汇总）。返回报告摘要。",
        input_schema={
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["daily", "weekly"], "description": "日报或周报"},
                "date": {"type": "string", "format": "date", "description": "基准日期（可选，默认今天）"},
            },
            "required": ["kind"],
        },
        safety="safe",
    ),
    # 阶段 C1：plan 模式专属收尾工具——提交结构化计划（不写业务数据，只生成计划卡片）
    ToolDef(
        name="propose_plan",
        description="【计划模式专用】调研完成后提交一份结构化计划供用户审阅。每步注明动作、目标工具、参数预览与理由。",
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "计划标题"},
                "affected_days": {
                    "type": "array",
                    "items": {"type": "string", "format": "date"},
                    "description": "计划影响的日期范围（ISO 日期）",
                },
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "description": "动作描述，如「创建任务」「修改截止日期」"},
                            "tool": {"type": "string", "description": "目标工具名，如 create_task / update_task"},
                            "args_preview": {"type": "string", "description": "参数预览（自然语言摘要）"},
                            "rationale": {"type": "string", "description": "这一步的理由"},
                        },
                        "required": ["action", "tool"],
                    },
                    "description": "计划步骤数组",
                },
            },
            "required": ["title", "steps"],
        },
        safety="safe",
    ),
    # 阶段 C2：工作清单工具——agent 自我跟踪多步任务进度（不操作业务数据）
    ToolDef(
        name="update_work_plan",
        description="更新当前任务的工作清单（TodoList）：3 步以上的任务应先建清单并实时更新进度。不操作业务数据。",
        input_schema={
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "步骤稳定 ID（用于跨轮更新）"},
                            "title": {"type": "string", "description": "步骤标题"},
                            "status": {"type": "string", "enum": ["pending", "in_progress", "done"], "description": "状态"},
                        },
                        "required": ["id", "title", "status"],
                    },
                    "description": "工作清单项数组（全量替换）",
                },
            },
            "required": ["items"],
        },
        safety="safe",
    ),
]

# endregion


# region ---- 查询派生 ----

_BY_NAME: dict[str, ToolDef] = {td.name: td for td in BUILTIN_TOOLS}


def get(name: str) -> ToolDef | None:
    return _BY_NAME.get(name)


def safe_names() -> set[str]:
    return {td.name for td in BUILTIN_TOOLS if td.safety == "safe"}


def confirm_names() -> set[str]:
    return {td.name for td in BUILTIN_TOOLS if td.safety == "confirm"}


def readonly_names() -> set[str]:
    """只读工具集合（不写业务数据）。用于并行执行（只读可并发）与 plan 模式工具过滤。"""
    return {td.name for td in BUILTIN_TOOLS if td.readonly}


def confirm_action_types() -> set[str]:
    """所有 confirm 工具对应的 action_type（== 工具名）。"""
    return {td.confirm_action_type for td in BUILTIN_TOOLS if td.safety == "confirm"}


def feature_flags() -> dict[str, str | None]:
    """工具名 -> 功能开关键（None 表示不受门控）。"""
    return {td.name: td.feature_flag for td in BUILTIN_TOOLS}


def all_tool_defs(db: Session) -> list[ToolDef]:
    """返回功能开关放行的工具定义（功能关闭的工具不暴露给模型）。"""
    from app.services import app_setting_service

    enabled: list[ToolDef] = []
    for td in BUILTIN_TOOLS:
        if td.feature_flag and not app_setting_service.feature_enabled(db, td.feature_flag):
            continue
        enabled.append(td)
    return enabled


def provider_tools(db: Session) -> list[dict[str, Any]]:
    """provider 无关的工具清单：[{"name","description","input_schema"}]。"""
    return [
        {"name": td.name, "description": td.description, "input_schema": td.input_schema}
        for td in all_tool_defs(db)
    ]


# endregion
