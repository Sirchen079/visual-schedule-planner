"""阶段 C1：Plan Mode 测试。

覆盖：
1. plan 模式下 tools payload 只含只读工具 + propose_plan（写工具不可见）。
2. propose_plan 工具产出 plan_card，落库到消息 meta。
3. /ai/plan/{id}/approve：把 steps 作为新用户指令注入并切回 chat 模式执行。
4. /ai/plan/{id}/reject：标记 rejected，不执行。
"""
import json

import pytest

from app.models import AIConversation, AIMessage
from app.services import tool_registry


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


def test_c1_plan_mode_filters_out_write_tools():
    """plan 模式：_assemble_native_tools 只暴露只读 + propose_plan。"""
    from app.routers.ai import _assemble_native_tools
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        chat_tools = {t["name"] for t in _assemble_native_tools(db, mode="chat")}
        plan_tools = {t["name"] for t in _assemble_native_tools(db, mode="plan")}
        # plan 模式不含写工具
        assert "create_task" not in plan_tools
        assert "update_task" not in plan_tools
        assert "delete_task" not in plan_tools
        # plan 模式含 propose_plan + 只读工具
        assert "propose_plan" in plan_tools
        assert "list_tasks" in plan_tools
        # chat 模式含写工具（对照）
        assert "create_task" in chat_tools
    finally:
        db.close()


@pytest.mark.anyio
async def test_c1_propose_plan_produces_plan_card(client, db_session, monkeypatch):
    """plan 模式下 agent 调用 propose_plan → plan_card 落库到消息 meta。"""
    from app.services import ai_client

    _enable_native_config(client)
    call_count = {"n": 0}

    async def fake_call_provider(request):
        call_count["n"] += 1
        # 第一轮：调用 propose_plan 提交计划；第二轮：纯文本收尾
        if call_count["n"] == 1:
            return {
                "choices": [{
                    "message": {
                        "content": "这是我的计划",
                        "tool_calls": [{
                            "id": "c1",
                            "type": "function",
                            "function": {
                                "name": "propose_plan",
                                "arguments": json.dumps({
                                    "title": "本周排程优化",
                                    "steps": [
                                        {"action": "创建任务", "tool": "create_task", "args_preview": "写周报", "rationale": "周五前要交"},
                                    ],
                                    "affected_days": ["2026-07-25"],
                                }),
                            },
                        }],
                    },
                    "finish_reason": "tool_calls",
                }]
            }
        return {"choices": [{"message": {"content": "计划已提交，等待你审阅"}, "finish_reason": "stop"}]}

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    body = client.post("/ai/chat", json={"message": "帮我规划本周", "mode": "plan"}).json()
    msgs = client.get(f"/ai/conversations/{body['conversation_id']}").json()["messages"]
    assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
    found_plan = any(
        isinstance((m.get("meta") or {}).get("plan_card"), dict)
        for m in assistant_msgs
    )
    assert found_plan, "应在 assistant 消息 meta 中找到 plan_card"


@pytest.mark.anyio
async def test_c1_approve_plan_injects_instruction_and_runs(client, db_session, monkeypatch):
    """approve：把 steps 作为新用户指令注入，切回 chat 模式执行（create_task 被调用）。"""
    from app.services import ai_client

    _enable_native_config(client)
    # 先造一个带 plan_card 的 assistant 消息
    conv = AIConversation(title="plan")
    db_session.add(conv)
    db_session.commit()
    # 用户消息
    db_session.add(AIMessage(conversation_id=conv.id, role="user", content="帮我规划"))
    db_session.commit()
    plan_msg = AIMessage(
        conversation_id=conv.id,
        role="assistant",
        content="这是计划",
        meta=json.dumps({"plan_card": {
            "title": "测试计划",
            "status": "pending",
            "steps": [{"action": "创建任务", "tool": "create_task", "args_preview": "测试任务"}],
        }}),
    )
    db_session.add(plan_msg)
    db_session.commit()

    calls = []

    async def fake_call_provider(request):
        calls.append(request.json)
        # approve 注入的指令会触发 create_task
        return {
            "choices": [{
                "message": {
                    "content": "已按计划执行",
                    "tool_calls": [{
                        "id": "c1", "type": "function",
                        "function": {"name": "create_task", "arguments": json.dumps({"title": "approve 创建的任务"})},
                    }],
                },
                "finish_reason": "tool_calls",
            }]
        }

    # 第二轮：纯文本收尾
    original = fake_call_provider

    async def fake_call_provider_2(request):
        calls.append(request.json)
        if len(calls) == 1:
            return await original(request)
        return {"choices": [{"message": {"content": "计划已执行完毕"}, "finish_reason": "stop"}]}

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider_2)

    body = client.post(f"/ai/plan/{plan_msg.id}/approve", json={}).json()
    assert "已按计划执行" in body["reply"] or "计划已执行完毕" in body["reply"]
    # 任务应被创建
    tasks = client.get("/tasks").json()
    assert any(t["title"] == "approve 创建的任务" for t in tasks)
    # plan_card 状态变 approved
    msg = db_session.get(AIMessage, plan_msg.id)
    pc = json.loads(msg.meta).get("plan_card")
    assert pc["status"] == "approved"


