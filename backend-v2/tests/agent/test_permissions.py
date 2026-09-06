import pytest
from zhishi.agent.permissions import classify, IRREVOCABLE_TOOLS
from zhishi.domain import settingsvc


def test_irrevocable_set():
    assert IRREVOCABLE_TOOLS == {"empty_trash", "bulk_delete_tasks", "bulk_delete_files",
                                 "import_web_resources"}


def test_readonly_always_allowed(db):
    assert classify(db, "list_tasks", {}) == "allow"


def test_safe_allowed(db):
    assert classify(db, "create_task", {}) == "allow"


def test_confirm_needs_approval_standard(db):
    settingsvc.set_setting(db, "agent_autonomy", "standard"); db.commit()
    assert classify(db, "delete_task", {}) == "confirm"


def test_grant_hit_skips_confirm(db):
    from zhishi.domain.models import AIToolGrant
    db.add(AIToolGrant(tool_name="update_task", arg_pattern='{"task_id": 1}')); db.commit()
    assert classify(db, "update_task", {"task_id": 1, "title": "新"}) == "allow"
    assert classify(db, "update_task", {"task_id": 2}) == "confirm"   # 参数模式不匹配
    db.add(AIToolGrant(tool_name="delete_task", arg_pattern="")); db.commit()
    assert classify(db, "delete_task", {}) == "allow"                 # 空模式=整工具


def test_autonomous_bypasses_confirm_but_not_irrevocable(db):
    settingsvc.set_setting(db, "agent_autonomy", "autonomous"); db.commit()
    assert classify(db, "delete_task", {}) == "allow"
    assert classify(db, "empty_trash", {}) == "confirm"


def test_grant_cannot_exempt_irrevocable(db):
    """预置 (empty_trash, "") 全工具 grant 后 classify 仍必须 confirm。
    不可豁免 = 任何途径（历史遗留 grant / autonomous / grant_always）都不得免确认。"""
    from zhishi.domain.models import AIToolGrant
    for tool in sorted(IRREVOCABLE_TOOLS):
        db.add(AIToolGrant(tool_name=tool, arg_pattern=""))   # 空模式=整工具放行
    db.commit()
    settingsvc.set_setting(db, "agent_autonomy", "standard"); db.commit()
    for tool in sorted(IRREVOCABLE_TOOLS):
        assert classify(db, tool, {}) == "confirm", f"{tool} 被遗留 grant 豁免"
    settingsvc.set_setting(db, "agent_autonomy", "autonomous"); db.commit()
    for tool in sorted(IRREVOCABLE_TOOLS):
        assert classify(db, tool, {}) == "confirm", f"{tool} 在 autonomous 档被豁免"


def test_careful_asks_everything_and_ignores_grants(db):
    settingsvc.set_setting(db, "agent_autonomy", "careful"); db.commit()
    from zhishi.domain.models import AIToolGrant
    db.add(AIToolGrant(tool_name="delete_task", arg_pattern="")); db.commit()
    assert classify(db, "delete_task", {}) == "confirm"
    assert classify(db, "create_task", {}) == "confirm"


def test_unknown_tool_denied(db):
    assert classify(db, "not_a_tool", {}) == "deny"


# MCP 工具的永久授权规则。

class _FakeServer:
    """classify 只读 auto_approve_readonly，分类级测试用哑对象即可。"""

    def __init__(self, auto_approve_readonly=False):
        self.auto_approve_readonly = auto_approve_readonly


def _mcp_classify(db, tool_name, args, *, server=None):
    return classify(db, tool_name, args,
                    readonly_hint=True, mcp_server=server or _FakeServer())


def test_mcp_grant_allows_in_standard(db):
    """standard 档：用户点过「始终允许」的 MCP 工具（grant 落命名空间全名）免审。"""
    from zhishi.domain.models import AIToolGrant
    db.add(AIToolGrant(tool_name="mcp__s1__add", arg_pattern="")); db.commit()
    assert _mcp_classify(db, "mcp__s1__add", {"a": 1, "b": 2}) == "allow"


def test_mcp_grant_pattern_mismatch_confirms(db):
    """arg_pattern 子集匹配语义与内置工具一致：参数不匹配仍走审批。"""
    from zhishi.domain.models import AIToolGrant
    db.add(AIToolGrant(tool_name="mcp__s1__del", arg_pattern='{"path": "a.txt"}')); db.commit()
    assert _mcp_classify(db, "mcp__s1__del", {"path": "a.txt"}) == "allow"
    assert _mcp_classify(db, "mcp__s1__del", {"path": "b.txt"}) == "confirm"


def test_mcp_grant_ignored_in_careful(db):
    """careful 档 grants 一律不生效（与内置工具语义边界一致）。"""
    from zhishi.domain.models import AIToolGrant
    from zhishi.domain import settingsvc
    settingsvc.set_setting(db, "agent_autonomy", "careful"); db.commit()
    db.add(AIToolGrant(tool_name="mcp__s1__add", arg_pattern="")); db.commit()
    assert _mcp_classify(db, "mcp__s1__add", {"a": 1, "b": 2}) == "confirm"


