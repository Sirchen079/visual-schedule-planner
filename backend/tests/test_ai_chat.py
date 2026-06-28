import json
import pytest
from datetime import datetime, timedelta
from io import BytesIO

from app.models import AIConversation, AIMessage


def json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


@pytest.mark.anyio
async def test_ai_chat_executes_safe_tool(client, monkeypatch):
    from app.services import ai_client

    config = client.post(
        "/ai/configs",
        json={
            "name": "test",
            "provider": "openai_responses",
            "model": "fake-model",
            "api_key": "test-key",
        },
    ).json()
    client.post(f"/ai/configs/{config['id']}/enable")

    async def fake_call_provider(_request):
        return {
            "output_text": (
                '```json\n'
                '{"reply":"已创建任务","tools":[{"name":"create_task","args":{"title":"AI 安排任务"}}],"dangerous_actions":[]}'
                "\n```"
            )
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    resp = client.post("/ai/chat", json={"message": "帮我安排任务"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"].startswith("已创建任务")
    assert body["tool_results"][0]["result"]["ok"] is True
    tasks = client.get("/tasks").json()
    assert [task["title"] for task in tasks].count("AI 安排任务") == 1


@pytest.mark.anyio
async def test_ai_chat_passes_native_web_search_options_to_provider(client, monkeypatch):
    from app.services import ai_client

    config = client.post(
        "/ai/configs",
        json={
            "name": "search",
            "provider": "claude_messages",
            "model": "fake-model",
            "api_key": "test-key",
            "native_web_search_enabled": True,
            "native_web_search_options": {
                "tools": [
                    {
                        "type": "web_search_20250305",
                        "name": "web_search",
                        "max_uses": 2,
                    }
                ],
                "tool_choice": {"type": "auto"},
            },
        },
    ).json()
    client.post(f"/ai/configs/{config['id']}/enable")

    captured = {}

    async def fake_call_provider(request):
        captured["json"] = request.json
        return {
            "content": [
                {
                    "type": "text",
                    "text": '{"reply":"我会联网核对","tools":[],"dangerous_actions":[]}',
                }
            ]
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)

    resp = client.post("/ai/chat", json={"message": "查一下最新信息"})

    assert resp.status_code == 200
    assert captured["json"]["tools"][0]["name"] == "web_search"
    assert captured["json"]["tools"][0]["max_uses"] == 2
    assert captured["json"]["tool_choice"] == {"type": "auto"}
    assert "联网搜索规则" in captured["json"]["system"]


@pytest.mark.anyio
async def test_ai_chat_search_enhancement_forces_native_search_and_prompt(
    client, monkeypatch
):
    from app.services import ai_client

    config = client.post(
        "/ai/configs",
        json={
            "name": "search-enhanced",
            "provider": "claude_messages",
            "model": "fake-model",
            "api_key": "test-key",
            "native_web_search_enabled": False,
            "search_enhancement_enabled": True,
        },
    ).json()
    client.post(f"/ai/configs/{config['id']}/enable")

    captured = {}

    async def fake_call_provider(request):
        captured["json"] = request.json
        return {
            "content": [
                {
                    "type": "text",
                    "text": '{"reply":"已搜索并参考资料","tools":[],"dangerous_actions":[]}',
                }
            ]
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)

    resp = client.post("/ai/chat", json={"message": "帮我找最新论文并安排阅读"})

    assert resp.status_code == 200
    assert captured["json"]["tools"][0]["name"] == "web_search"
    assert "搜索增强" in captured["json"]["system"]
    assert "必须先使用模型原生联网搜索" in captured["json"]["system"]
    assert "至少列出 2 条可核对来源" in captured["json"]["system"]


@pytest.mark.anyio
async def test_ai_chat_retries_once_after_tool_failure(client, monkeypatch):
    from app.services import ai_client

    config = client.post(
        "/ai/configs",
        json={
            "name": "test",
            "provider": "openai_chat",
            "model": "fake-model",
            "api_key": "test-key",
        },
    ).json()
    client.post(f"/ai/configs/{config['id']}/enable")

    calls = []

    async def fake_call_provider(request):
        calls.append(request.json)
        if len(calls) == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"reply":"已设置提醒","tools":[{"name":"create_reminder","args":{"title":"读论文提醒"}}],"dangerous_actions":[]}'
                            )
                        }
                    }
                ]
            }
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"reply":"已改为创建待办任务","tools":[{"name":"create_task","args":{"title":"读论文提醒"}}],"dangerous_actions":[]}'
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)

    resp = client.post("/ai/chat", json={"message": "提醒我读论文"})

    assert resp.status_code == 200
    body = resp.json()
    assert len(calls) == 3
    retry_content = calls[1]["messages"][-1]["content"]
    assert "create_reminder" in retry_content
    assert "创建提醒需要 due_date" in retry_content
    assert body["reply"].startswith("已改为创建待办任务")
    assert [item["tool"] for item in body["tool_results"]] == [
        "create_reminder",
        "create_task",
        "create_task",
    ]
    assert body["tool_results"][0]["result"]["ok"] is False
    assert body["tool_results"][1]["result"]["ok"] is True
    assert body["tool_results"][2]["result"]["skipped"] is True


