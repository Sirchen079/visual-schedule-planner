"""阶段 B3：会话上下文压缩（conversation compaction）测试。

覆盖：
1. 超阈值触发压缩 → 旧消息标记 compacted、摘要写入会话 meta、build_replay 不再回放旧消息。
2. 未达阈值不压缩。
3. 压缩失败（provider 异常）降级：不抛错、不标记 compacted、不写摘要。
"""
import json

import pytest

from app.models import AIConversation, AIMessage
from app.services import ai_compaction_service


def _seed_messages(db_session, conversation_id, count):
    """造 count 条 user/assistant 交替消息。"""
    for i in range(count):
        db_session.add(
            AIMessage(
                conversation_id=conversation_id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"消息 {i}：这是一段需要被压缩的较长的对话内容，用于测试摘要。",
            )
        )
    db_session.commit()


class _FakeConfig:
    provider = "openai_chat"
    model = "fake"
    api_key = "k"


@pytest.mark.anyio
async def test_b3_compaction_triggers_on_threshold(client, db_session, monkeypatch):
    """40 条历史 → 触发压缩：摘要写入、旧消息 compacted、最近 12 条保留原文。"""
    conv = AIConversation(title="长会话")
    db_session.add(conv)
    db_session.commit()
    _seed_messages(db_session, conv.id, 40)

    captured = {}

    async def fake_generate(db, config, system, user, *, kind):
        captured["system"] = system
        captured["user"] = user
        captured["kind"] = kind
        # 模型返回四段式摘要
        return "用户目标：测试压缩\n已办事项：无\n关键偏好：无\n未完成事项：压缩验证"

    monkeypatch.setattr(ai_compaction_service.ai_oneshot_service, "generate_text", fake_generate)

    db = db_session
    conv_fresh = db.get(AIConversation, conv.id)
    did = await ai_compaction_service.maybe_compact(db, conv_fresh, _FakeConfig(), threshold=30, keep_recent=12)
    assert did is True

    # 摘要写入会话 meta
    meta = json.loads(conv_fresh.meta or "{}")
    assert "测试压缩" in meta["summary"]
    assert meta["summary_upto_message_id"] > 0

    # 旧 28 条被标记 compacted，最近 12 条未标记
    msgs = db.query(AIMessage).filter(AIMessage.conversation_id == conv.id).order_by(AIMessage.id).all()
    compacted_count = sum(1 for m in msgs if getattr(m, "compacted", False))
    assert compacted_count == 28
    # 最后 12 条未被压缩
    for m in msgs[-12:]:
        assert getattr(m, "compacted", False) is False

    # summary_for_replay 返回摘要
    summary = ai_compaction_service.summary_for_replay(conv_fresh)
    assert "测试压缩" in summary


@pytest.mark.anyio
async def test_b3_no_compaction_below_threshold(client, db_session, monkeypatch):
    """20 条历史（< 阈值 30）→ 不触发压缩。"""
    conv = AIConversation(title="短会话")
    db_session.add(conv)
    db_session.commit()
    _seed_messages(db_session, conv.id, 20)

    called = {"n": 0}

    async def fake_generate(*args, **kwargs):
        called["n"] += 1
        return "不应被调用"

    monkeypatch.setattr(ai_compaction_service.ai_oneshot_service, "generate_text", fake_generate)

    db = db_session
    conv_fresh = db.get(AIConversation, conv.id)
    did = await ai_compaction_service.maybe_compact(db, conv_fresh, _FakeConfig(), threshold=30, keep_recent=12)
    assert did is False
    assert called["n"] == 0
    # 没有消息被标记 compacted
    msgs = db.query(AIMessage).filter(AIMessage.conversation_id == conv.id).all()
    assert all(not getattr(m, "compacted", False) for m in msgs)


@pytest.mark.anyio
async def test_b3_compaction_failure_degrades_gracefully(client, db_session, monkeypatch):
    """provider 异常 → 压缩降级：不抛错、不标记 compacted、不写摘要。"""
    conv = AIConversation(title="异常会话")
    db_session.add(conv)
    db_session.commit()
    _seed_messages(db_session, conv.id, 40)

    async def fake_generate(*args, **kwargs):
        raise RuntimeError("provider 挂了")

    monkeypatch.setattr(ai_compaction_service.ai_oneshot_service, "generate_text", fake_generate)

    db = db_session
    conv_fresh = db.get(AIConversation, conv.id)
    # 不应抛出
    did = await ai_compaction_service.maybe_compact(db, conv_fresh, _FakeConfig(), threshold=30, keep_recent=12)
    assert did is False
    # 没有任何消息被压缩
    msgs = db.query(AIMessage).filter(AIMessage.conversation_id == conv.id).all()
    assert all(not getattr(m, "compacted", False) for m in msgs)
    # meta 没有摘要
    assert ai_compaction_service.summary_for_replay(conv_fresh) is None


@pytest.mark.anyio
async def test_b3_compacted_messages_excluded_from_replay(client, db_session, monkeypatch):
    """端到端：压缩后 build_replay_messages 不再回放被压缩的旧消息，但含摘要注入。"""
    from app.routers.ai import build_replay_messages
    from app.services import ai_oneshot_service

    conv = AIConversation(title="回放会话")
    db_session.add(conv)
    db_session.commit()
    _seed_messages(db_session, conv.id, 40)

    async def fake_generate(db, config, system, user, *, kind):
        return "用户目标：压缩后回放\n已办事项：无\n关键偏好：无\n未完成事项：验证回放"

    monkeypatch.setattr(ai_oneshot_service, "generate_text", fake_generate)

    db = db_session
    conv_fresh = db.get(AIConversation, conv.id)
    await ai_compaction_service.maybe_compact(db, conv_fresh, _FakeConfig(), threshold=30, keep_recent=12)

    # 压缩后重放：旧 28 条不应出现在回放序列
    history = (
        db.query(AIMessage)
        .filter(AIMessage.conversation_id == conv.id)
        .order_by(AIMessage.id)
        .all()
    )
    replayed = build_replay_messages(history)
    replayed_text = " ".join(str(m.get("content", "")) for m in replayed)
    # 最近 12 条原文应在
    assert "消息 39" in replayed_text
    # 被压缩的旧消息（消息 0~11）不应在
    assert "消息 0：" not in replayed_text
    assert "消息 5：" not in replayed_text