def test_c1_reject_plan_marks_rejected(client, db_session):
    """reject：标记 rejected，不执行任何步骤。"""
    conv = AIConversation(title="plan2")
    db_session.add(conv)
    db_session.commit()
    db_session.add(AIMessage(conversation_id=conv.id, role="user", content="规划"))
    db_session.commit()
    plan_msg = AIMessage(
        conversation_id=conv.id,
        role="assistant",
        content="计划",
        meta=json.dumps({"plan_card": {"title": "t", "status": "pending", "steps": []}}),
    )
    db_session.add(plan_msg)
    db_session.commit()

    r = client.post(f"/ai/plan/{plan_msg.id}/reject", json={"reason": "不需要"}).json()
    assert r["ok"] is True
    assert r["status"] == "rejected"
    msg = db_session.get(AIMessage, plan_msg.id)
    pc = json.loads(msg.meta).get("plan_card")
    assert pc["status"] == "rejected"
    assert pc["reject_reason"] == "不需要"


def test_c1_approve_missing_plan_returns_404(client, db_session):
    """approve 不含 plan_card 的消息 → 404。"""
    _enable_native_config(client)
    conv = AIConversation(title="no plan")
    db_session.add(conv)
    db_session.commit()
    msg = AIMessage(conversation_id=conv.id, role="assistant", content="普通回复", meta="{}")
    db_session.add(msg)
    db_session.commit()
    r = client.post(f"/ai/plan/{msg.id}/approve", json={})
    assert r.status_code == 404


@pytest.mark.anyio
async def test_fu21_approve_stream_emits_sse_events(client, db_session, monkeypatch):
    """阶段 FU-2.1：approve 的流式链路产出 SSE 事件序列（meta → text_delta → done）。

    直接调用 _stream_agent_run（与既有 test_ai_stream_chat 同模式），验证事件词汇与 chat/stream 一致。
    HTTP 端点（/plan/{id}/approve/stream）用独立 SessionLocal，无法用内存库 fixture 测；
    其前置逻辑（_prepare_plan_approve_context）由 test_c1_approve_plan_injects_instruction_and_runs 覆盖。
    """
    from app.models import AIConfig
    from app.routers.ai import _prepare_plan_approve_context, _stream_agent_run
    from app.services import ai_client

    _enable_native_config(client)
    # 造 plan 消息（用 client 端点建会话，确保 config/conv 一致）
    conv = AIConversation(title="stream-approve")
    db_session.add(conv)
    db_session.commit()
    db_session.add(AIMessage(conversation_id=conv.id, role="user", content="规划"))
    db_session.commit()
    plan_msg = AIMessage(
        conversation_id=conv.id, role="assistant", content="计划",
        meta=json.dumps({"plan_card": {
            "title": "流式批准", "status": "pending",
            "steps": [{"action": "建任务", "tool": "create_task", "args_preview": "流式任务"}],
        }}),
    )
    db_session.add(plan_msg)
    db_session.commit()

    # 复用 approve 的前置逻辑（_prepare_plan_approve_context），验证它返回可用上下文
    config, conversation, user_text, messages = _prepare_plan_approve_context(
        db_session, plan_msg.id, None
    )
    assert config is not None
    assert user_text.startswith("请按以下已批准的计划执行")

    # plan 已被标记 approved
    msg = db_session.get(AIMessage, plan_msg.id)
    pc = json.loads(msg.meta).get("plan_card")
    assert pc["status"] == "approved"

    call_count = {"n": 0}

    def fake_stream_provider(request):
        call_count["n"] += 1
        return _async_iter([{"type": "turn", "raw": {"choices": [{"message": {"content": "开始执行"}, "finish_reason": "stop"}]}}])

    monkeypatch.setattr(ai_client, "stream_provider", fake_stream_provider)

    # 直接驱动 _stream_agent_run，收集事件帧
    events = []
    async for chunk in _stream_agent_run(
        db_session, config, conversation, user_text, messages, "测试助手", mode="chat",
    ):
        events.append(chunk)
    event_names = [e.split("\n")[0].replace("event: ", "") for e in events if e.startswith("event:")]
    assert "meta" in event_names
    assert "done" in event_names


def test_fu21_approve_rejects_duplicate_approve(client, db_session):
    """阶段 FU-2.1：已 approved 的计划重复 approve → 409。"""
    _enable_native_config(client)
    conv = AIConversation(title="dup")
    db_session.add(conv)
    db_session.commit()
    db_session.add(AIMessage(conversation_id=conv.id, role="user", content="规划"))
    db_session.commit()
    plan_msg = AIMessage(
        conversation_id=conv.id, role="assistant", content="计划",
        meta=json.dumps({"plan_card": {"title": "t", "status": "approved", "steps": []}}),
    )
    db_session.add(plan_msg)
    db_session.commit()
    r = client.post(f"/ai/plan/{plan_msg.id}/approve", json={})
    assert r.status_code == 409


async def _async_iter(items):
    """把同步列表包成异步迭代器（fake_stream_provider 用）。"""
    for item in items:
        yield item
