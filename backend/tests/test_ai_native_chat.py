"""原生 function-calling 路径（tool_calling_mode=native）端到端测试。

覆盖三家 provider 的 tool_call 解析/序列化、确认闸门、MCP 闸门、畸形参数熔断、
配置开关透传。复用 test_ai_chat 的 fake_call_provider monkeypatch 模式。
"""
import json

import pytest


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


# ---- 1. openai_chat：单轮 tool_call → 执行 → 第二轮纯文本 ----


@pytest.mark.anyio
async def test_native_openai_chat_tool_call_then_text(client, monkeypatch):
    from app.services import ai_client

    _enable_native_config(client)
    calls = []

    async def fake_call_provider(request):
        calls.append(request.json)
        if len(calls) == 1:
            assert "tools" in request.json  # payload 含 tools 数组
            return {
                "choices": [{
                    "message": {
                        "content": "我先建任务",
                        "tool_calls": [{
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "create_task", "arguments": '{"title":"原生任务"}'},
                        }],
                    },
                    "finish_reason": "tool_calls",
                }]
            }
        # 第二轮请求含 role:tool 消息
        roles = [m.get("role") for m in request.json["messages"]]
        assert "tool" in roles
        return {"choices": [{"message": {"content": "已创建原生任务"}, "finish_reason": "stop"}]}

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    body = client.post("/ai/chat", json={"message": "建个任务"}).json()

    assert body["reply"] == "已创建原生任务"
    assert body["tool_results"][0]["tool"] == "create_task"
    assert body["tool_results"][0]["result"]["ok"] is True
    tasks = client.get("/tasks").json()
    assert any(t["title"] == "原生任务" for t in tasks)


# ---- 2. claude_messages：tool_use/tool_result block + 连续结果合并 ----


@pytest.mark.anyio
async def test_native_claude_tool_use_and_result_blocks(client, monkeypatch):
    from app.services import ai_client

    _enable_native_config(client, provider="claude_messages")
    calls = []

    async def fake_call_provider(request):
        calls.append(request.json)
        if len(calls) == 1:
            return {
                "stop_reason": "tool_use",
                "content": [
                    {"type": "text", "text": "建两个任务"},
                    {"type": "tool_use", "id": "tu_1", "name": "create_task", "input": {"title": "C-A"}},
                    {"type": "tool_use", "id": "tu_2", "name": "create_task", "input": {"title": "C-B"}},
                ],
            }
        # 第二轮：assistant tool_use 之后紧跟 user(tool_result 合并)
        last = request.json["messages"][-1]
        assert last["role"] == "user"
        assert all(b["type"] == "tool_result" for b in last["content"])
        assert len(last["content"]) == 2
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "claude 完成"}]}

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    body = client.post("/ai/chat", json={"message": "建两个任务"}).json()

    assert body["reply"] == "claude 完成"
    titles = {t["title"] for t in client.get("/tasks").json()}
    assert {"C-A", "C-B"}.issubset(titles)


# ---- 3. openai_responses：function_call / function_call_output items ----


@pytest.mark.anyio
async def test_native_openai_responses_function_call_items(client, monkeypatch):
    from app.services import ai_client

    _enable_native_config(client, provider="openai_responses")
    calls = []

    async def fake_call_provider(request):
        calls.append(request.json)
        if len(calls) == 1:
            return {
                "output_text": "建任务",
                "output": [
                    {"type": "function_call", "call_id": "r1", "name": "create_task", "arguments": '{"title":"R 任务"}'},
                ],
            }
        items = request.json["input"]
        types = [i.get("type") for i in items]
        assert "function_call_output" in types
        return {"output_text": "responses 完成", "output": []}

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    body = client.post("/ai/chat", json={"message": "建任务"}).json()

    assert body["reply"] == "responses 完成"
    assert any(t["title"] == "R 任务" for t in client.get("/tasks").json())


# ---- 4. 确认闸门：delete_task tool_call 不执行，产生 pending action ----


