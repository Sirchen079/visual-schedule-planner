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
    app_setting_service,
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
    load_days = schedule_service.get_range_load(db, today, 7)

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
        capacity = app_setting_service.daily_capacity_minutes(db)
        work_start, work_end = app_setting_service.working_hours(db)
        system = (
            "你是用户的贴身秘书，负责把任务排进未来 7 天。"
            "原则：不晚于截止日、避开高负载日、逾期与高优先任务尽早（今天/明天）、每天不超过 2 个；"
            f"用户工作时段 {work_start}-{work_end}，每天深度工作总量不宜超过 {capacity} 分钟。"
            "只输出 JSON。"
        )
        load_text = "\n".join(
            f"  {d['date']} 周{d['weekday']}：已排 {d['count']} 项、约 {d['total_minutes']} 分钟"
            for d in load_days
        )
        user = (
            f"今天：{today.isoformat()} 周{'一二三四五六日'[today.weekday()]}\n"
            f"待排任务：{json.dumps([_task_brief(t) for t in candidates], ensure_ascii=False)}\n"
            f"未来 7 天每日已排：\n{load_text}\n"
            f'输出格式：{{"assignments": [{{"task_id": 1, "date": "YYYY-MM-DD", "note": "一句话安排理由"}}]}}，'
            f"最多 {MAX_ASSIGNMENTS} 条；没有合适的就给空数组。"
        )
        schedule_failed = False
        try:
            result = await ai_oneshot_service.generate_json(db, config, system, user, kind="autopilot")
        except Exception as exc:  # provider 网络/5xx 等：记 error，不让自动档整体 500
            result = None
            schedule_failed = True
            actions.append({"kind": "error", "message": f"AI 排程调用失败，已跳过：{exc}"})
        if result is None and not schedule_failed:
            # 解析失败（非异常）：AI 没返回可用的 JSON
            actions.append({"kind": "error", "message": "AI 排程未返回有效结果，已跳过"})
        by_id = {t.id: t for t in candidates}
        for item in (result or {}).get("assignments", [])[:MAX_ASSIGNMENTS]:
            try:
                task_id = int(item.get("task_id"))
                day_str = date.fromisoformat(str(item.get("date")))
            except (TypeError, ValueError):
                continue
            if task_id not in by_id or day_str < today or day_str > today + timedelta(days=6):
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
            "你是任务拆解专家。把任务拆成 3-5 个可立即执行的子任务。要求："
            "每条一句话、动词开头、有明确产出物，禁止「准备」「着手」「跟进」「完善」这类空泛步骤；"
            "每条 30-90 分钟可完成；顺序即执行顺序。只输出 JSON。"
        )
        user = (
            f"任务：{task.title}\n备注：{task.notes or '无'}\n"
            f"截止：{task.due_date.isoformat()}，优先级 {task.priority}\n"
            '输出格式：{"subtasks": ["步骤一", "步骤二", ...]}'
        )
        try:
            result = await ai_oneshot_service.generate_json(db, config, system, user, kind="autopilot")
        except Exception as exc:  # provider 网络/5xx 等：记 error 跳过本任务，不让自动档整体 500
            actions.append({"kind": "error", "message": f"「{task.title}」拆解调用失败，已跳过：{exc}"})
            continue
        titles = [
            str(t).strip()
            for t in (result or {}).get("subtasks", [])
            if isinstance(t, str) and str(t).strip()
        ][:5]
        if not titles:
            actions.append({"kind": "error", "message": f"「{task.title}」拆解未返回有效结果，已跳过"})
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
        "estimated_minutes": task.estimated_minutes,
        "notes": (task.notes or "")[:100],
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
    errors = [a for a in actions if a.get("kind") == "error"]
    if not parts and errors:
        # 排程和拆解都失败：不要拼成"我已为你 N 项未能完成"（主语错位）
        return f"今天尝试代劳但 {len(errors)} 项未能完成（详见记录），可能需要你手动处理。"
    if not parts:
        return "今天的事项已经井井有条，无需我代劳。"
    if errors:
        parts.append(f"{len(errors)} 项未能完成（详见记录）")
    return "我已为你" + "，并".join(parts) + "。"
