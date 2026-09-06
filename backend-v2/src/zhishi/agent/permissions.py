# src/zhishi/agent/permissions.py
"""权限门：全部判定走这一条路径（流式循环/恢复执行/未来计划模式共用）。
返回 'allow'（直接执行）/ 'confirm'（落审批卡片）/ 'deny'（未知工具，直接拒绝）。"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from zhishi.domain import settingsvc

IRREVOCABLE_TOOLS = {"empty_trash", "bulk_delete_tasks", "bulk_delete_files", "import_web_resources"}


def _autonomy(db: Session) -> str:
    return settingsvc.get_setting(db, "agent_autonomy", "standard")


def _mcp_server_id_of(tool_name: str) -> int | None:
    """mcp__{sid}__{name} → sid；非该命名空间返回 None。
    按「__」切分取第二段转 int 精确整数比对——sid 是 sqlite rowid 可复用，
    字符串前缀匹配会误伤（sid=1 撞 sid=10/sid=11）。"""
    if not tool_name.startswith("mcp__"):
        return None
    parts = tool_name.split("__")
    if len(parts) < 3:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def revoke_mcp_grants(db: Session, server_id: int) -> int:
    """撤销某 MCP 服务器的全部「始终允许」授权（re #063 blocker）。
    grants 键 mcp__{sid}__{name} 里的 sid 是 sqlite rowid 可复用：删 A 建 B 得同
    sid、或 PUT 把端点整个换掉，B 的同名工具不得沿用 A 的授权——DELETE 与
    PUT（连接语义字段实际变更）必须在 commit 前调用本函数同事务撤销。
    返回撤销条数（调用方负责 commit）。"""
    from zhishi.domain.models import AIToolGrant
    rows = db.scalars(select(AIToolGrant)).all()
    hit = [r for r in rows if _mcp_server_id_of(r.tool_name) == server_id]
    for row in hit:
        db.delete(row)
    return len(hit)


def expire_mcp_pending_actions(db: Session, server_id: int) -> int:
    """将某 MCP 服务器的 pending 与未消费 confirmed 审批卡置 expired（re #063/#072）。
    旧卡一旦被批准并 resume，会经 ctx.tool_call_approved 绕过权限门直执行
    「同 sid 新服务器」的同名工具——DELETE/PUT 变更连接语义字段后旧卡必须作废。
    状态机 pending → confirmed（approve）→ executed（resume 消费）：approved 但尚未
    resume 的 confirmed 仍有可执行效力，一并作废；executed/rejected 是真终态
    （已消费/明确拒绝），保留为历史审计不回改。
    返回过期条数（调用方负责 commit）。"""
    from zhishi.domain.models import AIPendingAction
    rows = db.scalars(select(AIPendingAction).where(
        AIPendingAction.status.in_(("pending", "confirmed")))).all()
    hit = [r for r in rows if _mcp_server_id_of(r.tool_name) == server_id]
    for row in hit:
        row.status, row.resolved_at = "expired", datetime.now()
    return len(hit)


def _grant_hit(db: Session, tool_name: str, args: dict) -> bool:
    from zhishi.domain.models import AIToolGrant
    rows = db.scalars(select(AIToolGrant).where(AIToolGrant.tool_name == tool_name)).all()
    for row in rows:
        if not row.arg_pattern.strip():
            return True
        try:
            pattern = json.loads(row.arg_pattern)
        except ValueError:
            continue
        if isinstance(pattern, dict) and all(args.get(k) == v for k, v in pattern.items()):
            return True
    return False


def classify(db: Session, tool_name: str, args: dict, *,
             readonly_hint: bool | None = None, mcp_server=None) -> str:
    """判定顺序：MCP 前缀分支 → 注册表存在性 → readonly/safe → autonomy 档位 → grant → confirm。
    careful 档：readonly 放行、safe/confirm 全确认（safe 且 careful 落到 confirm）。
    MCP 动态工具（mcp__ 前缀）：不进 registry，按 server.auto_approve_readonly +
    工具 readOnlyHint 判定；确认判定前查 grants（清账 v1 简化）——审批「始终允许」
    落库的 tool_name 即命名空间全名 mcp__{sid}__{name}，天然对齐，arg_pattern
    子集匹配语义与内置工具一致；careful 档 grants 一律不生效（与内置同边界）。
    MCP 工具不属于 IRREVOCABLE_TOOLS（集合只含内置四件），无不可豁免问题。"""
    if tool_name.startswith("mcp__"):
        if mcp_server is not None and mcp_server.auto_approve_readonly and readonly_hint:
            return "allow"
        if _autonomy(db) in ("standard", "autonomous") and _grant_hit(db, tool_name, args):
            return "allow"
        return "confirm"
    from zhishi.agent.tools.registry import get_spec
    spec = get_spec(tool_name)
    if spec is None:
        return "deny"
    if tool_name == "apply_research_plan":
        from zhishi.domain.models import ResearchPlan
        plan_id = args.get("plan_id")
        if isinstance(plan_id, int):
            plan = db.get(ResearchPlan, plan_id, populate_existing=True)
            if plan is not None and plan.state == "applied":
                # This terminal plan can only return its prior result; it cannot write again.
                return "allow"
    if tool_name == 'apply_secretary_followup':
        from zhishi.domain.models import ResearchPlan, SecretaryFollowup
        followup_id = args.get('followup_id')
        if type(followup_id) is int:
            row = db.get(SecretaryFollowup, followup_id, populate_existing=True)
            plan = db.get(ResearchPlan, row.plan_id, populate_existing=True) if row and row.plan_id else None
            if row and (row.status == 'applied' or plan and plan.state == 'applied'):
                return 'allow'
    autonomy = _autonomy(db)
    if spec.safety == "readonly" or (spec.safety == "safe" and autonomy != "careful"):
        return "allow"
    if autonomy == "autonomous" and tool_name not in IRREVOCABLE_TOOLS:
        return "allow"
    if tool_name in IRREVOCABLE_TOOLS:
        # 不可豁免（re #019 blocker）：任何途径（含历史遗留 grant）都不得免确认，
        # 必须早于 grant 检查短路，否则 (tool, "") 空模式 grant 会永久放行。
        return "confirm"
    if autonomy in ("standard", "autonomous") and _grant_hit(db, tool_name, args):
        return "allow"
    return "confirm"
