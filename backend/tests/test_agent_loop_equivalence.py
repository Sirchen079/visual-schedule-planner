"""阶段 FU-3.1：双循环等价性测试（合并的安全绳）。

用同一组 fixture（mock provider 的多轮响应序列）分别驱动
`_run_native_agent_loop`（非流式）与 `stream_native_agent_loop`（流式，消费事件流取 terminal 帧），
断言两者的 AgentRunResult 在关键不变量上一致：
1. 工具调用序列（名称 + 参数 + 顺序）
2. 最终文本、done_reason、stop_message
3. pending/dangerous 集合
4. usage 累计

合并后（FU-3.2）两条旧路径删除，本测试转为「事件流折叠结果 == 原非流式契约」的固化快照。
"""
import json

import pytest

from app.models import AIConfig
from app.routers.ai import _run_native_agent_loop, stream_native_agent_loop


def _enable_native_config(client, **overrides):
    payload = {
        "name": "native",
        "provider": "openai_chat",
        "model": "fake-model",
        "api_key": "test-key",
        "tool_calling_mode": "native",
    }
    payload.update(overrides)
    config = client.post("/ai/configs", json=payload).json()
    client.post(f"/ai/configs/{config['id']}/enable")
    return config


def _extract_tool_sequence(agent_run):
    """从 AgentRunResult 提取工具调用序列：[(tool, args), ...]，按执行顺序。"""
    return [(t.get("tool"), t.get("args")) for t in (agent_run.tool_results or [])]


def _norm_result(agent_run):
    """归一化 AgentRunResult 为可比较的字段集。"""
    return {
        "final_text": agent_run.final_text,
        "tool_seq": _extract_tool_sequence(agent_run),
        "done_reason": (agent_run.run_summary or {}).get("done_reason"),
        "reached_limit": agent_run.reached_limit,
        "stopped_for_repeat": agent_run.stopped_for_repeat,
        "has_resume_checkpoint": agent_run.resume_checkpoint is not None,
        "plan_card": agent_run.plan_card,
        "work_plan": agent_run.work_plan,
        "usage_total": (agent_run.usage or {}).get("total_tokens", 0),
        "usage_calls": (agent_run.usage or {}).get("calls", 0),
    }


async def _async_iter(items):
    """把同步列表包成异步生成器。"""
    for item in items:
        yield item


