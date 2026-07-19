"""内嵌 AI 动作：长在功能现场的一键 AI 直接执行（不跳聊天窗）。

四个动作：任务拆解子任务、任务智能排程、日记本日小结草稿、番茄钟收束语。
全部只做低风险写入（子任务/日程排期/草稿文本），失败降级为规则结果或友好错误。
"""
from __future__ import annotations

from datetime import date as date_type, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import ScheduleEntryCreate, SubtaskCreate
from app.services import (
    ai_config_service,
    ai_oneshot_service,
    ai_prompt_service,
    app_setting_service,
    habit_service,
    schedule_service,
    subtask_service,
    task_service,
    timer_service,
)

router = APIRouter(prefix="/ai/actions", tags=["ai-actions"])


class BreakdownRequest(BaseModel):
    task_id: int


class ScheduleTaskRequest(BaseModel):
    task_id: int
    date: date_type | None = None  # 指定日期时直接排程（无需 AI）


class JournalDraftRequest(BaseModel):
    date: date_type | None = None


class TimerSignoffRequest(BaseModel):
    log_id: int


def _require_inline(db: Session) -> None:
    if not app_setting_service.feature_enabled(db, "feature_inline_ai_enabled"):
        raise HTTPException(status_code=403, detail="内嵌 AI 动作已关闭，可在功能管理中开启")


def _require_companion(db: Session) -> None:
    if not app_setting_service.feature_enabled(db, "feature_companion_enabled"):
        raise HTTPException(status_code=403, detail="伴随联动已关闭，可在功能管理中开启")
    if ai_prompt_service.assistant_mode(db) != "agent":
        raise HTTPException(status_code=403, detail="伴随联动是「知时代理」专属能力，请在助手中切换到知时代理")


def _enabled_config(db: Session):
    return ai_config_service.get_enabled_config(db)