@pytest.mark.anyio
async def test_ai_chat_runs_multiple_agent_steps_with_observations(client, monkeypatch):
    from app.services import ai_client

    client.post("/tasks", json={"title": "已有论文任务"})
    config = client.post(
        "/ai/configs",
        json={
            "name": "agent",
            "provider": "openai_chat",
            "model": "fake-model",
            "api_key": "test-key",
        },
    ).json()
    client.post(f"/ai/configs/{config['id']}/enable")

    calls = []

    async def fake_call_provider(request):
        calls.append(request.json)
        if len(calls) == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"reply":"我先查看现有任务","tools":[{"name":"list_tasks","args":{}}],"dangerous_actions":[]}'
                            )
                        }
                    }
                ]
            }
        if len(calls) == 2:
            observation = request.json["messages"][-1]["content"]
            assert "工具执行结果" in observation
            assert "已有论文任务" in observation
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"reply":"我会创建补充任务","tools":[{"name":"create_task","args":{"title":"整理论文笔记","tags":["论文"]}}],"dangerous_actions":[]}'
                            )
                        }
                    }
                ]
            }
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"reply":"已查看任务并创建整理论文笔记。","tools":[],"dangerous_actions":[]}'
                    }
                }
            ]
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)

    resp = client.post("/ai/chat", json={"message": "看看现有任务，再帮我安排论文整理"})

    assert resp.status_code == 200
    body = resp.json()
    assert len(calls) == 3
    assert body["reply"] == "已查看任务并创建整理论文笔记。"
    assert [item["tool"] for item in body["tool_results"]] == ["list_tasks", "create_task"]
    tasks = client.get("/tasks").json()
    assert any(task["title"] == "整理论文笔记" for task in tasks)


