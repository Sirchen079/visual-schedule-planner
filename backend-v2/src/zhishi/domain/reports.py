# src/zhishi/domain/reports.py
"""AI 报告：日报/周报/晨报。数据收集是确定性的（stats/insights/focus），
模型只做一次性文本生成（oneshot，不走 agent 工具循环）。
失败语义：daily/weekly 抛错由路由转 422；briefing 绝不静默失败——
无配置或调用失败降级纯规则文案（model_name="rule"）。"""
from __future__ import annotations

import json
from datetime import date, datetime, time as dtime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from zhishi.agent.providers import build_model, oneshot_text  # 测试 monkeypatch 锚点
from zhishi.domain.models import AIConfig, AIReport, Task

TASK_LIMIT = 20          # 单清单条目上限：防撑爆上下文
REPORT_TYPES = ("daily", "weekly")
BRIEFING_MIN, BRIEFING_MAX = 150, 250  # 晨报字数目标（写进提示词）


def _week_window(target: date) -> tuple[date, date]:
    start = target - timedelta(days=target.weekday())
    return start, start + timedelta(days=6)


def _titles(tasks: list[Task], limit: int = TASK_LIMIT) -> list[str]:
    return [t.title for t in tasks[:limit]]


def collect_data(db: Session, report_type: str, target_date: date) -> dict:
    """确定性数据收集：窗口内日/周分桶，复用 stats/insights/focus。"""
    from zhishi.domain.focus.service import time_stats
    from zhishi.domain.insights import compute_insights
    from zhishi.domain import stats

    if report_type == "weekly":
        start, end = _week_window(target_date)
    else:
        start = end = target_date
    start_dt, end_dt = datetime.combine(start, datetime.min.time()), \
        datetime.combine(end, datetime.max.time())

    active = db.scalars(select(Task).where(
        Task.deleted_at.is_(None), Task.status != "done",
        Task.due_date.is_not(None)).order_by(Task.due_date)).all()
    overdue = [t for t in active if t.due_date < start_dt]
    due_in_window = [t for t in active if start_dt <= t.due_date <= end_dt]
    completed = db.scalars(select(Task).where(
        Task.deleted_at.is_(None), Task.status == "done",
        Task.completed_at.is_not(None),
        Task.completed_at >= start_dt, Task.completed_at <= end_dt)).all()

    trend = [d for d in stats.daily(db, days=7 if report_type == "daily" else 14)
             if start.isoformat() <= d["date"] <= end.isoformat()]
    return {
        "report_type": report_type,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "summary": stats.summary(db),
        "trend": trend,
        "by_tag": stats.by_tag(db)[:10],
        "insights": compute_insights(db, limit=5),
        "focus": time_stats(db, days=7),
        "completed": _titles(completed),
        "overdue": _titles(overdue),
        "due_in_period": _titles(due_in_window),
    }


def build_prompts(config: AIConfig | None, report_type: str, data: dict) -> tuple[str, str]:
    kind = {"daily": "日报", "weekly": "周报"}.get(report_type)
    if kind is None:
        raise ValueError(f"report_type 须为 {' 或 '.join(REPORT_TYPES)}，收到 {report_type!r}")
    system = (f"你是用户的贴身幕僚，基于本地数据写{kind}。直接输出 Markdown："
              "回顾/风险/建议/下一步。只基于给定数据，数据为空如实说明。")
    user = json.dumps(data, ensure_ascii=False, default=str)
    return system, user


def _oneshot_text(model, system: str, user: str) -> str:
    """单次模型调用（无工具循环）。见 providers.oneshot_text。"""
    return oneshot_text(model, system, user)


def generate(db: Session, config: AIConfig, report_type: str, target_date: date) -> AIReport:
    """生成日报/周报并落库。模型/装配/调用失败一律抛错（路由转 422），不落半成品。"""
    data = collect_data(db, report_type, target_date)
    system, user = build_prompts(config, report_type, data)
    text = _oneshot_text(build_model(config), system, user)
    if report_type == "weekly":
        start, end = _week_window(target_date)
        title = f"周报 {start.isoformat()} ~ {end.isoformat()}"
    else:
        title = f"日报 {target_date.isoformat()}"
    row = AIReport(report_type=report_type,
                   period_start=date.fromisoformat(data["period"]["start"]),
                   period_end=date.fromisoformat(data["period"]["end"]),
                   title=title,
                   content=text, model_name=config.model)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---- 晨报（briefing）----