# ---- 1. AI 拆解子任务 ----
@router.post("/breakdown-subtasks")
async def breakdown_subtasks(payload: BreakdownRequest, db: Session = Depends(get_db)):
    _require_inline(db)
    task = task_service.get_task(db, payload.task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    config = _enabled_config(db)
    if config is None:
        raise HTTPException(status_code=400, detail="未启用 AI 配置，请先在助手中配置模型")
    if task.subtasks:
        raise HTTPException(status_code=409, detail="该任务已有子任务，请先清理后再拆解")

    system = (
        "你是任务拆解专家。把用户给出的任务拆成 3-6 个具体、可执行、有先后顺序的子任务。"
        "每个子任务一句话、动词开头、可在一次专注内完成。只输出 JSON。"
    )
    user = (
        f"任务标题：{task.title}\n备注：{task.notes or '无'}\n"
        f"截止：{task.due_date.isoformat() if task.due_date else '无'}\n"
        '输出格式：{"subtasks": ["步骤一", "步骤二", ...]}'
    )
    result = await ai_oneshot_service.generate_json(db, config, system, user, kind="inline")
    titles = [
        str(t).strip()
        for t in (result or {}).get("subtasks", [])
        if isinstance(t, str) and str(t).strip()
    ][:6]
    if not titles:
        raise HTTPException(status_code=502, detail="AI 未能给出有效拆解，请换个问法或稍后再试")
    created = [
        subtask_service.create_subtask(db, task.id, SubtaskCreate(title=title))
        for title in titles
    ]
    return {
        "ok": True,
        "task_id": task.id,
        "subtasks": [
            {"id": s.id, "title": s.title, "done": s.done} for s in created if s is not None
        ],
    }


# ---- 2. AI 智能排程 ----
@router.post("/schedule-task")
async def schedule_task(payload: ScheduleTaskRequest, db: Session = Depends(get_db)):
    _require_inline(db)
    task = task_service.get_task(db, payload.task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    target = payload.date
    note = "手动排程"
    if target is None:
        config = _enabled_config(db)
        if config is None:
            raise HTTPException(status_code=400, detail="未启用 AI 配置，请先在助手中配置模型")
        today = date_type.today()
        month = schedule_service.get_month_schedule(db, today.year, today.month)
        pressure = {
            day.date.isoformat(): day.total_count for day in month.days
        }
        days = [today + timedelta(days=i) for i in range(7)]
        system = (
            "你是日程规划秘书。根据任务截止日与未来 7 天每日负载，为任务选一个最合适的日子。"
            "原则：不晚于截止日、避开高负载日、重要任务尽早。只输出 JSON。"
        )
        user = (
            f"今天：{today.isoformat()}\n"
            f"任务：{task.title}（优先级 {task.priority}，截止 "
            f"{task.due_date.isoformat() if task.due_date else '无'}）\n"
            f"候选日期与当前负载：{ {d.isoformat(): pressure.get(d.isoformat(), 0) for d in days} }\n"
            '输出格式：{"date": "YYYY-MM-DD", "reason": "一句话理由"}'
        )
        result = await ai_oneshot_service.generate_json(db, config, system, user, kind="inline")
        try:
            target = date_type.fromisoformat(str((result or {}).get("date", "")))
        except ValueError:
            target = None
        if target is None or target < today or target > today + timedelta(days=7):
            raise HTTPException(status_code=502, detail="AI 未能给出合适的日期，请手动选择")
        note = str((result or {}).get("reason") or "AI 排程")[:200]

    entry = schedule_service.create_schedule_entry(
        db,
        ScheduleEntryCreate(task_id=task.id, date=target, source="ai", note=note),
    )
    return {"ok": True, "task_id": task.id, "date": target.isoformat(), "note": entry.note}


# ---- 3. 日记本日小结草稿 ----
@router.post("/journal-draft")
async def journal_draft(payload: JournalDraftRequest, db: Session = Depends(get_db)):
    _require_inline(db)
    day = payload.date or date_type.today()
    # 汇总当日素材：完成任务、习惯打卡、专注时长
    tasks_today = [
        t for t in task_service.list_tasks(db)
        if t.completed_at and t.completed_at.date() == day
    ]
    habits = []
    if app_setting_service.feature_enabled(db, "feature_habits_enabled"):
        for habit in habit_service.list_habits(db):
            status = habit_service.habit_status(habit, day)
            if status["today_count"] > 0:
                habits.append(f"{habit.name}×{status['today_count']}")
    logs = [log for log in timer_service.list_logs(db, 1) if log.started_at.date() == day]
    focus_minutes = sum(log.minutes for log in logs)

    facts = (
        f"日期：{day.isoformat()}\n"
        f"完成任务：{[t.title for t in tasks_today] or ['无']}\n"
        f"习惯打卡：{habits or ['无']}\n"
        f"专注投入：{focus_minutes} 分钟（{[log.task_title for log in logs][:5]}）"
    )
    config = _enabled_config(db)
    if config is not None:
        system = (
            "你是用户的贴身幕僚，根据今日事实为用户写一段日记草稿。"
            "150-220 字，第一人称，口语自然不堆砌；先写完成了什么，再写一句感受或明天要注意的。"
            "只基于事实，不要编造心情与事件。"
        )
        try:
            content = await ai_oneshot_service.generate_text(
                db, config, system, facts, kind="inline"
            )
            if content:
                return {"ok": True, "date": day.isoformat(), "content": content, "source": "ai"}
        except Exception:
            pass  # 降级规则模板
    # 规则模板（无 AI 配置或调用失败）
    lines = [f"## {day.isoformat()} 小结", ""]
    if tasks_today:
        lines.append("今天完成了：" + "、".join(f"「{t.title}」" for t in tasks_today) + "。")
    if habits:
        lines.append("打卡：" + "、".join(habits) + "。")
    if focus_minutes:
        lines.append(f"专注投入 {focus_minutes} 分钟。")
    if len(lines) == 2:
        lines.append("今天比较安静，适合整理和规划。")
    return {
        "ok": True,
        "date": day.isoformat(),
        "content": "\n".join(lines),
        "source": "rule",
    }


# ---- 4. 番茄钟收束语 ----
@router.post("/timer-signoff")
async def timer_signoff(payload: TimerSignoffRequest, db: Session = Depends(get_db)):
    _require_companion(db)
    from app.models import TimeLog

    log = db.get(TimeLog, payload.log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="计时记录不存在")

    config = _enabled_config(db)
    if config is not None:
        task = task_service.get_task(db, log.task_id) if log.task_id else None
        context_bits = [f"刚完成 {log.minutes} 分钟专注，任务是「{log.task_title}」。"]
        if task is not None:
            context_bits.append(f"任务当前进度 {task.progress or 0}%，状态 {task.status}。")
        system = (
            "你是用户的贴身幕僚。用户刚结束一段番茄钟，写一句收束语（不超过 40 字）："
            "肯定这段投入，视任务进度给一句轻巧的下一步提示或休息提醒。口语、克制、不鸡汤。"
        )
        try:
            text = await ai_oneshot_service.generate_text(
                db, config, system, "\n".join(context_bits), kind="companion"
            )
            if text:
                return {"ok": True, "text": text.strip('" '), "source": "ai"}
        except Exception:
            pass
    return {
        "ok": True,
        "text": f"《{log.task_title}》专注 {log.minutes} 分钟，辛苦了，喝口水再决定下一步。",
        "source": "rule",
    }
