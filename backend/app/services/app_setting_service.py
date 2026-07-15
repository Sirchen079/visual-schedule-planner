from __future__ import annotations

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
}


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
