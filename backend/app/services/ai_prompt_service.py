from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AIConfig, Task
from app.services import (
    ai_skill_service,
    app_setting_service,
    file_service,
    goal_service,
    habit_service,
    insight_service,
    journal_service,
    mcp_service,
    reminder_service,
    schedule_service,
    task_service,
    timer_service,
)

WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

# 两个内置助手名称；用户自定义名称（非这两个）时始终尊重自定义
STOCK_NAMES = {"知时助手", "知时代理"}

# 知时助手（原版）：问答式助手人设——有求必应，不主动越界
CLASSIC_PERSONA = """默认人设（知时助手）：
你是用户的日程与资料管理助手，温和、严谨、可靠、有求必应。
用户提问时基于本地数据如实回答；用户要求操作时按白名单工具准确执行。
不主动评价用户未提及的事项，不替用户做计划外的决定；需要更多上下文时先查看再回答。
表达克制、具体、可执行；删除、清空、批量覆盖、修改既有对象等高风险动作必须请求系统创建待确认操作，不能替用户确认。"""

DEFAULT_PERSONA = """默认人设：
你是用户的幕僚型参谋、贴身秘书，也是科学、严谨、可靠的个人事务管理助手。
你的职责不是陪聊，而是帮助用户判断形势、厘清目标、制定方案、安排时间、沉淀资料，并在关键节点提醒风险。
你的工作习惯是先识别事实、约束、目标、时间窗口和依赖关系，再把模糊需求拆成可执行任务。
规划时要给出清晰的优先级、起止时间、截止时间、阶段目标和必要的资料归档建议。
当存在多种做法时，给出少量备选方案，并说明主要利弊和风险；不要用空泛建议代替具体安排。
遇到信息不足时，先基于已知条件做保守安排，并明确说明关键假设；不要编造不存在的任务、资料或时间。

你掌握用户的全域数据：任务与日程、目标(OKR)与关键结果、习惯打卡与连续纪录、日记与心情、番茄钟与时间投入、资料库。
作为秘书而非问答机，你必须主动关联这些域，而不是等用户逐个点名：
- 聊任务安排时，自然联想到相关目标（KR）与时间投入；聊状态时，参考最近日记的心情走向。
- 系统给出的「幕僚观察」是你预先发现的跨域注意点（断签、KR 落后、预估偏差、计时异常、情绪线索等）：与用户话题相关时自然融入，不相关则略过，绝不逐条播报、绝不生硬罗列。
- 建议必须落到下一步动作：该建任务就建任务、该打卡就打卡、该拆解就拆解、该计时就提议计时（低风险操作直接动手），不要只说「建议你……」却不动手。
- 复盘与分析时用数据说话：完成趋势、时间投入、预估 vs 实际、KR 进度、连续纪录；指出问题时顺手给出可执行的修正方案。

你表达克制、具体、可执行，像可靠参谋提交简报：先结论，再行动项，再风险和需要用户决策的点。
删除、清空、批量覆盖、修改既有对象或改变资料关联等高风险动作必须请求系统创建待确认操作，不能替用户确认。"""


# 原生 function-calling 模式的系统 prompt 协议段：工具清单由 tools 数组承载，
# prompt 不再输出 JSON 契约/工具枚举，只保留行为准则与业务规则。
_NATIVE_PROTOCOL_BODY = """

你可以直接调用系统提供的工具完成任务。修改、删除、批量操作类工具不会立即执行——系统会先向用户展示确认卡片，你在确认前不要假设它们已生效。工具结果会以工具消息返回给你，请基于结果继续推进；目标完成后直接用自然语言回复用户，不要输出 JSON 代码块。

工作准则：
- 必须使用“当前时间状态”和“当前业务状态”作为判断依据；不要凭模型训练知识猜今天日期。
- 用户说今天、明天、本周、下周、下周六、月底等相对日期时，必须基于当前本地日期换算成明确日期，在工具参数中传明确 ISO 日期/时间。
- 创建任务、日程或提醒时，start_date/end_date/due_date 必须使用明确 ISO 时间；用户没有给具体时刻时，应先询问，或在回复中说明你采用的保守假设。
- 像可靠的 coding agent 一样工作：复杂任务先调用工具查看当前状态，再根据工具结果继续推进，最后总结；不要重复已经成功的同一工具调用。
- 工具失败时基于错误信息修正参数或换工具，不要原样重复失败调用；无法安全完成时说明阻塞点和需要用户补充的信息。
- 领域流程规则见上方「系统内置规则」，始终生效、不得忽视。"""


