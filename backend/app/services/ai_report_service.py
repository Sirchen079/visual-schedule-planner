"""AI 日报/周报：按时间窗口收集任务数据、构造报告 prompt、调用模型生成并落库，外加历史报告 CRUD。

报告是只读分析，走 ai_client 的单次文本生成（不走 agent loop / 工具调用）。
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AIConfig, AIReport, Task
from app.services import (
    ai_client,
    ai_config_service,
    ai_usage_service,
    app_setting_service,
    goal_service,
    habit_service,
    insight_service,
    risk_service,
    task_service,
    timer_service,
)

DONE = "完成"
IN_PROGRESS = "进行中"


# ---- 工具 ----
def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def _dt(value) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


def _task_dict(task: Task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
        "progress": task.progress,
        "start_date": _dt(task.start_date),
        "end_date": _dt(task.end_date),
        "due_date": _dt(task.due_date),
        "tags": [tag.name for tag in task.tags],
    }


# ---- 数据收集 ----
def collect_report_data(
    db: Session,
    report_type: str,
    target_date: date | None = None,
    *,
    task_limit: int = 50,
) -> dict:
    """按日/周窗口把任务分桶，供报告 prompt 与统计使用。

    task_limit>0 时，每桶只保留前 task_limit 条（summary 仍统计真实总数），
    超出部分记入 omitted，避免任务过多撑爆模型 prompt。
    """
    today = target_date or datetime.now().date()
    tasks = task_service.list_tasks(db)
    if report_type == "weekly":
        start = today - timedelta(days=today.weekday())  # 本周周一
        end = start + timedelta(days=6)  # 周日
        next_start = end + timedelta(days=1)
        next_end = next_start + timedelta(days=6)
        next_label = "下周"
    else:
        start = today
        end = today
        next_start = today + timedelta(days=1)
        next_end = next_start
        next_label = "明日"

    def in_window(value) -> bool:
        d = _as_date(value)
        return d is not None and start <= d <= end

    completed: list[dict] = []
    in_progress: list[dict] = []
    due_in_window: list[dict] = []
    overdue: list[dict] = []
    new_in_window: list[dict] = []
    nxt: list[dict] = []

    for task in tasks:
        item = _task_dict(task)
        is_done = task.status == DONE
        # 本期完成：优先按 completed_at（A1 起打点），旧数据回退 updated_at 近似
        done_at = task.completed_at or task.updated_at
        if is_done and in_window(done_at):
            completed.append(item)
        if not is_done:
            if task.status == IN_PROGRESS:
                in_progress.append(item)
            due = _as_date(task.due_date)
            if due is not None:
                if due < start:
                    overdue.append(item)
                elif due <= end:
                    due_in_window.append(item)
                elif next_start <= due <= next_end:
                    nxt.append(item)
        if in_window(task.created_at):
            new_in_window.append(item)

    summary = {
        "total": len(tasks),
        "completed": len(completed),
        "in_progress": len(in_progress),
        "due_in_window": len(due_in_window),
        "overdue": len(overdue),
        "new_in_window": len(new_in_window),
        "next": len(nxt),
    }
    # summary 用真实计数；桶按 task_limit 截断，超出记入 omitted
    buckets = {
        "completed": completed,
        "in_progress": in_progress,
        "due_in_window": due_in_window,
        "overdue": overdue,
        "new_in_window": new_in_window,
        "next": nxt,
    }
    omitted: dict[str, int] = {}
    if task_limit > 0:
        for key, items in buckets.items():
            if len(items) > task_limit:
                omitted[key] = len(items) - task_limit
                buckets[key] = items[:task_limit]
    return {
        "report_type": report_type,
        "period_start": start,
        "period_end": end,
        "next_label": next_label,
        "next_range": [next_start.isoformat(), next_end.isoformat()],
        **buckets,
        "omitted": omitted,
        "summary": summary,
    }


# ---- prompt ----
def build_report_prompt(
    config: AIConfig | None, report_type: str, data: dict
) -> tuple[str, str]:
    """返回 (system_prompt, user_content)，用于单次模型调用。"""
    assistant_name = (config.assistant_name if config else None) or "知时助手"
    type_label = "日报" if report_type == "daily" else "周报"
    period = f"{data['period_start'].isoformat()} ~ {data['period_end'].isoformat()}"
    system = (
        f"你是{assistant_name}的报告生成模块。请根据下方提供的本地任务数据，"
        f"为用户生成一份结构清晰、克制、可执行的{type_label}。\n"
        "要求：\n"
        "- 直接输出 Markdown，不要输出 JSON 或任何多余说明。\n"
        "- 包含以下部分（使用二级/三级标题）：回顾（本期已完成与进展）、"
        f"当前风险（逾期与临近截止）、建议（优先级与节奏调整）、下一步（{data['next_label']}计划）。\n"
        "- 只基于提供的数据，不要编造不存在的任务、日期或进度；数据为空时如实说明。\n"
        "- 语言简练，先结论后细节；数量与任务标题必须准确。\n"
    )
    detail_keys = (
        "completed",
        "in_progress",
        "due_in_window",
        "overdue",
        "new_in_window",
        "next",
    )
    omitted = data.get("omitted", {})
    omitted_hint = ""
    if any(omitted.values()):
        parts = [f"{k} 另有 {v} 项未展示" for k, v in omitted.items() if v]
        omitted_hint = "任务较多已截断，" + "；".join(parts) + "。\n"
    # 周报附加全域数据（目标/习惯/时间投入/幕僚观察），日报保持精简不加
    extra = ""
    if data.get("goals"):
        extra += "\n目标进度（OKR）：\n" + json.dumps(data["goals"], ensure_ascii=False)
    if data.get("habits"):
        extra += "\n习惯打卡：\n" + json.dumps(data["habits"], ensure_ascii=False)
    if data.get("time"):
        extra += "\n时间投入：\n" + json.dumps(data["time"], ensure_ascii=False)
    if data.get("insights"):
        extra += "\n幕僚观察：\n" + json.dumps(data["insights"], ensure_ascii=False)
    if extra:
        extra = (
            "\n（周报还需覆盖：目标推进是否健康、习惯保持情况、时间分配是否合理，"
            "并给出下周期建议）" + extra
        )
    user = (
        f"报告类型：{type_label}\n"
        f"时间窗口：{period}\n"
        f"下一窗口（{data['next_label']}）：{data['next_range'][0]} ~ {data['next_range'][1]}\n"
        f"统计：{json.dumps(data['summary'], ensure_ascii=False)}\n"
        + omitted_hint
        + "\n任务明细（JSON）：\n"
        + json.dumps(
            {k: data[k] for k in detail_keys}, ensure_ascii=False, indent=2
        )
        + extra
    )
    return system, user


# ---- 生成 ----
def _weekly_extra(db: Session) -> dict:
    """周报附加全域数据：目标进度、习惯保持、时间投入、幕僚观察（各按功能开关裁剪）。"""
    extra: dict = {}
    if app_setting_service.feature_enabled(db, "feature_goals_enabled"):
        goals = []
        for goal in goal_service.list_goals(db)[:8]:
            if goal.status != "active":
                continue
            goals.append(
                {
                    "title": goal.title,
                    "progress": goal_service.goal_progress(db, goal),
                    "krs": [
                        {
                            "title": kr.title,
                            "progress": goal_service.kr_progress(db, kr, goal)[1],
                        }
                        for kr in goal.key_results[:5]
                    ],
                }
            )
        extra["goals"] = goals
    if app_setting_service.feature_enabled(db, "feature_habits_enabled"):
        extra["habits"] = [
            {
                "name": h.name,
                "period": h.period,
                **{
                    k: v
                    for k, v in habit_service.habit_status(h).items()
                    if k in ("period_count", "target_count", "streak")
                },
            }
            for h in habit_service.list_habits(db)[:10]
        ]
    if app_setting_service.feature_enabled(db, "feature_timer_enabled"):
        stats = timer_service.time_stats(db, 7)
        extra["time"] = {
            "total_minutes": stats["total_minutes"],
            "by_tag": stats["by_tag"][:5],
            "estimates_overrun": [
                e for e in stats["estimates"] if e["actual_minutes"] > e["estimated_minutes"]
            ][:3],
        }
    extra["insights"] = [item["text"] for item in insight_service.compute_insights(db, 5)]
    return extra


async def generate_report(
    db: Session,
    config: AIConfig,
    report_type: str,
    target_date: date | None = None,
) -> AIReport:
    try:
        task_limit = int(app_setting_service.get_setting(db, "report_task_limit") or 50)
    except (TypeError, ValueError):
        task_limit = 50
    task_limit = max(1, task_limit)
    data = collect_report_data(db, report_type, target_date, task_limit=task_limit)
    if report_type == "weekly":
        data.update(_weekly_extra(db))
    system, user = build_report_prompt(config, report_type, data)
    req = ai_client.build_provider_request(
        provider=config.provider,
        model=config.model,
        api_key=config.api_key,
        messages=[{"role": "user", "content": user}],
        system_prompt=system,
        extra_headers=ai_config_service.headers_from_json(config.extra_headers),
        base_url=config.base_url,
        full_url=config.full_url,
        proxy_url=config.proxy_url,
    )
    raw = await ai_client.call_provider(req)
    ai_usage_service.log_usage(db, config=config, kind="report", payload=raw)
    content = ai_client.extract_text(config.provider, raw)
    type_label = "日报" if report_type == "daily" else "周报"
    report = AIReport(
        report_type=report_type,
        period_start=data["period_start"],
        period_end=data["period_end"],
        title=f"{data['period_start'].isoformat()} {type_label}",
        content=content or "",
        model_name=config.model,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


# ---- 晨报（幕僚线）：当天幂等，AI 生成优先、失败降级为规则文案 ----
def build_briefing_prompt(config: AIConfig | None, data: dict) -> tuple[str, str]:
    """晨报 prompt：像了解全局的秘书在早晨简短汇报。返回 (system, user)。"""
    assistant_name = (config.assistant_name if config else None) or "知时助手"
    system = (
        f"你是{assistant_name}，用户的贴身幕僚。根据用户的本地任务数据生成一份晨报。\n"
        "要求：\n"
        "- 150~250 字，口吻克制、可执行，像秘书早晨汇报，不要客套话\n"
        "- 先讲必须处理的（已逾期 + 今日截止），点出最关键的任务名（优先级高者优先）\n"
        "- 再讲进行中事项的一句话建议，最后给一条今日聚焦建议\n"
        "- 用 Markdown 短段落或少量列表，不要标题层级，不要罗列全部任务\n"
    )
    user = (
        f"日期：{data['period_start'].isoformat()}\n"
        f"统计：{json.dumps(data['summary'], ensure_ascii=False)}\n"
        f"已逾期：{json.dumps(data['overdue'], ensure_ascii=False)}\n"
        f"今日截止：{json.dumps(data['due_in_window'], ensure_ascii=False)}\n"
        f"进行中：{json.dumps(data['in_progress'], ensure_ascii=False)}\n"
        f"明日到期：{json.dumps(data['next'], ensure_ascii=False)}\n"
        f"风险预警：{json.dumps(data.get('risks', []), ensure_ascii=False, default=str)}\n"
        f"今日未打卡习惯：{json.dumps(data.get('habits_pending', []), ensure_ascii=False)}\n"
        f"幕僚观察：{json.dumps(data.get('insights', []), ensure_ascii=False)}"
    )
    return system, user


def build_rule_briefing(data: dict) -> str:
    """无 AI 配置（或模型调用失败）时的规则文案晨报。"""
    s = data["summary"]
    lines = [f"**{data['period_start'].isoformat()} 晨报**", ""]
    if s["overdue"]:
        titles = "、".join(f"「{t['title']}」" for t in data["overdue"][:3])
        lines.append(f"- {s['overdue']} 项已逾期，建议优先处理：{titles}")
    if s["due_in_window"]:
        titles = "、".join(f"「{t['title']}」" for t in data["due_in_window"][:3])
        lines.append(f"- 今日截止 {s['due_in_window']} 项：{titles}")
    if s["in_progress"]:
        lines.append(f"- 进行中 {s['in_progress']} 项，保持推进")
    if s["next"]:
        lines.append(f"- 明日到期 {s['next']} 项，可提前安排")
    risks = data.get("risks") or []
    if risks:
        top = risks[0]
        lines.append(f"- 风险预警：「{top['title']}」（{'；'.join(top['reasons'])}）")
    habits = data.get("habits_pending") or []
    if habits:
        lines.append(f"- 习惯未打卡 {len(habits)} 个：{'、'.join(habits[:3])}")
    insights = data.get("insights") or []
    for insight in insights[:2]:
        lines.append(f"- {insight}")
    if not any([s["overdue"], s["due_in_window"], s["in_progress"], s["next"], risks, habits, insights]):
        lines.append("- 今日没有紧迫事项，可以从容规划。")
    return "\n".join(lines)


async def generate_briefing(
    db: Session, config: AIConfig | None, target_date: date | None = None
) -> AIReport:
    """生成晨报并落库。模型调用失败时静默降级为规则文案，绝不打扰用户。"""
    data = collect_report_data(db, "daily", target_date, task_limit=10)
    # 幕僚视角补充：风险预测 Top3 与今日未达标习惯（习惯功能关闭则略过）
    risks = risk_service.compute_risk(db, limit=3)
    habits_pending = []
    if app_setting_service.feature_enabled(db, "feature_habits_enabled"):
        habits_pending = [
            f"{h.name}（{habit_service.habit_status(h)['period_count']}/{h.target_count}）"
            for h in habit_service.list_habits(db)
            if not habit_service.habit_status(h)["done_today"]
        ]
    data["risks"] = risks
    data["habits_pending"] = habits_pending
    # 幕僚洞察：跨域注意点（断签/KR 落后/预估偏差/计时异常/情绪线索）
    data["insights"] = [item["text"] for item in insight_service.compute_insights(db, 4)]
    content: str | None = None
    model_name = "规则模板"
    if config is not None:
        try:
            system, user = build_briefing_prompt(config, data)
            req = ai_client.build_provider_request(
                provider=config.provider,
                model=config.model,
                api_key=config.api_key,
                messages=[{"role": "user", "content": user}],
                system_prompt=system,
                extra_headers=ai_config_service.headers_from_json(config.extra_headers),
                base_url=config.base_url,
                full_url=config.full_url,
                proxy_url=config.proxy_url,
            )
            raw = await ai_client.call_provider(req)
            ai_usage_service.log_usage(db, config=config, kind="briefing", payload=raw)
            content = ai_client.extract_text(config.provider, raw) or None
            model_name = config.model
        except Exception:
            content = None
    if not content:
        content = build_rule_briefing(data)
        model_name = "规则模板"
    report = AIReport(
        report_type="briefing",
        period_start=data["period_start"],
        period_end=data["period_end"],
        title=f"{data['period_start'].isoformat()} 晨报",
        content=content,
        model_name=model_name,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


async def get_or_create_briefing(
    db: Session, config: AIConfig | None, target_date: date | None = None
) -> tuple[AIReport, bool]:
    """当天幂等：已有当天晨报直接返回 (report, False)，否则生成 (report, True)。"""
    day = target_date or datetime.now().date()
    stmt = (
        select(AIReport)
        .where(AIReport.report_type == "briefing", AIReport.period_start == day)
        .order_by(AIReport.id.desc())
    )
    existing = db.execute(stmt).scalars().first()
    if existing is not None:
        return existing, False
    return await generate_briefing(db, config, day), True


# ---- CRUD ----
def list_reports(db: Session, report_type: str | None = None) -> list[AIReport]:
    stmt = select(AIReport).order_by(AIReport.created_at.desc(), AIReport.id.desc())
    if report_type:
        stmt = stmt.where(AIReport.report_type == report_type)
    return list(db.execute(stmt).scalars().all())


def get_report(db: Session, report_id: int) -> AIReport | None:
    return db.get(AIReport, report_id)


def delete_report(db: Session, report_id: int) -> bool:
    report = db.get(AIReport, report_id)
    if report is None:
        return False
    db.delete(report)
    db.commit()
    return True
