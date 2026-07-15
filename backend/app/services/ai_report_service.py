"""AI 日报/周报：按时间窗口收集任务数据、构造报告 prompt、调用模型生成并落库，外加历史报告 CRUD。

报告是只读分析，走 ai_client 的单次文本生成（不走 agent loop / 工具调用）。
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AIConfig, AIReport, Task
from app.services import ai_client, ai_config_service, app_setting_service, task_service

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
        # 本期完成：状态完成且 updated_at 落在窗口（Task 无 completed_at，近似）
        if is_done and in_window(task.updated_at):
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
    )
    return system, user


# ---- 生成 ----
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
