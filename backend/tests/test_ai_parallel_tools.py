"""阶段 B4：安全工具并行执行辅助测试。

覆盖：
1. 全部只读工具 + 多个调用 → 并发执行（各自独立 Session），结果顺序与入参一致。
2. 含写类 safe 工具 → 退化为串行（保持请求 Session 写事务语义）。
3. 单个只读调用 → 串行（无并发收益）。
"""
import asyncio
import time

import pytest

from app.routers.ai import _dispatch_native_safe_calls
from app.services import tool_registry


def _call(name, args=None, cid=None):
    return {"name": name, "id": cid or f"c_{name}", "arguments": args or {}}


@pytest.mark.anyio
async def test_b4_parallel_readonly_preserves_order(client, db_session):
    """3 个只读工具并发执行，结果顺序与入参一致。"""
    calls = [_call("list_tasks"), _call("list_reminders"), _call("list_goals")]
    outcomes = await _dispatch_native_safe_calls(db_session, calls, set(), "summary")
    assert len(outcomes) == 3
    # 顺序与入参一致（协议要求 tool 消息按 assistant tool_calls 顺序）
    assert outcomes[0]["tool_result"]["tool"] == "list_tasks"
    assert outcomes[1]["tool_result"]["tool"] == "list_reminders"
    assert outcomes[2]["tool_result"]["tool"] == "list_goals"
    # 都成功执行
    for o in outcomes:
        assert o["tool_result"]["result"]["ok"] is True


@pytest.mark.anyio
async def test_b4_mixed_safety_falls_back_to_serial(client, db_session):
    """含写类 safe 工具（create_task）→ 退化为串行，用请求 Session。"""
    # 先造一个任务标题，create_task 是写类 safe（非 readonly）
    calls = [_call("list_tasks"), _call("create_task", {"title": "并行测试任务"})]
    assert "create_task" not in tool_registry.readonly_names()
    outcomes = await _dispatch_native_safe_calls(db_session, calls, set(), "summary")
    assert len(outcomes) == 2
    assert outcomes[0]["tool_result"]["tool"] == "list_tasks"
    assert outcomes[1]["tool_result"]["tool"] == "create_task"
    assert outcomes[1]["tool_result"]["result"]["ok"] is True


@pytest.mark.anyio
async def test_b4_single_call_runs_serially(client, db_session):
    """单个只读调用 → 串行路径。"""
    calls = [_call("list_habits")]
    outcomes = await _dispatch_native_safe_calls(db_session, calls, set(), "summary")
    assert len(outcomes) == 1
    assert outcomes[0]["tool_result"]["tool"] == "list_habits"