def _briefing_prompts(data: dict) -> tuple[str, str]:
    system = (f"你是用户的贴身幕僚，写一段今日晨报，{BRIEFING_MIN}-{BRIEFING_MAX} 字，"
              "只基于给定数据，数据为空如实说明。直接输出正文，不要标题与客套。")
    return system, json.dumps(data, ensure_ascii=False, default=str)


def build_rule_briefing(data: dict) -> str:
    """纯规则晨报文案：逾期/今日截止/聚焦建议。无 AI 时的兜底，绝不静默失败。"""
    summary, focus = data.get("summary", {}), data.get("focus", {})
    lines: list[str] = []
    overdue = data.get("overdue") or []
    due_today = data.get("due_in_period") or data.get("due_today") or []
    if overdue:
        lines.append(f"有 {summary.get('overdue', len(overdue))} 项逾期，"
                     f"优先处理：「{overdue[0]}」" +
                     (f"等 {len(overdue)} 项" if len(overdue) > 1 else "") + "。")
    if due_today:
        lines.append("今日截止：" + "、".join(f"「{t}」" for t in due_today[:3]) +
                     ("等。" if len(due_today) > 3 else "。"))
    minutes = focus.get("total_minutes") or 0
    if minutes:
        top = (focus.get("by_task") or [{}])[0].get("task_title")
        lines.append(f"近 7 天专注 {minutes} 分钟" +
                     (f"，投入最多的是「{top}」。" if top else "。"))
    todo = summary.get("todo", 0)
    doing = summary.get("doing", 0)
    if todo or doing:
        lines.append(f"当前待办 {todo} 项、进行中 {doing} 项，建议先聚焦一件高优事务。")
    if not lines:
        lines.append("今天暂无逾期与截止事项，安排一段专注时间推进最重要的事即可。")
    return "\n".join(lines)


def get_report(db: Session, report_type: str, target_date: date) -> AIReport | None:
    """按（类型, 窗口起点）取报告——briefing/autopilot 同日幂等的判定依据。"""
    return db.scalar(select(AIReport).where(
        AIReport.report_type == report_type, AIReport.period_start == target_date))


def get_briefing(db: Session, target_date: date) -> AIReport | None:
    return get_report(db, "briefing", target_date)


def generate_briefing(db: Session, config: AIConfig | None, target_date: date) -> AIReport:
    """生成当日晨报（调用方保证同日未生成）。无配置或 AI 失败 → 规则降级。"""
    data = collect_data(db, "briefing", target_date)
    content, model_name = None, None
    if config is not None:
        try:
            system, user = _briefing_prompts(data)
            content = _oneshot_text(build_model(config), system, user)
            model_name = config.model
        except Exception:  # noqa: BLE001 生成链任何失败都降级，晨报必须天天有
            content, model_name = None, None
    if content is None:
        content, model_name = build_rule_briefing(data), "rule"
    row = AIReport(report_type="briefing", period_start=target_date,
                   period_end=target_date, title=f"晨报 {target_date.isoformat()}",
                   content=content, model_name=model_name)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_or_create_briefing(db: Session, config: AIConfig | None,
                           target_date: date) -> AIReport:
    """同日幂等：已有当日晨报直接返回。"""
    existing = get_briefing(db, target_date)
    if existing is not None:
        return existing
    return generate_briefing(db, config, target_date)


def enabled_config(db: Session) -> AIConfig | None:
    return db.scalar(select(AIConfig).where(AIConfig.enabled.is_(True)))


BRIEFING_AFTER = dtime(7, 0)   # 晨报触发时刻：每日 07:00 后（调度器轮询自检）


def should_run_briefing_now(db: Session, now: datetime | None = None) -> bool:
    """调度器自检：已过 07:00 且今日尚无晨报。"""
    now = now or datetime.now()
    if (now.hour, now.minute) < (BRIEFING_AFTER.hour, BRIEFING_AFTER.minute):
        return False
    return get_briefing(db, now.date()) is None


def run_briefing_job(db: Session, target_date: date) -> AIReport:
    """调度器入口：无配置自动降级规则文案，绝不让晨报缺席。
    含 run_sync（自建事件循环），异步上下文须经 asyncio.to_thread 调用。"""
    return get_or_create_briefing(db, enabled_config(db), target_date)
