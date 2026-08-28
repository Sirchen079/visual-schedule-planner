"""会话上下文压缩（conversation compaction）——阶段 B3。

长会话必然超窗：历史硬切会让模型「失忆」。本服务在每次发消息前检查未压缩消息数量，
超阈值时把最旧的一批连同旧摘要一起压成一段四段式摘要（用户目标 / 已办事项 / 关键偏好 / 未完成事项），
写回 AIConversation.meta.summary 并标记旧消息 compacted=True。
组装请求时 = [system + summary 注入] + 最近保留条原文。

降级：压缩失败（模型异常）不阻塞对话，回退到现有按轮截断行为。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import AIConversation, AIMessage
from app.services import ai_oneshot_service

logger = logging.getLogger("zhishi.ai.compaction")

# 触发阈值：未压缩消息 ≥ 此值时压缩。默认 30 条（约对应 15 轮对话）。
COMPACTION_THRESHOLD = 30
# 压缩后保留最新的原文消息数（其余压成摘要）。12 条 ≈ 6 轮近期上下文，够模型续接。
COMPACTION_KEEP_RECENT = 12
# 单条消息喂给摘要模型时的截断长度，防超长拖垮压缩调用。
PER_MESSAGE_CHAR_LIMIT = 400
# 摘要输出上限。
SUMMARY_CHAR_LIMIT = 500

_SUMMARY_SYSTEM = (
    "你是会话摘要助手。把下面这段较长的对话历史压缩成一份简洁的摘要，"
    "严格按四段输出，每段不超过 120 字：\n"
    "1. 用户目标：用户在这次对话里想达成的核心目标。\n"
    "2. 已办事项：已经确认完成 / 落地的关键动作。\n"
    "3. 关键偏好：用户表达过的稳定偏好或约束（时间、习惯、口径等）。\n"
    "4. 未完成事项：尚未完成、待跟进、被搁置的事项。\n"
    "只输出这四段，不要寒暄、不要复述原文。"
)


def _conversation_meta(conv: AIConversation) -> dict[str, Any]:
    """安全解析会话 meta（旧库可能无 meta 列或缺键）。"""
    raw = getattr(conv, "meta", None) or "{}"
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _set_conversation_meta(db: Session, conv: AIConversation, meta: dict[str, Any]) -> None:
    conv.meta = json.dumps(meta, ensure_ascii=False)
    db.add(conv)


def _uncompacted_messages(history: list[AIMessage]) -> list[AIMessage]:
    """未压缩的 user/assistant 消息（按 id 升序）。compacted 列可能缺失（旧数据），按 False 处理。"""
    return [
        m for m in history
        if m.role in {"user", "assistant"}
        and not bool(getattr(m, "compacted", False))
        and (m.content or "").strip()
    ]


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def _build_summary_prompt(
    old_messages: list[AIMessage], previous_summary: str | None
) -> str:
    """把待压缩消息 + 旧摘要拼成喂给摘要模型的 user prompt。"""
    parts: list[str] = []
    if previous_summary:
        parts.append(f"【既有摘要】\n{previous_summary}")
    transcript_lines: list[str] = []
    for m in old_messages:
        role_label = "用户" if m.role == "user" else "助手"
        transcript_lines.append(f"{role_label}：{_truncate(m.content, PER_MESSAGE_CHAR_LIMIT)}")
    parts.append("【对话历史】\n" + "\n".join(transcript_lines))
    return "\n\n".join(parts)


def maybe_compact_sync(
    db: Session,
    conv: AIConversation,
    config,
    *,
    threshold: int = COMPACTION_THRESHOLD,
    keep_recent: int = COMPACTION_KEEP_RECENT,
) -> bool:
    """同步入口（供非异步调用方）：不触发压缩调用，仅返回是否需要压缩的标记。

    真正的压缩是 async（需调用 provider）。本函数保留供未来同步预判使用，当前返回 False。
    """
    return False


async def maybe_compact(
    db: Session,
    conv: AIConversation,
    config,
    *,
    threshold: int = COMPACTION_THRESHOLD,
    keep_recent: int = COMPACTION_KEEP_RECENT,
) -> bool:
    """若未压缩消息超阈值，触发压缩并落库。返回是否执行了压缩。

    失败（provider 异常 / 配置缺失）时不抛出：记录日志并返回 False，调用方回退到按轮截断。
    """
    if config is None:
        return False
    history = (
        db.query(AIMessage)
        .filter(AIMessage.conversation_id == conv.id)
        .order_by(AIMessage.id)
        .all()
    )
    uncompacted = _uncompacted_messages(history)
    if len(uncompacted) < max(threshold, keep_recent + 1):
        return False

    # 待压缩 = 全部未压缩 - 保留最近的 keep_recent 条
    to_compress = uncompacted[:-keep_recent] if keep_recent > 0 else uncompacted
    if not to_compress:
        return False
    # 压缩边界：最后一条被压缩消息的 id，写入 summary_upto_message_id
    boundary_id = to_compress[-1].id

    meta = _conversation_meta(conv)
    previous_summary = meta.get("summary") if isinstance(meta.get("summary"), str) else None

    prompt = _build_summary_prompt(to_compress, previous_summary)
    try:
        summary = await ai_oneshot_service.generate_text(
            db, config, _SUMMARY_SYSTEM, prompt, kind="compaction",
        )
    except Exception as exc:  # 压缩失败：降级，不阻塞对话
        logger.warning(
            "会话 %s 压缩失败，回退到按轮截断：%s", conv.id, exc, exc_info=False,
        )
        return False

    summary = _truncate(summary or "", SUMMARY_CHAR_LIMIT)
    if not summary:
        return False

    # 落库：写回 summary + 边界，标记已压缩消息
    meta["summary"] = summary
    meta["summary_upto_message_id"] = boundary_id
    _set_conversation_meta(db, conv, meta)
    for m in to_compress:
        m.compacted = True
        db.add(m)
    db.commit()
    logger.info(
        "会话 %s 已压缩 %d 条消息至摘要（边界 msg=%s）", conv.id, len(to_compress), boundary_id,
    )
    return True


def summary_for_replay(conv: AIConversation) -> str | None:
    """读取会话当前摘要，供 build_replay_messages 注入。无摘要返回 None。"""
    if conv is None:
        return None
    meta = _conversation_meta(conv)
    summary = meta.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    return None