@pytest.mark.anyio
async def test_native_confirm_gate_creates_pending_action(client, monkeypatch):
    from app.services import ai_client

    task_id = client.post("/tasks", json={"title": "待删除"}).json()["id"]
    _enable_native_config(client)

    async def fake_call_provider(_request):
        return {
            "choices": [{
                "message": {
                    "content": "需要删除这个任务",
                    "tool_calls": [{
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "delete_task", "arguments": json.dumps({"task_id": task_id})},
                    }],
                },
                "finish_reason": "tool_calls",
            }]
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    body = client.post("/ai/chat", json={"message": "删掉它"}).json()

    # 未实际删除
    assert client.get(f"/tasks/{task_id}").status_code == 200
    # 产生 pending action，形状不变
    assert len(body["pending_actions"]) == 1
    assert body["pending_actions"][0]["action_type"] == "delete_task"
    assert body["pending_actions"][0]["preview"][0] == "操作: 将任务移入回收站"
    # tool_result 标记 pending
    assert body["tool_results"][0]["result"]["pending"] is True
    assert body["tool_results"][0]["result"]["ok"] is False


# ---- 5. MCP 工具：auto_approved 直调 / 否则 mcp_tool_call pending ----


@pytest.mark.anyio
async def test_native_mcp_auto_approved_direct_call(client, monkeypatch):
    from app.services import ai_client, mcp_service

    _enable_native_config(client)
    # 注入一个 auto_approved MCP 工具
    monkeypatch.setattr(
        mcp_service, "list_enabled_tools_for_agent",
        lambda db: [{
            "server_id": 1, "server_name": "S", "auto_approve_readonly": True,
            "read_only": True, "name": "echo", "namespaced": "mcp__s1__echo",
            "description": "回声", "input_schema": {"type": "object", "properties": {}},
        }],
    )
    monkeypatch.setattr(mcp_service, "is_auto_approved", lambda db, sid, tn: True)
    monkeypatch.setattr(mcp_service, "call_tool", lambda db, sid, tn, args: {"ok": True, "text": "echo-result"})

    async def fake_call_provider(_request):
        return {
            "choices": [{
                "message": {
                    "content": "调用 mcp",
                    "tool_calls": [{
                        "id": "m1", "type": "function",
                        "function": {"name": "mcp__s1__echo", "arguments": "{}"},
                    }],
                },
                "finish_reason": "tool_calls",
            }]
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    body = client.post("/ai/chat", json={"message": "调 mcp"}).json()

    assert body["tool_results"][0]["tool"] == "mcp__s1__echo"
    assert body["tool_results"][0]["result"]["ok"] is True
    assert body["tool_results"][0]["result"]["text"] == "echo-result"
    assert body["pending_actions"] == []


@pytest.mark.anyio
async def test_native_mcp_non_approved_creates_pending(client, monkeypatch):
    from app.services import ai_client, mcp_service

    _enable_native_config(client)
    monkeypatch.setattr(
        mcp_service, "list_enabled_tools_for_agent",
        lambda db: [{
            "server_id": 2, "server_name": "S2", "auto_approve_readonly": False,
            "read_only": False, "name": "write", "namespaced": "mcp__s2__write",
            "description": "写操作", "input_schema": {"type": "object", "properties": {}},
        }],
    )
    monkeypatch.setattr(mcp_service, "is_auto_approved", lambda db, sid, tn: False)

    async def fake_call_provider(_request):
        return {
            "choices": [{
                "message": {
                    "content": "调用写工具",
                    "tool_calls": [{
                        "id": "m2", "type": "function",
                        "function": {"name": "mcp__s2__write", "arguments": '{"x":1}'},
                    }],
                },
                "finish_reason": "tool_calls",
            }]
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    body = client.post("/ai/chat", json={"message": "调写工具"}).json()

    assert body["pending_actions"][0]["action_type"] == "mcp_tool_call"
    assert body["tool_results"][0]["result"]["pending"] is True


# ---- 6. 畸形 arguments → 错误回喂 → 重试预算熔断 ----


@pytest.mark.anyio
async def test_native_malformed_arguments_exhausts_retry_budget(client, monkeypatch):
    from app.services import ai_client

    _enable_native_config(client)
    calls = []

    async def fake_call_provider(request):
        calls.append(request.json)
        return {
            "choices": [{
                "message": {
                    "content": "重试",
                    "tool_calls": [{
                        "id": "bad", "type": "function",
                        "function": {"name": "create_task", "arguments": "{not-json"},
                    }],
                },
                "finish_reason": "tool_calls",
            }]
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    body = client.post("/ai/chat", json={"message": "建任务"}).json()

    # 重试预算熔断：AGENT_TOOL_RETRY_LIMIT=2 → 3 次调用后停止
    assert len(calls) == 3
    assert "重试预算" in body["reply"]
    assert "解析失败" in body["reply"]
    # 未创建任务
    assert client.get("/tasks").json() == []


# ---- 6b. agent 自助创建 skill（确认闸门端到端）----


@pytest.mark.anyio
async def test_native_agent_creates_skill_via_confirm_gate(client, monkeypatch):
    from app.services import ai_client

    _enable_native_config(client)

    async def fake_call_provider(_request):
        return {
            "choices": [{
                "message": {
                    "content": "我帮你把阅读规则存成 skill",
                    "tool_calls": [{
                        "id": "s1", "type": "function",
                        "function": {
                            "name": "create_skill",
                            "arguments": json.dumps({
                                "name": "论文阅读",
                                "description": "阅读规划",
                                "content": "拆成 45 分钟块",
                                "enabled": True,
                            }),
                        },
                    }],
                },
                "finish_reason": "tool_calls",
            }]
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    body = client.post("/ai/chat", json={"message": "把这份阅读规则存成 skill"}).json()

    # 产生确认卡片，skill 尚未创建
    assert body["pending_actions"][0]["action_type"] == "create_skill"
    assert body["tool_results"][0]["result"]["pending"] is True
    from app.models import AISkill
    # 用户两段确认后创建
    action_id = body["pending_actions"][0]["id"]
    token = client.post(f"/ai/actions/{action_id}/confirm").json()["confirm_token"]
    exec_resp = client.post(f"/ai/actions/{action_id}/execute", json={"confirm_token": token})
    assert exec_resp.status_code == 200
    skills = client.get("/ai/skills").json()
    assert any(s["name"] == "论文阅读" for s in skills)


# ---- 6c. 同轮回含 confirm 工具时，safe 工具必须暂缓（与 plan 路径不变量一致）----


@pytest.mark.anyio
async def test_native_mixed_safe_and_confirm_same_turn_defers_safe(client, monkeypatch):
    from app.services import ai_client

    _enable_native_config(client)

    async def fake_call_provider(_request):
        return {
            "choices": [{
                "message": {
                    "content": "建一个再删另一个",
                    "tool_calls": [
                        {
                            "id": "a1",
                            "type": "function",
                            "function": {"name": "create_task", "arguments": '{"title":"不应该被创建"}'},
                        },
                        {
                            "id": "d1",
                            "type": "function",
                            "function": {"name": "delete_task", "arguments": json.dumps({"task_id": 999})},
                        },
                    ],
                },
                "finish_reason": "tool_calls",
            }]
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    body = client.post("/ai/chat", json={"message": "建一个删一个"}).json()

    # delete_task 进待确认
    assert body["pending_actions"][0]["action_type"] == "delete_task"
    # 同轮回的 safe 工具被暂缓，不应真正创建任务（避免用户拒确认时留下半成品副作用）
    titles = [t["title"] for t in client.get("/tasks").json()]
    assert "不应该被创建" not in titles
    # create_task 的 tool_result 标记 pending（暂缓执行）
    create_results = [r for r in body["tool_results"] if r["tool"] == "create_task"]
    assert create_results and create_results[0]["result"].get("pending") is True


# ---- 7. 配置开关透传 ----


def test_native_config_passthrough_tool_calling_mode(client):
    """阶段 7：tool_calling_mode 列保留但运行时忽略（恒走 native）。

    列值仍可读写（免迁移），但 agent 循环不再据此分流。
    """
    config = client.post(
        "/ai/configs",
        json={
            "name": "native-mode",
            "provider": "openai_chat",
            "model": "m",
            "api_key": "k",
            "tool_calling_mode": "native",
        },
    ).json()
    assert config["tool_calling_mode"] == "native"

    # 列值仍可更新（保留兼容），但运行时忽略
    updated = client.put(
        f"/ai/configs/{config['id']}",
        json={"tool_calling_mode": "native"},
    ).json()
    assert updated["tool_calling_mode"] == "native"


def test_native_config_defaults_to_native(client):
    config = client.post(
        "/ai/configs",
        json={"name": "d", "provider": "openai_chat", "model": "m", "api_key": "k"},
    ).json()
    assert config["tool_calling_mode"] == "native"


# ---- 8. 确认后回灌续跑（/ai/chat/resume）----


def _resume_tool_call(call_id, name, arguments):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


@pytest.mark.anyio
async def test_resume_after_confirm_reruns_paused_safe_tool(client, monkeypatch):
    """混合调用（create_task[safe] + delete_task[confirm]）暂停 → confirm delete → resume
    → 暂缓的 create_task 补执行 + 模型追加总结。"""
    from app.services import ai_client

    task_id = client.post("/tasks", json={"title": "待删除"}).json()["id"]
    _enable_native_config(client)
    call_count = {"n": 0}

    async def fake_call_provider(request):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # 首轮：safe(create_task) + confirm(delete_task) → 整轮暂缓
            return {
                "choices": [{
                    "message": {
                        "content": "先建一个再删另一个",
                        "tool_calls": [
                            _resume_tool_call("a1", "create_task", {"title": "续跑应创建"}),
                            _resume_tool_call("d1", "delete_task", {"task_id": task_id}),
                        ],
                    },
                    "finish_reason": "tool_calls",
                }]
            }
        # 续跑轮：messages 含 role:tool（含 create_task 补执行结果 + delete_task 已执行结果）
        roles = [m.get("role") for m in request.json["messages"]]
        assert "tool" in roles
        # 回归防护：不得出现连续两条 assistant 消息（checkpoint 消息已被剔除，由尾部重建）
        for i in range(1, len(roles)):
            assert not (roles[i] == "assistant" and roles[i - 1] == "assistant"), \
                "续跑上下文出现连续 assistant 消息（checkpoint 未剔除）"
        # 尾部应是 assistant(tool_calls) + 两条 tool 结果
        assert roles[-3:] == ["assistant", "tool", "tool"]
        return {"choices": [{"message": {"content": "已完成：建了任务并删除了指定任务"}, "finish_reason": "stop"}]}

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    body = client.post("/ai/chat", json={"message": "建一个删一个"}).json()
    assert body["pending_actions"] and body["pending_actions"][0]["action_type"] == "delete_task"
    # safe 被暂缓，任务未创建
    assert all(t["title"] != "续跑应创建" for t in client.get("/tasks").json())

    # confirm + execute delete
    action_id = body["pending_actions"][0]["id"]
    token = client.post(f"/ai/actions/{action_id}/confirm").json()["confirm_token"]
    assert client.post(f"/ai/actions/{action_id}/execute", json={"confirm_token": token}).status_code == 200

    # resume 续跑
    resume = client.post("/ai/chat/resume", json={"conversation_id": body["conversation_id"]}).json()
    assert resume["resumed"] is True
    assert "已完成" in resume["reply"]
    # 暂缓的 create_task 已补执行
    assert any(t["title"] == "续跑应创建" for t in client.get("/tasks").json())


@pytest.mark.anyio
async def test_resume_after_reject_feeds_rejection_to_model(client, monkeypatch):
    from app.services import ai_client

    task_id = client.post("/tasks", json={"title": "拒绝目标"}).json()["id"]
    _enable_native_config(client)
    call_count = {"n": 0}

    async def fake_call_provider(request):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {
                "choices": [{
                    "message": {
                        "content": "需要删除",
                        "tool_calls": [_resume_tool_call("d1", "delete_task", {"task_id": task_id})],
                    },
                    "finish_reason": "tool_calls",
                }]
            }
        # 续跑：tool 消息内容应含 rejected 标记
        tool_msgs = [m for m in request.json["messages"] if m.get("role") == "tool"]
        assert tool_msgs
        assert "拒绝" in tool_msgs[-1]["content"] or "rejected" in tool_msgs[-1]["content"]
        return {"choices": [{"message": {"content": "好的，已取消该操作"}, "finish_reason": "stop"}]}

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    body = client.post("/ai/chat", json={"message": "删掉它"}).json()
    action_id = body["pending_actions"][0]["id"]
    # reject
    assert client.post(f"/ai/actions/{action_id}/reject").status_code == 200

    resume = client.post("/ai/chat/resume", json={"conversation_id": body["conversation_id"]}).json()
    assert resume["resumed"] is True
    assert "取消" in resume["reply"]
    # 任务仍存在（拒绝 = 不执行）
    assert client.get(f"/tasks/{task_id}").status_code == 200


@pytest.mark.anyio
async def test_resume_returns_waiting_when_still_pending(client, monkeypatch):
    from app.services import ai_client

    task_id = client.post("/tasks", json={"title": "等待中"}).json()["id"]
    _enable_native_config(client)

    async def fake_call_provider(_request):
        return {
            "choices": [{
                "message": {
                    "content": "删",
                    "tool_calls": [_resume_tool_call("d1", "delete_task", {"task_id": task_id})],
                },
                "finish_reason": "tool_calls",
            }]
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    body = client.post("/ai/chat", json={"message": "删"}).json()
    # 仅 confirm（未 execute）→ 仍处于 confirmed，不应续跑
    action_id = body["pending_actions"][0]["id"]
    client.post(f"/ai/actions/{action_id}/confirm")

    resume = client.post("/ai/chat/resume", json={"conversation_id": body["conversation_id"]}).json()
    assert resume["resumed"] is False


@pytest.mark.anyio
async def test_resume_expired_action_feeds_error(client, db_session, monkeypatch):
    from app.services import ai_client
    from app.models import AIPendingAction
    from datetime import timedelta

    task_id = client.post("/tasks", json={"title": "过期目标"}).json()["id"]
    _enable_native_config(client)
    call_count = {"n": 0}

    async def fake_call_provider(request):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {
                "choices": [{
                    "message": {
                        "content": "删",
                        "tool_calls": [_resume_tool_call("d1", "delete_task", {"task_id": task_id})],
                    },
                    "finish_reason": "tool_calls",
                }]
            }
        tool_msgs = [m for m in request.json["messages"] if m.get("role") == "tool"]
        assert tool_msgs
        assert "过期" in tool_msgs[-1]["content"]
        return {"choices": [{"message": {"content": "操作已过期，未执行"}, "finish_reason": "stop"}]}

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    body = client.post("/ai/chat", json={"message": "删"}).json()
    action_id = body["pending_actions"][0]["id"]
    # 直接把 action 的 expires_at 收紧到过去，confirm 检测过期 → 置 expired
    action = db_session.get(AIPendingAction, action_id)
    action.expires_at = action.expires_at - timedelta(minutes=20)
    db_session.commit()
    client.post(f"/ai/actions/{action_id}/confirm")  # 触发 expired

    resume = client.post("/ai/chat/resume", json={"conversation_id": body["conversation_id"]}).json()
    assert resume["resumed"] is True
    assert "过期" in resume["reply"]


@pytest.mark.anyio
async def test_resume_idempotent_clears_checkpoint(client, monkeypatch):
    from app.services import ai_client
    from app.routers.ai import message_meta
    from app.models import AIMessage
    from sqlalchemy import select

    task_id = client.post("/tasks", json={"title": "幂等测试"}).json()["id"]
    _enable_native_config(client)
    call_count = {"n": 0}

    async def fake_call_provider(_request):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {
                "choices": [{
                    "message": {
                        "content": "删",
                        "tool_calls": [_resume_tool_call("d1", "delete_task", {"task_id": task_id})],
                    },
                    "finish_reason": "tool_calls",
                }]
            }
        return {"choices": [{"message": {"content": "续跑完成"}, "finish_reason": "stop"}]}

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    body = client.post("/ai/chat", json={"message": "删"}).json()
    conversation_id = body["conversation_id"]
    action_id = body["pending_actions"][0]["id"]
    token = client.post(f"/ai/actions/{action_id}/confirm").json()["confirm_token"]
    client.post(f"/ai/actions/{action_id}/execute", json={"confirm_token": token})

    # 第一次 resume：成功续跑
    r1 = client.post("/ai/chat/resume", json={"conversation_id": conversation_id}).json()
    assert r1["resumed"] is True

    # 原 checkpoint 消息的 meta.resume 应被清除
    msgs = client.get(f"/ai/conversations/{conversation_id}").json()["messages"]
    # 第二次 resume：无 checkpoint → resumed:false
    r2 = client.post("/ai/chat/resume", json={"conversation_id": conversation_id}).json()
    assert r2["resumed"] is False


# ---- 阶段 B2：步数预算可配置 + 优雅收尾 ----


@pytest.mark.anyio
async def test_b2_max_steps_request_override_caps_loop(client, monkeypatch):
    """请求体 max_steps 覆盖：模型持续发工具调用时，循环在 max_steps 处停止并标记 reached_limit。"""
    from app.services import ai_client

    _enable_native_config(client)
    call_count = {"n": 0}

    async def fake_call_provider(request):
        call_count["n"] += 1
        n = call_count["n"]
        # 每轮发不同的 safe 只读工具，永不主动收尾 → 必然撞 max_steps。
        # 用不同工具避免触发「重复成功跳过」→ no_progress 提前停止。
        tools_seq = ["list_tasks", "list_reminders", "list_files", "list_habits", "list_goals"]
        tool_name = tools_seq[(n - 1) % len(tools_seq)]
        return {
            "choices": [{
                "message": {
                    "content": "继续",
                    "tool_calls": [{
                        "id": f"call_{n}",
                        "type": "function",
                        "function": {"name": tool_name, "arguments": "{}"},
                        }],
                },
                "finish_reason": "tool_calls",
            }]
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    # max_steps=3：循环应执行恰好 3 轮 provider 调用后停止
    body = client.post("/ai/chat", json={"message": "查任务", "max_steps": 3}).json()
    assert call_count["n"] == 3
    assert "已达到连续工作轮次上限（3 轮）" in body["reply"]


@pytest.mark.anyio
async def test_b2_wrap_up_prompt_injected_at_penultimate_step(client, monkeypatch):
    """优雅收尾：到达预算倒数第 2 步时，向模型注入收尾提示（messages 中应出现该提示）。"""
    from app.services import ai_client

    _enable_native_config(client)
    seen_wrap_up = {"hit": False}
    step = {"n": 0}

    async def fake_call_provider(request):
        step["n"] += 1
        msgs = request.json.get("messages", [])
        # 检查是否注入了收尾提示（倒数第 2 步，即 step==budget-1 时注入并随该步请求发出）
        if any("你还剩 2 步工作预算" in (m.get("content") or "") for m in msgs):
            seen_wrap_up["hit"] = True
        # 前 3 轮发工具（用不同工具避免触发「重复成功跳过」），最后一轮收尾纯文本
        if step["n"] <= 3:
            tools_seq = ["list_tasks", "list_reminders", "list_files"]
            tool_name = tools_seq[step["n"] - 1]
            return {
                "choices": [{
                    "message": {
                        "content": "干活",
                        "tool_calls": [{
                            "id": f"c_{step['n']}", "type": "function",
                            "function": {"name": tool_name, "arguments": "{}"},
                        }],
                    },
                    "finish_reason": "tool_calls",
                }]
            }
        return {"choices": [{"message": {"content": "已完成全部工作"}, "finish_reason": "stop"}]}

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    # budget=5 → 倒数第 2 步 = step 4 时注入提示
    body = client.post("/ai/chat", json={"message": "干活", "max_steps": 5}).json()
    assert seen_wrap_up["hit"] is True
    assert body["reply"] == "已完成全部工作"


@pytest.mark.anyio
async def test_b2_max_steps_clamped_to_valid_range(client, monkeypatch):
    """max_steps 越界被夹到 [3,30]：传 1 → 实际至少 3 轮空间（不会立即在第 1 步撞墙）。"""
    from app.services import ai_client

    _enable_native_config(client)
    call_count = {"n": 0}

    async def fake_call_provider(request):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {
                "choices": [{
                    "message": {
                        "content": "查一下",
                        "tool_calls": [{
                            "id": "c1", "type": "function",
                            "function": {"name": "list_tasks", "arguments": "{}"},
                        }],
                    },
                    "finish_reason": "tool_calls",
                }]
            }
        return {"choices": [{"message": {"content": "好了"}, "finish_reason": "stop"}]}

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    # max_steps=1（越下界）→ 夹到 3，允许第 2 轮收尾
    body = client.post("/ai/chat", json={"message": "查", "max_steps": 1}).json()
    assert call_count["n"] == 2
    assert body["reply"] == "好了"