def _make_turn_openai(content, tool_calls=None, finish="stop"):
    """构造 openai_chat 格式的 turn payload。"""
    msg = {"content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {"choices": [{"message": msg, "finish_reason": finish}]}


def _tc(call_id, name, args):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


async def _run_both(config, db, messages, monkeypatch, turn_sequence):
    """用同一组 turn 序列分别跑非流式与流式，返回 (nonstream_result, stream_result)。

    turn_sequence: list[dict]，第 i 次调用返回第 i 个 turn（越界返回最后一个）。
    非流式用 call_provider（async），流式用 stream_provider（返回 async generator）。
    """
    from app.services import ai_client
    call_idx = {"n": 0}

    async def fake_call(req):
        i = min(call_idx["n"], len(turn_sequence) - 1)
        call_idx["n"] += 1
        return turn_sequence[i]

    monkeypatch.setattr(ai_client, "call_provider", fake_call)
    ns = await _run_native_agent_loop(db, config, messages, "test", conversation_id=None, mode="chat")
    call_idx["n"] = 0

    def fake_stream(req):
        i = min(call_idx["n"], len(turn_sequence) - 1)
        call_idx["n"] += 1
        return _async_iter([{"type": "turn", "raw": turn_sequence[i]}])

    monkeypatch.setattr(ai_client, "stream_provider", fake_stream)
    st = None
    async for frame in stream_native_agent_loop(
        db, config, messages, "test", conversation_id=None, mode="chat",
    ):
        if frame.get("event") == "terminal":
            st = (frame.get("data") or {}).get("agent_run")
    return ns, st


# ---- 场景 1：无工具直接答 ----


@pytest.mark.anyio
async def test_equiv_no_tool_direct_answer(client, db_session, monkeypatch):
    _enable_native_config(client)
    config = db_session.query(AIConfig).filter(AIConfig.enabled.is_(True)).first()
    messages = [{"role": "user", "content": "你好"}]
    turns = [_make_turn_openai("你好！")]
    ns, st = await _run_both(config, db_session, messages, monkeypatch, turns)
    assert _norm_result(ns) == _norm_result(st)


# ---- 场景 2：safe 工具链（调用 → 执行 → 收尾文本）----


@pytest.mark.anyio
async def test_equiv_safe_tool_chain(client, db_session, monkeypatch):
    _enable_native_config(client)
    config = db_session.query(AIConfig).filter(AIConfig.enabled.is_(True)).first()
    client.post("/tasks", json={"title": "等价任务"})
    messages = [{"role": "user", "content": "查看任务"}]
    turns = [
        _make_turn_openai("查一下", [_tc("c1", "list_tasks", {})], "tool_calls"),
        _make_turn_openai("已查看"),
    ]
    ns, st = await _run_both(config, db_session, messages, monkeypatch, turns)
    assert _extract_tool_sequence(ns) == _extract_tool_sequence(st)
    assert _norm_result(ns) == _norm_result(st)


# ---- 场景 3：同轮含 confirm 工具 → 整轮暂缓（pending_confirmation）----


@pytest.mark.anyio
async def test_equiv_confirm_tool_pauses_round(client, db_session, monkeypatch):
    _enable_native_config(client)
    config = db_session.query(AIConfig).filter(AIConfig.enabled.is_(True)).first()
    messages = [{"role": "user", "content": "删任务"}]
    turns = [_make_turn_openai("需要确认", [_tc("c1", "delete_task", {"task_id": 1})], "tool_calls")]
    ns, st = await _run_both(config, db_session, messages, monkeypatch, turns)
    ns_n, st_n = _norm_result(ns), _norm_result(st)
    assert ns_n["has_resume_checkpoint"] is True
    assert st_n["has_resume_checkpoint"] is True
    assert ns_n["done_reason"] == st_n["done_reason"] == "pending_confirmation"


# ---- 场景 4：max_tokens 截断回喂 ----


@pytest.mark.anyio
async def test_equiv_truncation_refeed(client, db_session, monkeypatch):
    _enable_native_config(client)
    config = db_session.query(AIConfig).filter(AIConfig.enabled.is_(True)).first()
    messages = [{"role": "user", "content": "继续"}]
    turns = [
        _make_turn_openai("截断了...", finish="length"),
        _make_turn_openai("已收尾"),
    ]
    ns, st = await _run_both(config, db_session, messages, monkeypatch, turns)
    ns_n, st_n = _norm_result(ns), _norm_result(st)
    assert ns_n["final_text"] == st_n["final_text"] == "已收尾"
    assert ns_n["usage_calls"] == st_n["usage_calls"] == 2


# ---- 场景 5：同签名失败超重试预算 ----


@pytest.mark.anyio
async def test_equiv_retry_budget_exhausted(client, db_session, monkeypatch):
    """连续多轮发同一个会失败的工具（重复签名），达到重试上限停止。

    list_subtasks(task_id=99999) 每次都 error（任务不存在）→ 同签名失败累积 → retry_budget_exhausted。
    """
    _enable_native_config(client)
    config = db_session.query(AIConfig).filter(AIConfig.enabled.is_(True)).first()
    messages = [{"role": "user", "content": "查不存在"}]
    # 重复发同一失败工具，直到撞预算（AGENT_TOOL_RETRY_LIMIT=2）
    turns = [
        _make_turn_openai("查", [_tc(f"c{i}", "list_subtasks", {"task_id": 99999})], "tool_calls")
        for i in range(1, 6)
    ]
    ns, st = await _run_both(config, db_session, messages, monkeypatch, turns)
    ns_n, st_n = _norm_result(ns), _norm_result(st)
    assert ns_n["done_reason"] == st_n["done_reason"]
    assert ns_n["done_reason"] == "retry_budget_exhausted"
