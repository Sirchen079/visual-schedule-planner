"""会话列表/详情查询测试。

阶段 7：plan 模式已硬删，原 plan e2e 用例（工具执行/重试/暂停不变量等）已由
test_ai_native_chat.py 的 native 等价用例覆盖；本文件仅保留与会话查询相关的用例。
"""
from datetime import datetime, timedelta

from app.models import AIConversation, AIMessage


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


def test_ai_conversation_detail_exposes_usage_and_reasoning_meta(client, db_session):
    conversation = AIConversation(title="用量会话")
    db_session.add(conversation)
    db_session.flush()
    db_session.add(
        AIMessage(
            conversation_id=conversation.id,
            role="assistant",
            content="已排好",
            meta=(
                '{"usage":{"prompt_tokens":40,"completion_tokens":2,"total_tokens":42},'
                '"elapsed_ms":1500,"reasoning":"先分析再排程","pending_action_ids":[]}'
            ),
        )
    )
    db_session.commit()

    resp = client.get(f"/ai/conversations/{conversation.id}")

    assert resp.status_code == 200
    msg = resp.json()["messages"][0]
    assert msg["meta"]["usage"]["total_tokens"] == 42
    assert msg["meta"]["elapsed_ms"] == 1500
    assert msg["meta"]["reasoning"] == "先分析再排程"
    assert "pending_action_ids" not in msg["meta"]  # 内部键不下发