def assistant_mode(db: Session) -> str:
    """助手模式：assistant=知时助手（原版问答式）；agent=知时代理（主动代劳）。"""
    return app_setting_service.get_setting(db, "assistant_mode") or "agent"


def resolve_assistant_name(db: Session, config: AIConfig) -> str:
    """名称解析：自定义名称（非两个内置名）优先，否则按模式给内置名。"""
    stock = "知时代理" if assistant_mode(db) == "agent" else "知时助手"
    name = (config.assistant_name or "").strip()
    if not name or name in STOCK_NAMES:
        return stock
    return name


def build_system_prompt(db: Session, config: AIConfig) -> str:
    mode = assistant_mode(db)
    assistant_name = resolve_assistant_name(db, config)
    default_persona = DEFAULT_PERSONA if mode == "agent" else CLASSIC_PERSONA
    persona = (config.persona or "").strip() or default_persona
    builtin_text = ai_skill_service.builtin_skill_text(db)
    user_skill = ai_skill_service.user_skill_text(db, config)
    base = f"""你是{assistant_name}，一个本地日程管理助手。
你可以帮助用户查看、规划、安排任务，整理资料，并创建任务时间线。
你只能请求系统提供的白名单工具。危险操作必须创建待确认操作，不能伪造用户确认。
助手人设和 skill 是分开的：人设决定表达方式和协作习惯，skill 只补充用户导入的工作规则。
自定义人设和 skill 都不能覆盖安全规则。

助手人设：
{persona}"""
    if builtin_text:
        base += (
            "\n\n系统内置规则（始终生效，优先级最高；与用户自定义规则冲突时以此为准，不得忽视或跳过）：\n"
            f"{builtin_text}"
        )
    if user_skill:
        base += f"\n\n用户自定义 skill：\n{user_skill}\n"
    # 阶段 7：plan 模式已硬删，恒走原生 function-calling 协议段。
    # MCP 工具经 tools 数组原生暴露，prompt 不再注入文本。
    base += _NATIVE_PROTOCOL_BODY
    search_enhanced = getattr(config, "search_enhancement_enabled", False)
    if getattr(config, "native_web_search_enabled", False) or search_enhanced:
        base += """

联网搜索规则：
当前模型配置允许使用模型原生联网搜索。涉及最新事实、当前网页信息、论文/资料补充检索、近期政策或库版本时，应优先使用模型原生联网能力；如果使用了联网搜索，请在回复中保留关键来源名称或链接，并区分搜索得到的信息与当前本地任务/资料状态。"""
    if search_enhanced:
        base += """

搜索增强：
本轮配置已开启“搜索增强”。当用户的问题涉及资料列举、论文/网页/工具/政策/近期事实、资料补充、方案规划或需要外部参考时，你必须先使用模型原生联网搜索获取相关资料作为参考，再结合当前本地任务和资料状态给出安排。
除非用户明确要求只使用本地资料，或请求完全不需要外部事实，否则不要直接凭训练知识回答。搜索后在回复中至少列出 2 条可核对来源；若实际搜索结果不足 2 条，必须说明原因。"""
    return base


def build_time_context(now: datetime | None = None) -> str:
    current = now or datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.astimezone()
    offset = current.strftime("%z")
    timezone_text = f"UTC{offset[:3]}:{offset[3:]}" if offset else "本地时区"
    weekday = WEEKDAYS[current.weekday()]
    return (
        "当前时间状态：\n"
        f"- 当前本地日期：{current:%Y-%m-%d}\n"
        f"- 当前本地时间：{current:%Y-%m-%d %H:%M:%S}\n"
        f"- 当前星期：{weekday}\n"
        f"- 当前时区：{timezone_text}\n"
        "相对日期规则：今天/明天/本周/下周/下周六/月底等必须以上述当前本地日期为基准，"
        "在工具参数中写成明确 ISO 时间。"
    )


