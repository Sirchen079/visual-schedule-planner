"""秘书自动档：每日一次的低风险自动化，只做两类写——
1) 确定性排程：未排期且 7 天内截止的未完成任务 → 负载最轻且不晚于截止的日期；
2) 大任务拆解：高优、临近截止、无子任务 → 模型 oneshot 拆 3-5 条子任务。
绝不修改/删除既有数据；幂等由 ai_reports(report_type=autopilot) 当日记录保证。"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, time as dtime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from zhishi.agent.providers import build_model, oneshot_text  # 测试 monkeypatch 锚点
from zhishi.domain import reports, settingsvc
from zhishi.domain.models import AIConfig, AIReport, ResearchTask, Subtask, Task, TaskScheduleEntry
from zhishi.domain.schedule.service import assign_task_to_day, range_load as schedule_range_load
from zhishi.domain.subtasks import create_subtask

log = logging.getLogger(__name__)

MAX_ASSIGNMENTS = 10          # 单日自动档排程总量上限
DAY_CAP = 2                   # 每日最多排入的任务数
HORIZON_DAYS = 7              # 排程窗口：截止须在 7 天内
BREAKDOWN_WINDOW_DAYS = 2     # 拆解候选：临近截止窗口
MAX_BREAKDOWNS = 5            # 单日拆解任务数上限
AFTER = dtime(8, 0)           # 每日 08:00 后允许执行（调度器轮询自检）

_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


def should_run_now(db: Session, now: datetime | None = None) -> bool:
    """调度器自检：已过 08:00、开关打开、今日未跑（三条件同时满足才执行）。"""
    now = now or datetime.now()
    if (now.hour, now.minute) < (AFTER.hour, AFTER.minute):
        return False
    if not settingsvc.feature_enabled(db, "feature_autopilot_enabled"):
        return False
    return reports.get_report(db, "autopilot", now.date()) is None


def run_autopilot(db: Session, config: AIConfig | None, target_date: date) -> dict:
    """执行自动档。关闭 → {"ran": False, "reason": "disabled"}；
    当日已跑 → {"ran": False, "reason": "already_ran"}；
    正常 → {"ran": True, "actions": [...], "message": 摘要, "report_id": ...}。"""
    if not settingsvc.feature_enabled(db, "feature_autopilot_enabled"):
        return {"ran": False, "reason": "disabled"}
    existing = reports.get_report(db, "autopilot", target_date)
    if existing is not None:
        return {"ran": False, "reason": "already_ran", "report_id": existing.id}

    actions: list[dict] = []
    assigned = _auto_schedule(db, target_date, actions)
    broken_down = _auto_breakdown(db, config, target_date, actions)
    message = f"自动排程 {assigned} 项任务"
    message += f"，拆解 {broken_down} 项高优任务" if broken_down else ""
    message += "。"

    row = AIReport(report_type="autopilot", period_start=target_date,
                   period_end=target_date, title=f"秘书自动档 {target_date.isoformat()}",
                   content=message, model_name=config.model if config else "rule")
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ran": True, "actions": actions, "message": message, "report_id": row.id}


def _auto_schedule(db: Session, target_date: date, actions: list[dict]) -> int:
    """确定性排程：未排期 + 未完成 + 截止在 [today, today+7] → 逐任务放入
    （日任务数 < DAY_CAP 的日子中）负载最轻、平局取最早、且不晚于截止的日期。"""
    now = datetime.combine(target_date, dtime(0, 0))
    horizon_end = now + timedelta(days=HORIZON_DAYS)
    scheduled_ids = set(db.scalars(select(TaskScheduleEntry.task_id)).all())
    # Learning projects own their prerequisite order, time budgets and slot provenance.
    scheduled_ids.update(db.scalars(select(ResearchTask.task_id)).all())
    candidates = [t for t in db.scalars(select(Task).where(
        Task.deleted_at.is_(None), Task.status != "done",
        Task.due_date.is_not(None), Task.due_date >= now, Task.due_date <= horizon_end)).all()
        if t.id not in scheduled_ids]
    candidates.sort(key=lambda t: (t.due_date, _PRIORITY_RANK.get(t.priority, 1)))

    days = [target_date + timedelta(days=i) for i in range(HORIZON_DAYS + 1)]
    load_view = schedule_range_load(db, target_date, len(days))
    counts = {d: len(load_view.get(d.isoformat(), {}).get("items", [])) for d in days}
    minutes = {d: load_view.get(d.isoformat(), {}).get("estimated_minutes", 0) for d in days}

    assigned = 0
    for task in candidates:
        if assigned >= MAX_ASSIGNMENTS:
            break
        last_day = min(task.due_date.date(), target_date + timedelta(days=HORIZON_DAYS))
        eligible = [d for d in days if d <= last_day and counts[d] < DAY_CAP]
        if not eligible:
            continue
        best = min(eligible, key=lambda d: (minutes[d], d))
        assign_task_to_day(db, task.id, best, source="ai", note="自动档排程")
        counts[best] += 1
        minutes[best] += task.estimated_minutes or 0
        assigned += 1
        actions.append({"kind": "assign", "task_id": task.id,
                        "title": task.title, "date": best.isoformat()})
    return assigned


def _auto_breakdown(db: Session, config: AIConfig | None, target_date: date,
                    actions: list[dict]) -> int:
    """高优、临近截止、无子任务的任务 → 模型拆 3-5 条子任务。
    无模型直接跳过整段；单任务失败跳过继续，不影响排程成果。"""
    if config is None:
        return 0
    soon = (datetime.combine(target_date, dtime(23, 59, 59))
            + timedelta(days=BREAKDOWN_WINDOW_DAYS))
    candidates = db.scalars(select(Task).where(
        Task.deleted_at.is_(None), Task.status != "done", Task.priority == "high",
        ~Task.id.in_(select(ResearchTask.task_id).where(ResearchTask.task_id.is_not(None))),
        Task.due_date.is_not(None), Task.due_date <= soon).order_by(Task.due_date)).all()

    count = 0
    for task in candidates:
        if count >= MAX_BREAKDOWNS:
            break
        has_subs = db.scalar(select(Subtask.id).where(Subtask.task_id == task.id).limit(1))
        if has_subs is not None:
            continue
        titles = _request_subtasks(config, task)
        if not titles:
            continue
        for title in titles:
            create_subtask(db, task.id, title=title)
        count += 1
        actions.append({"kind": "breakdown", "task_id": task.id,
                        "title": task.title, "subtasks": titles})
    return count


def _request_subtasks(config: AIConfig, task: Task) -> list[str]:
    """oneshot 请求 3-5 条子任务标题；任何失败返回空（调用方跳过该任务）。"""
    system = ("你是用户的幕僚。把任务拆成 3-5 条可执行的子任务。"
              "只输出一个 JSON 字符串数组，不要解释、不要代码块标记。")
    user = json.dumps({"task": task.title, "notes": (task.notes or "")[:500],
                       "due": task.due_date.isoformat() if task.due_date else None,
                       "estimated_minutes": task.estimated_minutes},
                      ensure_ascii=False)
    try:
        raw = oneshot_text(build_model(config), system, user)
        data = json.loads(raw)
    except Exception as exc:  # noqa: BLE001 单任务失败跳过，绝不中断自动档
        log.info("autopilot breakdown failed for task %s: %s", task.id, exc)
        return []
    if not isinstance(data, list):
        return []
    titles = [str(x).strip()[:100] for x in data if str(x).strip()]
    return titles[:5]
