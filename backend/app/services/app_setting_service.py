from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppSetting

# 已知设置项及其默认值。list_settings 会用默认值补齐尚未写入库的键。
DEFAULTS: dict[str, str] = {
    "assistant_float_enabled": "false",
    "close_button_behavior": "minimize",
    # AI 日报/周报：每桶任务上限、生成超时（秒）、历史是否按类型过滤
    "report_task_limit": "50",
    "report_timeout_seconds": "180",
    "report_history_filter": "true",
    # 功能开关（功能管理面板）：默认全开，关闭仅隐藏入口、数据保留
    "feature_habits_enabled": "true",
    "feature_journal_enabled": "true",
    "feature_goals_enabled": "true",
    "feature_timer_enabled": "true",
    "feature_inline_ai_enabled": "true",  # 内嵌 AI 动作（用户主动触发，不产生额外自动消耗）
    # 自动代劳/伴随联动：默认关闭（消耗模型调用且代替用户行动，需显式授权）
    "feature_autopilot_enabled": "false",
    "feature_companion_enabled": "false",
    # 晨报开关（同属功能管理）：默认关闭（消耗模型调用，需显式开启）
    "proactive_briefing_enabled": "false",
    # 助手模式：assistant=知时助手（原版问答式）；agent=知时代理（主动代劳的秘书）
    "assistant_mode": "agent",
    # 首次启动引导：0=未完成（全新用户启动时弹欢迎页），1=已完成或已跳过
    "onboarding_done": "0",
    # AI 排程偏好：工作时间与每日深度工作容量（分钟）
    "working_hours_start": "09:00",
    "working_hours_end": "18:00",
    "daily_capacity_minutes": "240",
}


def feature_enabled(db: Session, key: str) -> bool:
    """功能开关读取：未写入时取 DEFAULTS（功能默认开启）。"""
    return (get_setting(db, key) or "false") == "true"


def get_setting(db: Session, key: str, default: str | None = None) -> str | None:
    """读取单个设置；未写入时返回 default（未传则回退到 DEFAULTS）。"""
    row = db.get(AppSetting, key)
    if row is not None:
        return row.value
    if default is not None:
        return default
    return DEFAULTS.get(key)


def list_settings(db: Session) -> dict[str, str]:
    """返回全部设置：DEFAULTS 为底，叠加数据库中实际存储的值。"""
    rows = db.execute(select(AppSetting)).scalars().all()
    stored = {row.key: row.value for row in rows}
    return {**DEFAULTS, **stored}


def set_setting(db: Session, key: str, value: str) -> str:
    """写入单个设置（存在则更新），返回写入后的值。"""
    _upsert(db, key, str(value))
    db.commit()
    return str(value)


def update_settings(db: Session, payload: dict[str, str]) -> dict[str, str]:
    """批量写入设置，返回更新后的全部设置。"""
    for key, value in payload.items():
        _upsert(db, key, str(value))
    db.commit()
    return list_settings(db)


def _upsert(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value


def daily_capacity_minutes(db: Session, default: int = 240) -> int:
    """每日深度工作容量（分钟）：设置缺失或脏值（非数字）时回退 default，避免脏值注入提示词。"""
    raw = get_setting(db, "daily_capacity_minutes")
    if raw and raw.strip().isdigit():
        return int(raw.strip())
    return default


_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def working_hours(db: Session) -> tuple[str, str]:
    """用户工作时段 (start, end)：设置缺失或格式非法时回退 09:00-18:00。"""
    start = (get_setting(db, "working_hours_start") or "").strip()
    end = (get_setting(db, "working_hours_end") or "").strip()
    return (
        start if _HHMM_RE.match(start) else "09:00",
        end if _HHMM_RE.match(end) else "18:00",
    )