@pytest.mark.anyio
async def test_ai_chat_does_not_execute_tools_when_dangerous_action_is_present(
    client, monkeypatch
):
    from app.services import ai_client

    task_id = client.post("/tasks", json={"title": "已有任务"}).json()["id"]
    config = client.post(
        "/ai/configs",
        json={
            "name": "agent-safety",
            "provider": "openai_chat",
            "model": "fake-model",
            "api_key": "test-key",
        },
    ).json()
    client.post(f"/ai/configs/{config['id']}/enable")

    async def fake_call_provider(_request):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"reply":"需要确认删除","tools":[{"name":"create_task","args":{"title":"不应创建"}}],'
                            '"dangerous_actions":[{"action_type":"delete_task","payload":{"task_id":'
                            + str(task_id)
                            + '},"summary":"删除已有任务"}]}'
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)

    resp = client.post("/ai/chat", json={"message": "删除旧任务并创建新任务"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["pending_actions"][0]["action_type"] == "delete_task"
    assert body["tool_results"] == []
    assert all(task["title"] != "不应创建" for task in client.get("/tasks").json())


@pytest.mark.anyio
async def test_ai_chat_recovers_from_malformed_tool_call(client, monkeypatch):
    from app.services import ai_client

    config = client.post(
        "/ai/configs",
        json={
            "name": "agent-malformed",
            "provider": "openai_chat",
            "model": "fake-model",
            "api_key": "test-key",
        },
    ).json()
    client.post(f"/ai/configs/{config['id']}/enable")
    calls = []

    async def fake_call_provider(request):
        calls.append(request.json)
        if len(calls) == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"reply":"先查任务","tools":["list_tasks"],"dangerous_actions":[]}'
                        }
                    }
                ]
            }
        assert "工具调用必须是对象" in calls[1]["messages"][-1]["content"]
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"reply":"已修正并创建任务","tools":[{"name":"create_task","args":{"title":"畸形调用修正后任务"}}],"dangerous_actions":[]}'
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)

    resp = client.post("/ai/chat", json={"message": "先查看再创建"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["tool_results"][0]["result"]["ok"] is False
    assert body["tool_results"][0]["result"]["error"] == "工具调用必须是对象"
    assert any(task["title"] == "畸形调用修正后任务" for task in client.get("/tasks").json())


@pytest.mark.anyio
async def test_ai_chat_limits_repeated_agent_work_and_skips_duplicate_success(
    client, monkeypatch
):
    from app.services import ai_client

    config = client.post(
        "/ai/configs",
        json={
            "name": "agent-limit",
            "provider": "openai_chat",
            "model": "fake-model",
            "api_key": "test-key",
        },
    ).json()
    client.post(f"/ai/configs/{config['id']}/enable")

    calls = []

    async def fake_call_provider(request):
        calls.append(request.json)
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"reply":"继续执行","tools":[{"name":"create_task","args":{"title":"只应创建一次"}}],"dangerous_actions":[]}'
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)

    resp = client.post("/ai/chat", json={"message": "连续工作但不要重复创建"})

    assert resp.status_code == 200
    body = resp.json()
    assert len(calls) == 2
    assert "重复工具调用" not in body["reply"]
    assert [task["title"] for task in client.get("/tasks").json()].count("只应创建一次") == 1
    assert body["tool_results"][0]["result"]["ok"] is True
    assert any(item["result"].get("skipped") is True for item in body["tool_results"][1:])


@pytest.mark.anyio
async def test_ai_chat_sends_full_attachment_only_on_first_agent_step(
    client, monkeypatch
):
    from app.services import ai_client

    config = client.post(
        "/ai/configs",
        json={
            "name": "agent-attachment",
            "provider": "openai_chat",
            "model": "fake-model",
            "api_key": "test-key",
        },
    ).json()
    client.post(f"/ai/configs/{config['id']}/enable")
    uploaded = client.post(
        "/ai/attachments",
        files={"file": ("paper.txt", BytesIO("论文结论：需要三天阅读计划".encode("utf-8")), "text/plain")},
    )
    assert uploaded.status_code == 201
    calls = []

    async def fake_call_provider(request):
        calls.append(request.json)
        if len(calls) == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"reply":"先查看任务","tools":[{"name":"list_tasks","args":{}}],"dangerous_actions":[]}'
                        }
                    }
                ]
            }
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"reply":"已基于附件完成规划","tools":[],"dangerous_actions":[]}'
                    }
                }
            ]
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)

    resp = client.post(
        "/ai/chat",
        json={"message": "根据附件规划", "attachments": [{"id": uploaded.json()["id"]}]},
    )

    assert resp.status_code == 200
    assert len(calls) == 2
    assert "三天阅读计划" in json_text(calls[0])
    assert "paper.txt" in json_text(calls[1])
    assert "三天阅读计划" not in json_text(calls[1])