# ---- MCP grant 生命周期：按服务器撤销 ----

def test_revoke_mcp_grants_precise_server_id_match(db):
    """sid 是 sqlite rowid 可复用，撤销须按「__」切分第二段精确整数比对——
    撤 sid=1 时 sid=10/sid=11 的 grants 原样保留，非 mcp__ 命名空间的也不动。"""
    from sqlalchemy import select
    from zhishi.agent.permissions import revoke_mcp_grants
    from zhishi.domain.models import AIToolGrant
    db.add(AIToolGrant(tool_name="mcp__1__add", arg_pattern=""))
    db.add(AIToolGrant(tool_name="mcp__10__add", arg_pattern=""))
    db.add(AIToolGrant(tool_name="mcp__11__add", arg_pattern=""))
    db.add(AIToolGrant(tool_name="delete_task", arg_pattern=""))
    db.commit()

    n = revoke_mcp_grants(db, 1)
    db.commit()

    assert n == 1
    left = {r.tool_name for r in db.scalars(select(AIToolGrant)).all()}
    assert left == {"mcp__10__add", "mcp__11__add", "delete_task"}, (
        f"sid=1 撤销不得波及 sid=10/sid=11 与内置工具授权: {left}")


def test_revoke_mcp_grants_only_target_server(db):
    """撤 sid=10 只删自己的；撤销不存在的 sid 是无操作（返回 0）。"""
    from sqlalchemy import select
    from zhishi.agent.permissions import revoke_mcp_grants
    from zhishi.domain.models import AIToolGrant
    db.add(AIToolGrant(tool_name="mcp__10__add", arg_pattern="")); db.commit()

    assert revoke_mcp_grants(db, 10) == 1
    assert revoke_mcp_grants(db, 99) == 0
    db.commit()
    left = {r.tool_name for r in db.scalars(select(AIToolGrant)).all()}
    assert left == set()


# ---- 未消费 confirmed 审批卡同属「可执行效力」状态，PUT/DELETE 须一并作废 ----

@pytest.fixture
def conv_id(db):
    """审批卡外键依赖真实会话。"""
    from zhishi.domain.models import AIConversation
    conv = AIConversation(title="t")
    db.add(conv); db.commit(); db.refresh(conv)
    return conv.id


def _add_action(db, conv_id: int, run_id: str, tool_name: str, status: str,
                call_id: str) -> None:
    from zhishi.domain.models import AIPendingAction
    db.add(AIPendingAction(conversation_id=conv_id, run_id=run_id, tool_call_id=call_id,
                           tool_name=tool_name, args_json="{}", status=status))


def test_expire_mcp_actions_covers_unconsumed_confirmed(db, conv_id):
    """approve 只把 pending→confirmed，真正消费在 resume——confirmed 在
    此前仍有可执行效力，作废必须覆盖；executed/rejected 是真终态不回改。"""
    from sqlalchemy import select
    from zhishi.agent.permissions import expire_mcp_pending_actions
    _add_action(db, conv_id, "r1", "mcp__1__del_file", "pending", "tc1")
    _add_action(db, conv_id, "r1", "mcp__1__del_file", "confirmed", "tc2")
    _add_action(db, conv_id, "r1", "mcp__1__del_file", "executed", "tc3")
    _add_action(db, conv_id, "r1", "mcp__1__del_file", "rejected", "tc4")
    db.commit()

    n = expire_mcp_pending_actions(db, 1)
    db.commit()

    from zhishi.domain.models import AIPendingAction
    assert n == 2, "仅 pending 与未消费 confirmed 作废"
    statuses = sorted(a.status for a in db.scalars(select(AIPendingAction)).all())
    assert statuses == ["executed", "expired", "expired", "rejected"], (
        f"executed/rejected 历史审计状态不得回改: {statuses}")
    for a in db.scalars(select(AIPendingAction)).all():
        if a.status == "expired":
            assert a.resolved_at is not None


def test_expire_mcp_actions_precise_server_id_match(db, conv_id):
    """作废按 sid 精确整数比对——撤 sid=1 时 sid=10/11 与内置工具卡不动。"""
    from sqlalchemy import select
    from zhishi.agent.permissions import expire_mcp_pending_actions
    _add_action(db, conv_id, "r1", "mcp__1__del_file", "confirmed", "tc1")
    _add_action(db, conv_id, "r1", "mcp__10__del_file", "confirmed", "tc2")
    _add_action(db, conv_id, "r1", "mcp__11__del_file", "pending", "tc3")
    _add_action(db, conv_id, "r1", "delete_task", "confirmed", "tc4")
    db.commit()

    assert expire_mcp_pending_actions(db, 1) == 1
    db.commit()
    from zhishi.domain.models import AIPendingAction
    left = {a.tool_call_id: a.status for a in db.scalars(select(AIPendingAction)).all()}
    assert left == {"tc1": "expired", "tc2": "confirmed",
                    "tc3": "pending", "tc4": "confirmed"}, f"误伤: {left}"