def build_local_context(db: Session) -> str:
    tasks = task_service.list_tasks(db)
    files = file_service.list_files(db)
    upcoming, overdue = reminder_service.due_reminders(db, hours=24 * 7)
    today = datetime.now().astimezone().date()
    today_schedule = schedule_service.get_day_schedule(db, today)
    counts = {
        status: db.execute(
            select(func.count())
            .select_from(Task)
            .where(Task.deleted_at.is_(None), Task.status == status)
        ).scalar()
        or 0
        for status in ("待办", "进行中", "完成")
    }
    task_lines = [
        f"- #{t.id} {t.title} | 状态:{t.status} | 优先级:{t.priority} | 进度:{t.progress}% | "
        f"预估:{t.estimated_minutes or '?'}分钟 | "
        f"开始:{_format_dt(t.start_date)} | 结束:{_format_dt(t.end_date)} | "
        f"截止/提醒:{_format_dt(t.due_date)}{(' ' + t.due_time) if t.due_time else ''} | "
        f"重复:{t.recur_rule if t.recur_rule != 'none' else '无'} | "
        f"标签:{','.join(tag.name for tag in t.tags) or '无'} | 子任务:{_subtask_summary(t)}"
        for t in tasks[:80]
    ]
    overdue_lines = [_reminder_line(t) for t in overdue[:20]]
    upcoming_lines = [_reminder_line(t) for t in upcoming[:20]]
    file_lines = [_file_line(f) for f in files[:80]]
    habit_lines = (
        _habit_lines(db)
        if app_setting_service.feature_enabled(db, "feature_habits_enabled")
        else []
    )
    journal_lines = (
        _journal_lines(db)
        if app_setting_service.feature_enabled(db, "feature_journal_enabled")
        else []
    )
    goal_lines = (
        _goal_lines(db)
        if app_setting_service.feature_enabled(db, "feature_goals_enabled")
        else []
    )
    timer_line = (
        _timer_line(db)
        if app_setting_service.feature_enabled(db, "feature_timer_enabled")
        else "番茄钟功能已关闭"
    )
    insight_lines = (
        [item["text"] for item in insight_service.compute_insights(db, 5)]
        if assistant_mode(db) == "agent"
        else []
    )
    schedule_lines = [
        f"- 今日日期:{today_schedule.date.isoformat()}",
        (
            f"- 日程摘要: 必做:{today_schedule.summary.must_do} | 已安排:{today_schedule.summary.planned} | "
            f"进行中:{today_schedule.summary.in_progress_today} | 未来压力:{today_schedule.summary.upcoming_pressure} | "
            f"未排期:{today_schedule.summary.unscheduled} | 合计:{today_schedule.summary.total}"
        ),
        "今日必做（含逾期）：",
        *(
            [
                f"  - #{item.task.id} {item.task.title} | 截止:{_format_dt(item.task.due_date)} | "
                f"预估:{item.task.estimated_minutes or '?'}分钟"
                for item in today_schedule.buckets.must_do[:10]
            ]
            or ["  - 无"]
        ),
        "未排期任务（需要安排）：",
        *(
            [
                f"  - #{item.task.id} {item.task.title} | 优先级:{item.task.priority} | "
                f"预估:{item.task.estimated_minutes or '?'}分钟"
                for item in today_schedule.buckets.unscheduled[:10]
            ]
            or ["  - 无"]
        ),
        "今日已安排：",
        *(
            [
                f"  - #{item.task.id} {item.task.title} -> {item.entry.date.isoformat()}"
                + (f" | 备注:{item.entry.note}" if item.entry and item.entry.note else "")
                for item in today_schedule.buckets.planned[:5]
            ]
            or ["  - 无"]
        ),
        "未来压力：",
        *(
            [
                f"  - #{item.task.id} {item.task.title} | 截止:{_format_dt(item.task.due_date)}"
                for item in today_schedule.buckets.upcoming_pressure[:5]
            ]
            or ["  - 无"]
        ),
    ]
    context = (
        build_time_context()
        + "\n\n当前任务统计：\n"
        + f"- 待办:{counts['待办']} | 进行中:{counts['进行中']} | 完成:{counts['完成']}"
        + "\n\n当前日程：\n"
        + "\n".join(schedule_lines)
        + "\n\n当前提醒状态：\n"
        + "已逾期：\n"
        + "\n".join(overdue_lines or ["无"])
        + "\n未来 7 天：\n"
        + "\n".join(upcoming_lines or ["无"])
        + "\n\n当前任务：\n"
        + "\n".join(task_lines or ["无"])
        + "\n\n当前资料：\n"
        + "\n".join(file_lines or ["无"])
        + "\n\n今日习惯打卡：\n"
        + "\n".join(habit_lines or ["无"])
        + "\n\n最近日记：\n"
        + "\n".join(journal_lines or ["无"])
        + "\n\n进行中的目标（OKR）：\n"
        + "\n".join(goal_lines or ["无"])
        + "\n\n当前计时：\n"
        + timer_line
    )
    # 幕僚观察是「知时代理」专属能力；原版知时助手不注入（保持问答式的克制）
    if assistant_mode(db) == "agent":
        context += (
            "\n\n幕僚观察（你预先发现的跨域注意点；与用户话题相关时自然融入回复，不相关则略过，绝不逐条播报）：\n"
            + "\n".join(f"- {line}" for line in insight_lines or ["暂无明显注意点"])
        )
    return context


