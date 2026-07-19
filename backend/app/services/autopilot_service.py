"""秘书自动档：每天一次，AI 主动为用户办妥今日规划。

做什么（且仅做这些低风险写入，全程留痕可撤销）：
1. 智能排程：把临期/未排期任务安排到未来 7 天（assign_task_to_day，source=ai）
2. 大任务拆解：把临近截止、无子任务的高优任务拆成子任务（create_subtask）

授权模型：用户在功能管理显式开启（feature_autopilot_enabled，默认关）；
开启即授权上述两类低风险操作直接执行，不做任何修改/删除/批量操作。
当天幂等：结果存 ai_reports(report_type='autopilot')，同日重复调用直接返回。
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AIConfig, AIReport, Task, TaskScheduleEntry
from app.schemas import ScheduleEntryCreate, SubtaskCreate
from app.services import (
    ai_oneshot_service,
    schedule_service,
    subtask_service,
    task_service,
)

MAX_ASSIGNMENTS = 5
MAX_BREAKDOWNS = 2


async def run_autopilot(
    db: Session, config: AIConfig, target_date: date | None = None
) -> dict:
    """执行当日自动档。返回 {ran, reason?, actions, message}。"""
    day = target_date or date.today()
    stmt = (
        select(AIReport)
        .where(AIReport.report_type == "autopilot", AIReport.period_start == day)
        .order_by(AIReport.id.desc())
    )
    existing = db.execute(stmt).scalars().first()
    if existing is not None:
        try:
            payload = json.loads(existing.content)
            payload["ran"] = bool(payload.get("actions"))
            payload["cached"] = True
            return payload
        except (TypeError, json.JSONDecodeError):
            pass  # 内容损坏则重新执行

    actions: list[dict] = []
    today = day
    week = [today + timedelta(days=i) for i in range(7)]
    month = schedule_service.get_month_schedule(db, today.year, today.month)
    load = {d.date.isoformat(): d.total_count for d in month.days}

    # ---- 1. 智能排程 ----
    scheduled_ids = set(db.execute(select(TaskScheduleEntry.task_id)).scalars().all())
    candidates = []
    for t in task_service.list_tasks(db):
        if t.status == "完成" or t.id in scheduled_ids:
            continue
        due = t.due_date.date() if t.due_date else None
        if due and due <= today + timedelta(days=7):
            candidates.append(t)
        elif t.priority == "高" and not due:
            candidates.append(t)
    candidates = candidates[:10]

    if candidates:
        system = (
            "你是用户的贴身秘书，负责把任务排进未来 7 天。"
            "原则：不晚于截止日、避开高负载日、逾期与高优先任务尽早（今天/明天）、每天不超过 2 个。"
            "只输出 JSON。"
        )
        user = (
            f"今天：{today.isoformat()}\n"
            f"待排任务：{json.dumps([_task_brief(t) for t in candidates], ensure_ascii=False)}\n"
            f"每日现有负载：{json.dumps({d.isoformat(): load.get(d.isoformat(), 0) for d in week}, ensure_ascii=False)}\n"
            f'输出格式：{{"assignments": [{{"task_id": 1, "date": "YYYY-MM-DD", "note": "一句话安排理由"}}]}}，'
            f"最多 {MAX_ASSIGNMENTS} 条；没有合适的就给空数组。"
        )
        result = await ai_oneshot_service.generate_json(db, config, system, user, kind="autopilot")
        by_id = {t.id: t for t in candidates}
        for item in (result or {}).get("assignments", [])[:MAX_ASSIGNMENTS]:
            try:
                task_id = int(item.get("task_id"))
                day_str = date.fromisoformat(str(item.get("date")))
            except (TypeError, ValueError):
                continue
            if task_id not in by_id or day_str < today or day_str > today + timedelta(days=7):
                continue
            entry = schedule_service.create_schedule_entry(
                db,
                ScheduleEntryCreate(
                    task_id=task_id,
                    date=day_str,
                    source="ai",
                    note=str(item.get("note") or "秘书自动排程")[:200],
                ),
            )
            task = by_id[task_id]
            actions.append(
                {
                    "kind": "schedule",
                    "task_id": task_id,
                    "title": task.title,
                    "date": day_str.isoformat(),
                    "entry_id": entry.id,
                    "note": entry.note,
                }
            )

    # ---- 2. 大任务拆解 ----
    breakdown_candidates = [
        t
        for t in task_service.list_tasks(db)
        if t.status != "完成"
        and not t.subtasks
        and t.priority == "高"
        and t.due_date
        and (t.due_date.date() - today).days <= 3
    ][:MAX_BREAKDOWNS]
    for task in breakdown_candidates:
        system = (
            "你是任务拆解专家。把任务拆成 3-5 个具体、可执行、有顺序的子任务，"
            "每条一句话、动词开头。只输出 JSON。"
        )
        user = (
            f"任务：{task.title}\n备注：{task.notes or '无'}\n"
            f"截止：{task.due_date.isoformat()}\n"
            '输出格式：{"subtasks": ["步骤一", "步骤二", ...]}'
        )
        result = await ai_oneshot_service.generate_json(db, config, system, user, kind="autopilot")
        titles = [
            str(t).strip()
            for t in (result or {}).get("subtasks", [])
            if isinstance(t, str) and str(t).strip()
        ][:5]
        if not titles:
            continue
        created = [
            subtask_service.create_subtask(db, task.id, SubtaskCreate(title=title))
            for title in titles
        ]
        actions.append(
            {
                "kind": "breakdown",
                "task_id": task.id,
                "title": task.title,
                "subtasks": titles,
                "subtask_ids": [s.id for s in created if s is not None],
            }
        )

    message = _summary_message(actions)
    payload = {"actions": actions, "message": message}
    report = AIReport(
        report_type="autopilot",
        period_start=day,
        period_end=day,
        title=f"{day.isoformat()} 秘书自动档",
        content=json.dumps(payload, ensure_ascii=False),
        model_name=config.model,
    )
    db.add(report)
    db.commit()
    return {"ran": bool(actions), "cached": False, **payload}


def _task_brief(task: Task) -> dict:
    return {
        "task_id": task.id,
        "title": task.title,
        "priority": task.priority,
        "due": task.due_date.date().isoformat() if task.due_date else None,
        "progress": task.progress or 0,
    }


def _summary_message(actions: list[dict]) -> str:
    scheduled = [a for a in actions if a["kind"] == "schedule"]
    breakdowns = [a for a in actions if a["kind"] == "breakdown"]
    parts = []
    if scheduled:
        parts.append(f"把 {len(scheduled)} 项任务排进了本周")
    if breakdowns:
        names = "、".join(f"「{a['title']}」" for a in breakdowns)
        parts.append(f"把 {names} 拆成了可执行的小步骤")
    if not parts:
        return "今天的事项已经井井有条，无需我代劳。"
    return "我已为你" + "，并".join(parts) + "。"