@pytest.mark.anyio
async def test_ai_chat_creates_pending_action_for_dangerous_request(
    client, monkeypatch
):
    from app.services import ai_client

    task_id = client.post("/tasks", json={"title": "需要确认删除"}).json()["id"]
    config = client.post(
        "/ai/configs",
        json={
            "name": "test",
            "provider": "openai_chat",
            "model": "fake-model",
            "api_key": "test-key",
        },
    ).json()
    client.post(f"/ai/configs/{config['id']}/enable")

    async def fake_call_provider(_request):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '```json\n'
                            '{"reply":"需要你确认删除","tools":[],"dangerous_actions":[{"action_type":"delete_task","payload":{"task_id":'
                            + str(task_id)
                            + '},"summary":"删除任务：需要确认删除"}]}'
                            "\n```"
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    resp = client.post("/ai/chat", json={"message": "删除这个任务"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["pending_actions"][0]["action_type"] == "delete_task"
    assert body["pending_actions"][0]["preview"] == [
        f"操作: 将任务移入回收站",
        f"任务: #{task_id} 需要确认删除",
    ]
    assert client.get(f"/tasks/{task_id}").status_code == 200


@pytest.mark.anyio
async def test_ai_chat_pending_action_preview_is_generated_from_payload(
    client, monkeypatch
):
    from app.services import ai_client

    first = client.post("/tasks", json={"title": "真实任务一"}).json()["id"]
    second = client.post("/tasks", json={"title": "真实任务二"}).json()["id"]
    config = client.post(
        "/ai/configs",
        json={
            "name": "test",
            "provider": "openai_chat",
            "model": "fake-model",
            "api_key": "test-key",
        },
    ).json()
    client.post(f"/ai/configs/{config['id']}/enable")

    async def fake_call_provider(_request):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '```json\n'
                            '{"reply":"需要确认","tools":[],"dangerous_actions":[{"action_type":"bulk_delete_tasks","payload":{"task_ids":['
                            + f"{first},{second}"
                            + ']},"summary":"只删除 1 个无关任务"}]}'
                            "\n```"
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    resp = client.post("/ai/chat", json={"message": "删除这些任务"})

    assert resp.status_code == 200
    action = resp.json()["pending_actions"][0]
    assert action["summary"] == "只删除 1 个无关任务"
    assert action["preview"] == [
        "操作: 批量将 2 个任务移入回收站",
        f"任务: #{first} 真实任务一",
        f"任务: #{second} 真实任务二",
    ]


@pytest.mark.anyio
async def test_ai_chat_ignores_unsupported_dangerous_action(
    client, monkeypatch
):
    from app.services import ai_client

    config = client.post(
        "/ai/configs",
        json={
            "name": "test",
            "provider": "openai_chat",
            "model": "fake-model",
            "api_key": "test-key",
        },
    ).json()
    client.post(f"/ai/configs/{config['id']}/enable")

    async def fake_call_provider(_request):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '```json\n'
                            '{"reply":"该操作无法执行","tools":[],"dangerous_actions":[{"action_type":"wipe_database","payload":{},"summary":"清空数据库"}]}'
                            "\n```"
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    resp = client.post("/ai/chat", json={"message": "清空数据库"})

    assert resp.status_code == 200
    assert resp.json()["pending_actions"] == []


@pytest.mark.anyio
async def test_ai_chat_uses_default_persona_separately_from_skill(
    client, monkeypatch
):
    from app.services import ai_client

    config = client.post(
        "/ai/configs",
        json={
            "name": "test",
            "provider": "openai_chat",
            "model": "fake-model",
            "api_key": "test-key",
        },
    ).json()
    client.post(f"/ai/configs/{config['id']}/enable")
    skill = client.post(
        "/ai/skills",
        json={
            "name": "阅读规划",
            "description": "工作规则",
            "content": "优先把阅读任务拆成 45 分钟块。",
        },
    ).json()
    client.post(f"/ai/skills/{skill['id']}/enable")

    captured = {}

    async def fake_call_provider(request):
        captured["system_prompt"] = request.json["messages"][0]["content"]
        return {"choices": [{"message": {"content": '{"reply":"好的","tools":[],"dangerous_actions":[]}'}}]}

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)

    resp = client.post("/ai/chat", json={"message": "帮我规划今天"})

    assert resp.status_code == 200
    prompt = captured["system_prompt"]
    assert "默认人设" in prompt
    assert "幕僚型参谋" in prompt
    assert "事实、约束、目标、时间窗口" in prompt
    assert "备选方案" in prompt
    assert "利弊和风险" in prompt
    assert "可执行任务" in prompt
    assert "用户自定义 skill：" in prompt
    assert "优先把阅读任务拆成 45 分钟块。" in prompt
    assert "当前时间状态" in prompt
    assert "当前本地日期" in prompt
    assert "当前提醒状态" in prompt
    assert "下周六" in prompt
    assert "create_reminder" in prompt


def test_ai_conversations_lists_recent_50(client, db_session):
    base = datetime(2026, 6, 28, 9, 0, 0)
    for index in range(55):
        conversation = AIConversation(
            title=f"会话 {index}",
            created_at=base + timedelta(minutes=index),
            updated_at=base + timedelta(minutes=index),
        )
        db_session.add(conversation)
        db_session.flush()
        db_session.add(
            AIMessage(
                conversation_id=conversation.id,
                role="user",
                content=f"消息 {index}",
                created_at=base + timedelta(minutes=index),
            )
        )
    db_session.commit()

    resp = client.get("/ai/conversations")

    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 50
    assert rows[0]["title"] == "会话 54"
    assert rows[-1]["title"] == "会话 5"
    assert rows[0]["last_message"] == "消息 54"


def test_ai_conversation_detail_restores_messages_and_tool_results(client, db_session):
    conversation = AIConversation(title="历史会话")
    db_session.add(conversation)
    db_session.flush()
    db_session.add(AIMessage(conversation_id=conversation.id, role="user", content="帮我建任务"))
    db_session.add(
        AIMessage(
            conversation_id=conversation.id,
            role="assistant",
            content="已创建任务",
            meta='{"tool_results":[{"tool":"create_task","result":{"ok":true}}],"pending_action_ids":[]}',
        )
    )
    db_session.commit()

    resp = client.get(f"/ai/conversations/{conversation.id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "历史会话"
    assert [message["role"] for message in body["messages"]] == ["user", "assistant"]
    assert body["messages"][1]["tool_results"][0]["tool"] == "create_task"


@pytest.mark.anyio
async def test_ai_chat_records_structured_agent_harness_summary(client, monkeypatch, db_session):
    from app.services import ai_client

    config = client.post(
        "/ai/configs",
        json={
            "name": "harness",
            "provider": "openai_chat",
            "model": "fake-model",
            "api_key": "test-key",
        },
    ).json()
    client.post(f"/ai/configs/{config['id']}/enable")

    async def fake_call_provider(_request):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"reply":"已完成安排","plan":{"goal":"安排论文阅读","steps":["创建任务"]},'
                            '"tools":[{"name":"create_task","args":{"title":"阅读论文","subtask_titles":["读摘要","整理方法"]}}],'
                            '"dangerous_actions":[],"done":true}'
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)

    resp = client.post("/ai/chat", json={"message": "帮我安排论文阅读"})

    assert resp.status_code == 200
    conversation_id = resp.json()["conversation_id"]
    assistant_message = (
        db_session.query(AIMessage)
        .filter(AIMessage.conversation_id == conversation_id, AIMessage.role == "assistant")
        .one()
    )
    meta = json.loads(assistant_message.meta)
    run = meta["agent_run"]
    assert run["objective"] == "帮我安排论文阅读"
    assert run["done_reason"] == "model_done"
    assert run["plan"]["goal"] == "安排论文阅读"
    assert run["steps"][0]["step"] == 1
    assert run["steps"][0]["tools"][0]["name"] == "create_task"
    assert run["steps"][0]["observations"][0]["ok"] is True


@pytest.mark.anyio
async def test_ai_chat_stops_after_repeated_failed_tool_reaches_harness_retry_budget(
    client, monkeypatch
):
    from app.services import ai_client

    config = client.post(
        "/ai/configs",
        json={
            "name": "harness-retry",
            "provider": "openai_chat",
            "model": "fake-model",
            "api_key": "test-key",
        },
    ).json()
    client.post(f"/ai/configs/{config['id']}/enable")
    calls = []

    async def fake_call_provider(request):
        calls.append(request.json)
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"reply":"继续尝试设置提醒","plan":{"goal":"设置提醒"},'
                            '"tools":[{"name":"create_reminder","args":{"title":"读论文提醒"}}],'
                            '"dangerous_actions":[],"done":false}'
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)

    resp = client.post("/ai/chat", json={"message": "提醒我读论文"})

    assert resp.status_code == 200
    body = resp.json()
    assert len(calls) == 3
    assert [item["tool"] for item in body["tool_results"]] == [
        "create_reminder",
        "create_reminder",
        "create_reminder",
    ]
    assert "重试预算" in body["reply"]
    assert "创建提醒需要 due_date" in body["reply"]