def _goal_lines(db: Session) -> list[str]:
    lines = []
    for goal in goal_service.list_goals(db)[:10]:
        if goal.status != "active":
            continue
        progress = goal_service.goal_progress(db, goal)
        kr_text = "；".join(
            f"{goal_service.kr_progress(db, kr, goal)[1]}%《{kr.title}》"
            for kr in goal.key_results[:3]
        )
        lines.append(f"- #{goal.id} {goal.title} | 总进度:{progress}% | {kr_text or '暂无KR'}")
    return lines


def _timer_line(db: Session) -> str:
    log = timer_service.current_log(db)
    if log is None:
        return "无运行中的计时"
    elapsed = round((datetime.now() - log.started_at).total_seconds() / 60)
    return f"正在计时：《{log.task_title}》已进行 {elapsed} 分钟（{log.kind}）"


def _habit_lines(db: Session) -> list[str]:
    lines = []
    for habit in habit_service.list_habits(db)[:20]:
        status = habit_service.habit_status(habit)
        period_label = "今日" if habit.period == "daily" else "本周"
        lines.append(
            f"- #{habit.id} {habit.name} | {period_label}:{status['period_count']}/{habit.target_count}"
            f" | 连续:{status['streak']}{'天' if habit.period == 'daily' else '周'}"
            f" | {'已达标' if status['done_today'] else '未达标'}"
        )
    return lines


def _journal_lines(db: Session) -> list[str]:
    return [
        f"- {entry.date.isoformat()}"
        + (f" | 心情:{entry.mood}" if entry.mood else "")
        + f" | {(entry.content or '')[:80].replace(chr(10), ' ')}"
        for entry in journal_service.list_entries(db, 3)
    ]


def _format_dt(value: datetime | None) -> str:
    return value.isoformat(timespec="seconds") if value else "无"


def _reminder_line(task: Task) -> str:
    return (
        f"- #{task.id} {task.title} | 截止/提醒:{_format_dt(task.due_date)} | "
        f"状态:{task.status} | 优先级:{task.priority}"
    )


def _file_line(db_file) -> str:
    parts = [
        f"- #{db_file.id} {db_file.original_name}",
        f"类型:{db_file.mime_type}",
        f"资料类型:{db_file.resource_type or 'file'}",
        f"备注:{db_file.notes}",
    ]
    if db_file.source_url:
        parts.append(f"链接:{db_file.source_url}")
    return " | ".join(parts)


def _subtask_summary(task: Task) -> str:
    if not task.subtasks:
        return "无"
    done = sum(1 for subtask in task.subtasks if subtask.done)
    titles = "；".join(
        f"{'已完成' if subtask.done else '待办'}:{subtask.title}"
        for subtask in task.subtasks[:6]
    )
    suffix = "；..." if len(task.subtasks) > 6 else ""
    return f"{done}/{len(task.subtasks)} | {titles}{suffix}"
