"""幕僚洞察引擎：跨域（习惯/目标/时间/日记/任务）确定性观察，产出可直接引用的短句。

与 risk_service 的区别：risk 只看任务逾期风险；insight 是幕僚的「全域注意点」——
断签、KR 落后、预估偏差、计时异常、情绪线索、数据缺口。
注入对话上下文与晨报，让 AI 主动带上这些观察（而不是等用户问）。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import JournalEntry, Task, TimeLog
from app.services import (
    app_setting_service,
    goal_service,
    habit_service,
    timer_service,
)


def compute_insights(db: Session, limit: int = 5) -> list[dict]:
    """返回 [{kind, severity(mid/low), text}]，按优先级排序，最多 limit 条。"""
    insights: list[dict] = []
    if app_setting_service.feature_enabled(db, "feature_goals_enabled"):
        insights += _goal_insights(db)
    if app_setting_service.feature_enabled(db, "feature_timer_enabled"):
        insights += _timer_insights(db)
    if app_setting_service.feature_enabled(db, "feature_habits_enabled"):
        insights += _habit_insights(db)
    if app_setting_service.feature_enabled(db, "feature_journal_enabled"):
        insights += _journal_insights(db)
    insights += _task_insights(db)
    # mid 优先，其次按给定顺序稳定输出
    insights.sort(key=lambda i: 0 if i["severity"] == "mid" else 1)
    return insights[: max(1, limit)]


def _goal_insights(db: Session) -> list[dict]:
    """KR 周期落后：目标时间消耗显著快于进度。"""
    out = []
    today = date.today()
    for goal in goal_service.list_goals(db):
        if goal.status != "active" or not goal.start_date or not goal.end_date:
            continue
        total_days = (goal.end_date - goal.start_date).days
        if total_days <= 0 or today < goal.start_date:
            continue
        elapsed_pct = min(100, round((today - goal.start_date).days / total_days * 100))
        progress = goal_service.goal_progress(db, goal)
        if elapsed_pct >= progress + 25 and elapsed_pct >= 30:
            lagging = min(
                (kr for kr in goal.key_results),
                key=lambda kr: goal_service.kr_progress(db, kr, goal)[1],
                default=None,
            )
            kr_hint = f"，最拖后腿的是「{lagging.title}」" if lagging else ""
            out.append(
                {
                    "kind": "kr_behind",
                    "severity": "mid",
                    "text": (
                        f"目标「{goal.title}」时间已过 {elapsed_pct}% 但进度只有 {progress}%{kr_hint}。"
                        "建议本周给它安排具体任务，或和我重新校准目标范围。"
                    ),
                }
            )
    return out


def _timer_insights(db: Session) -> list[dict]:
    out = []
    # 计时超长未停
    running = timer_service.current_log(db)
    if running is not None:
        elapsed = (datetime.now() - running.started_at).total_seconds() / 60
        if elapsed >= 60:
            out.append(
                {
                    "kind": "timer_long_running",
                    "severity": "mid",
                    "text": (
                        f"「{running.task_title}」的专注已进行 {round(elapsed)} 分钟未停，"
                        "可能忘了结束——建议先停下休息，或我帮你结束计时。"
                    ),
                }
            )
    # 预估严重偏差（近 30 天）
    stats = timer_service.time_stats(db, 30)
    for est in stats["estimates"]:
        if est["estimated_minutes"] > 0 and est["actual_minutes"] >= est["estimated_minutes"] * 2:
            out.append(
                {
                    "kind": "estimate_overrun",
                    "severity": "mid",
                    "text": (
                        f"「{est['title']}」已投入 {est['actual_minutes']} 分钟，"
                        f"是预估 {est['estimated_minutes']} 分钟的两倍多。"
                        "值得看看是低估了工时，还是任务该拆小。"
                    ),
                }
            )
            break  # 只报最严重的一条
    # 有产出但从没计时（近 7 天）
    week_ago = datetime.now() - timedelta(days=7)
    completed = db.execute(
        select(func.count()).select_from(Task).where(
            Task.deleted_at.is_(None),
            Task.status == "完成",
            Task.completed_at >= week_ago,
        )
    ).scalar() or 0
    logs = db.execute(
        select(func.count()).select_from(TimeLog).where(TimeLog.started_at >= week_ago)
    ).scalar() or 0
    if completed >= 2 and logs == 0:
        out.append(
            {
                "kind": "no_time_tracking",
                "severity": "low",
                "text": (
                    f"本周完成了 {completed} 项任务但没有计时记录。"
                    "试试从任务卡右键「开始专注」，时间数据会帮我给你更准的建议。"
                ),
            }
        )
    return out


def _habit_insights(db: Session) -> list[dict]:
    """有连续纪录的习惯今天还没达标：提醒保纪录。"""
    out = []
    for habit in habit_service.list_habits(db):
        status = habit_service.habit_status(habit)
        if status["done_today"] or status["streak"] < 3:
            continue
        unit = "天" if habit.period == "daily" else "周"
        out.append(
            {
                "kind": "habit_streak_risk",
                "severity": "low",
                "text": (
                    f"「{habit.name}」已连续 {status['streak']} {unit}达标，今天还没完成——"
                    "现在花两分钟就能保住纪录。"
                ),
            }
        )
    return out


def _journal_insights(db: Session) -> list[dict]:
    out = []
    entries = (
        db.execute(select(JournalEntry).order_by(JournalEntry.date.desc()).limit(7))
        .scalars()
        .all()
    )
    if not entries:
        return out
    recent3 = entries[:3]
    low = sum(1 for e in recent3 if e.mood == "差")
    if low >= 2:
        out.append(
            {
                "kind": "journal_mood_low",
                "severity": "mid",
                "text": (
                    "最近几篇日记心情持续偏低。我在——要不要聊聊发生了什么，"
                    "或者把压在心里的事拆成几件能处理的小事？"
                ),
            }
        )
    yesterday = date.today() - timedelta(days=1)
    if entries[0].date < yesterday and len(entries) >= 3:
        out.append(
            {
                "kind": "journal_missing",
                "severity": "low",
                "text": "昨天没写日记。花两分钟记一笔今天的状态和一件值得记住的事？我可以代笔整理。",
            }
        )
    return out


def _task_insights(db: Session) -> list[dict]:
    """高优先级任务临近截止但毫无排期/子任务拆解。"""
    out = []
    today = date.today()
    rows = (
        db.execute(
            select(Task).where(
                Task.deleted_at.is_(None),
                Task.status != "完成",
                Task.priority == "高",
                Task.due_date.is_not(None),
            )
        )
        .scalars()
        .all()
    )
    for task in rows:
        days_left = (task.due_date.date() - today).days
        if 0 <= days_left <= 2 and not task.subtasks and (task.progress or 0) < 30:
            out.append(
                {
                    "kind": "big_task_undivided",
                    "severity": "mid",
                    "text": (
                        f"高优任务「{task.title}」还剩 {days_left or '零'} 天截止，"
                        "进度低且没有拆解。要不要我帮你拆成今天能上手的几个小步骤？"
                    ),
                }
            )
            break
    return out
