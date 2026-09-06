"""应用设置：key-value + 功能开关 + 工作时段。脏值一律回退默认。"""
from __future__ import annotations
import re
from sqlalchemy.orm import Session
from zhishi.domain.models import AppSetting

DEFAULTS: dict[str, str] = {
    "feature_tasks_enabled": "true",
    "feature_schedule_enabled": "true",
    "feature_goals_enabled": "true",
    "feature_habits_enabled": "true",
    "feature_journal_enabled": "true",
    "feature_focus_enabled": "true",
    "feature_library_enabled": "true",
    "working_hours_start": "09:00",
    "working_hours_end": "18:00",
    "daily_capacity_minutes": "480",
    "assistant_mode": "agent",
    "agent_autonomy": "standard",  # careful/standard/autonomous（消费）
    "feature_autopilot_enabled": "false",  # 秘书自动档：默认关闭
    "feature_followup_enabled": "true",  # 规则跟进；实际调整仍检查自动档与授权。
    "compaction_threshold": "12",  # 会话摘要压缩触发阈值（轮数）
}

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def get_setting(db: Session, key: str, default: str | None = None) -> str:
    row = db.get(AppSetting, key)
    if row is not None and row.value != "":
        return row.value
    if default is not None:
        return default
    return DEFAULTS.get(key, "")


def set_setting(db: Session, key: str, value: str) -> str:
    row = db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()
    return value


def feature_enabled(db: Session, key: str) -> bool:
    return get_setting(db, key) == "true"


def working_hours(db: Session) -> tuple[str, str]:
    start = get_setting(db, "working_hours_start")
    end = get_setting(db, "working_hours_end")
    if not _HHMM.match(start) or not _HHMM.match(end) or start >= end:
        return ("09:00", "18:00")
    return (start, end)


def daily_capacity_minutes(db: Session, default: int = 480) -> int:
    raw = get_setting(db, "daily_capacity_minutes")
    try:
        return int(raw)
    except ValueError:
        return default
