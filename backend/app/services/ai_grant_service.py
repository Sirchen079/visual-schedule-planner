"""阶段 D1：工具「始终允许」授权服务。

管理 ai_tool_grants 表：grant 命中即视为 safe（跳过确认）。
- create_grant：确认卡片「以后都允许」勾选时调用
- is_granted：_classify_native_call 判定时查询（先查 grant 再回落 safety 分级）
- list_grants / delete_grant：设置面板授权管理

权限三档（agent_autonomy: careful | standard | autonomous）：
- careful：所有 confirm 都问（不查 grant）
- standard：confirm 问，但 grant 命中即免问（默认）
- autonomous：除三大不可豁免高危（empty_trash / bulk_delete_* / import_web_resources）外全部免问
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AIToolGrant

# 不可豁免高危工具（autonomous 档也必须确认）
IRREVOCABLE_TOOLS = {"empty_trash", "bulk_delete_tasks", "bulk_delete_files", "import_web_resources"}


def _autonomy_level(db: Session) -> str:
    """读取权限档位（careful/standard/autonomous），默认 standard。"""
    from app.services import app_setting_service
    val = app_setting_service.get_setting(db, "agent_autonomy") or "standard"
    return val if val in {"careful", "standard", "autonomous"} else "standard"


def is_irrevocable(tool_name: str) -> bool:
    """是否不可豁免高危（autonomous 档也必须确认）。"""
    return tool_name in IRREVOCABLE_TOOLS


def is_granted(db: Session, tool_name: str, args: dict | None = None) -> bool:
    """判断某工具调用是否被「始终允许」规则命中。

    - autonomous 档：除不可豁免高危外，全部视为 granted
    - careful 档：永不 granted（所有 confirm 都问）
    - standard 档：查 grant 表，命中即 granted
    """
    level = _autonomy_level(db)
    if level == "careful":
        return False
    if level == "autonomous":
        return not is_irrevocable(tool_name)
    # standard：查表
    return _match_grant(db, tool_name, args)


def _match_grant(db: Session, tool_name: str, args: dict | None) -> bool:
    """查 grant 表：tool_name 匹配 + arg_pattern 为空（整工具）或参数模式匹配。"""
    rows = db.execute(
        select(AIToolGrant).where(AIToolGrant.tool_name == tool_name)
    ).scalars().all()
    if not rows:
        return False
    for row in rows:
        pattern = (row.arg_pattern or "").strip()
        if not pattern:
            return True  # 整工具允许
        # 参数模式匹配（简单实现：pattern 作为 JSON 子集，args 包含即命中）
        if args and _args_match_pattern(args, pattern):
            return True
    return False


def _args_match_pattern(args: dict, pattern: str) -> bool:
    """宽松参数模式匹配：pattern 是 JSON 片段，args 包含其所有键值即命中。"""
    try:
        expected = json.loads(pattern)
    except (TypeError, ValueError):
        return False
    if not isinstance(expected, dict):
        return False
    for key, value in expected.items():
        if args.get(key) != value:
            return False
    return True


def create_grant(db: Session, tool_name: str, arg_pattern: str = "") -> AIToolGrant:
    """创建一条授权规则。tool_name 必填，arg_pattern 可空（整工具允许）。"""
    grant = AIToolGrant(tool_name=tool_name, arg_pattern=arg_pattern or "")
    db.add(grant)
    db.commit()
    db.refresh(grant)
    return grant


def list_grants(db: Session) -> list[AIToolGrant]:
    return db.execute(
        select(AIToolGrant).order_by(AIToolGrant.created_at.desc())
    ).scalars().all()


def delete_grant(db: Session, grant_id: int) -> bool:
    grant = db.get(AIToolGrant, grant_id)
    if grant is None:
        return False
    db.delete(grant)
    db.commit()
    return True
