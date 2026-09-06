"""会话上下文压缩与预算控制。

按完整轮次拆分历史，分块摘要并合并已有摘要。原始会话另行持久保存，
摘要失败时保留原历史；发起模型请求前执行上下文预算检查。
"""
from __future__ import annotations

import asyncio
import hashlib
import math
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from types import SimpleNamespace

from zhishi.agent.context_budget import (
    ContextBudgetExceeded,
    estimate_messages_tokens,
    estimate_text_tokens,
    history_budget,
    output_reserve,
    prepared_messages,
    request_extra_tokens,
    safe_round_starts,
    window_to_budget,
)
from zhishi.agent.providers import build_model, oneshot_text  # 测试 monkeypatch 锚点

DEFAULT_COMPACTION_THRESHOLD = 12
DEFAULT_COMPACTION_TIMEOUT = 20.0
SUMMARY_PREFIX = "【会话摘要】"
SUMMARY_CONFIRMATION = "已加载先前会话摘要。摘要可能省略细节；涉及原话、约束或已执行操作时，使用 read_conversation_history 查询本会话原始记录后再判断，不猜测或重复执行。"

SUMMARY_SYSTEM_PROMPT = (
    "你是会话摘要器，把给定的历史对话压缩为一份承接上下文用的结构化摘要。"
    "严格输出以下四段，每段以【】标题起行，该段无内容时写「无」，不要输出其他文字：\n"
    "【用户目标】用户在这段对话中想达成什么\n"
    "【已办事项】已完成或已确认的事项（保留关键结果与数字）\n"
    "【关键偏好】用户表达的偏好、约束与习惯\n"
    "【未完成事项】尚未完成、待跟进或被搁置的事项")

# 合并式压缩：旧摘要 + 新折叠段 → 新摘要，旧摘要中仍有效的事实必须保留
MERGE_INSTRUCTION = (
    "以下是先前会话摘要与本次需并入的对话轮次。请把两者合并为一份新的结构化摘要，"
    "保留旧摘要中仍然有效的事实，并融合新增轮次的关键信息。"
    "严格输出以下四段，每段以【】标题起行，该段无内容时写「无」，不要输出其他文字：\n"
    "【用户目标】用户在这段对话中想达成什么\n"
    "【已办事项】已完成或已确认的事项（保留关键结果与数字）\n"
    "【关键偏好】用户表达的偏好、约束与习惯\n"
    "【未完成事项】尚未完成、待跟进或被搁置的事项")


def _is_round_start(m: dict) -> bool:
    return m.get("role") == "user"


def window_history(messages: list[dict], keep: int = 12) -> list[dict]:
    """从最新往回保留 keep 个「轮」（user 起），在轮边界截断。"""
    if len(messages) <= keep:
        return list(messages)
    # 找倒数第 keep 个 user 的下标
    starts = [i for i, m in enumerate(messages) if _is_round_start(m)]
    if len(starts) <= keep:
        return list(messages)
    cut = starts[-keep]
    return messages[cut:]


def model_message_round_start(msg) -> bool:
    """ModelMessage 版的轮边界：ModelRequest 且含 UserPromptPart。"""
    from pydantic_ai.messages import ModelRequest, UserPromptPart
    return isinstance(msg, ModelRequest) and any(isinstance(p, UserPromptPart) for p in msg.parts)


def window_model_messages(messages: list, keep: int = 12) -> list:
    """喂回模型前的 history 截断（与 window_history 同语义，作用于 PydanticAI ModelMessage）。"""
    if len(messages) <= keep:
        return list(messages)
    starts = safe_round_starts(messages)
    if len(starts) <= keep:
        return list(messages)
    from pydantic_ai.messages import ModelRequest, SystemPromptPart
    cut = starts[-keep]
    system_parts = [p for m in messages[:cut] if isinstance(m, ModelRequest)
                    for p in m.parts if isinstance(p, SystemPromptPart)]
    return ([ModelRequest(parts=system_parts)] if system_parts else []) + messages[cut:]


# ---- 会话摘要压缩 ----

def compaction_threshold(db) -> int:
    """触发阈值（轮数）：settingsvc 可配 compaction_threshold，脏值/非正数回退默认 12。"""
    from zhishi.domain import settingsvc
    raw = settingsvc.get_setting(db, "compaction_threshold",
                                 str(DEFAULT_COMPACTION_THRESHOLD))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_COMPACTION_THRESHOLD
    return value if value > 0 else DEFAULT_COMPACTION_THRESHOLD


def compaction_timeout(db) -> float:
    """摘要模型调用超时（秒）：settingsvc 可配 compaction_timeout，
    脏值/非正数回退默认 20.0。"""
    from zhishi.domain import settingsvc
    raw = settingsvc.get_setting(db, "compaction_timeout", str(DEFAULT_COMPACTION_TIMEOUT))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_COMPACTION_TIMEOUT
    return value if math.isfinite(value) and value > 0 else DEFAULT_COMPACTION_TIMEOUT


def _round_starts(messages: list) -> list[int]:
    return safe_round_starts(messages)


def _render_content(content) -> str:
    """Never stringify binary bytes into the summary prompt."""
    from pydantic_ai.messages import BinaryContent, FileUrl
    if isinstance(content, BinaryContent):
        return f"[附件 {content.media_type}, {len(content.data)} bytes]"
    if isinstance(content, FileUrl):
        return f"[附件 {content.media_type}: {content.url}]"
    if isinstance(content, (list, tuple)):
        return "\n".join(_render_content(item) for item in content)
    if isinstance(content, dict):
        return "{" + ", ".join(f"{key}: {_render_content(value)}"
                               for key, value in content.items()) + "}"
    if isinstance(content, bytes):
        return f"[二进制附件 {len(content)} bytes]"
    return str(content)


def _render_messages(messages: list) -> str:
    """ModelMessage 轮次 → 摘要输入文本（工具调用/结果折叠为单行，逐条截断防爆量）。"""
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        ToolCallPart,
        ToolReturnPart,
        UserPromptPart,
    )
    lines: list[str] = []
    for m in messages:
        if isinstance(m, ModelRequest):
            for p in m.parts:
                if isinstance(p, UserPromptPart):
                    lines.append(f"用户: {_render_content(p.content)}")
                elif isinstance(p, ToolReturnPart):
                    lines.append(f"（工具 {p.tool_name} 结果: {_render_content(p.content)}）")
        elif isinstance(m, ModelResponse):
            for p in m.parts:
                if isinstance(p, TextPart) and p.content:
                    lines.append(f"助手: {str(p.content)}")
                elif isinstance(p, ToolCallPart):
                    lines.append(f"（助手调用工具 {p.tool_name}，参数 {str(p.args)}）")
    return "\n".join(lines)


def summary_pair(text: str) -> list:
    """摘要对：一条 user 消息（【会话摘要】前缀）+ assistant 确认占位。"""
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
    return [
        ModelRequest(parts=[UserPromptPart(content=f"{SUMMARY_PREFIX}{text}")]),
        ModelResponse(parts=[TextPart(content=SUMMARY_CONFIRMATION)]),
    ]


def _fold_fingerprint(messages: list) -> str:
    """被折叠进摘要的消息集指纹：对消息序列的规范化 JSON 取 sha256，
    同一原始历史的重放指纹一致，内容有增改则必然不同。"""
    from pydantic_ai.messages import ModelMessagesTypeAdapter
    raw = ModelMessagesTypeAdapter.dump_json(list(messages))
    return hashlib.sha256(raw).hexdigest()


def _oneshot_with_timeout(config, system: str, user: str, timeout: float) -> str:
    """带应用级超时的摘要模型调用：摘要接在请求路径且在取消机制
    覆盖之外，供应商挂起不能无限拖住对话。超时抛 TimeoutError，由调用方降级硬截断；
    守护线程晚到的结果直接丢弃（写入决策在超时返回之后，绝不补写旧摘要）。
    oneshot/build_model 不碰 db/Session，超时后无共享资源滞留。"""
    result: dict = {}

    def _run():
        try:
            result["text"] = oneshot_text(build_model(config), system, user)
        except BaseException as e:      # noqa: BLE001 —— 原样转交主线程判定
            result["error"] = e

    worker = threading.Thread(target=_run, daemon=True,
                              name="zhishi-compaction-oneshot")
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        raise TimeoutError(f"摘要模型调用超过 {timeout}s，保留原始历史")
    if "error" in result:
        raise result["error"]
    return result["text"]


def _bounded_text(text: str, budget: int) -> str:
    """Bound UTF-8 estimated tokens, visibly marking omissions without broken text."""
    if estimate_text_tokens(text) <= budget:
        return text
    marker = "\n[内容因上下文预算截短]"
    if budget < estimate_text_tokens(marker):
        return ""
    remaining = budget - estimate_text_tokens(marker)
    # Retain both ends: merge prompts place prior summary first and newer facts last.
    raw = text.encode("utf-8", errors="replace")
    head = remaining // 2
    tail = remaining - head
    return (raw[:head].decode("utf-8", errors="ignore") + marker
            + (raw[-tail:].decode("utf-8", errors="ignore") if tail else ""))


def _summary_config(config, max_tokens: int):
    """Plain snapshot; cap output without mutating a live SQLAlchemy config."""
    snapshot = SimpleNamespace(**{key: getattr(config, key, None) for key in (
        "api_key_ref", "name", "provider_kind", "base_url", "model", "context_window", "reasoning_effort",
    )})
    snapshot.max_output_tokens = max_tokens
    return snapshot


def _bounded_summary_user(config, system: str, user: str) -> str:
    from pydantic_ai.messages import ModelRequest, UserPromptPart
    # oneshot_text uses Agent(instructions=system); reserve instruction framing too.
    budget = history_budget(config, estimate_text_tokens(system) + 32)
    if budget is None:
        return user
    overhead = estimate_messages_tokens([ModelRequest(parts=[UserPromptPart(content="")])])
    if estimate_text_tokens(user) > max(0, budget - overhead):
        raise ValueError("摘要请求超出输入预算；原始历史保留")
    return user


def _summarize_complete(config, system: str, transcript: str, timeout: float) -> str:
    """Consume every text character in bounded chunks; commit only after all succeed."""
    from pydantic_ai.messages import ModelRequest, UserPromptPart
    deadline = time.monotonic() + timeout
    offset, summary = 0, ''
    output_limit = getattr(config, 'max_output_tokens', None)
    while offset < len(transcript):
        active_system = MERGE_INSTRUCTION if summary else system
        prefix = f'【先前片段摘要】\n{summary}\n\n【接下来的原始片段】\n' if summary else ''
        budget = history_budget(config, estimate_text_tokens(active_system) + 32)
        if budget is None:
            budget = 24000
        overhead = estimate_messages_tokens([ModelRequest(parts=[UserPromptPart(content='')])])
        room = budget - overhead - estimate_text_tokens(prefix)
        if room < 64:
            raise ValueError('摘要分段没有足够预算，原始历史保留')
        low, high = 0, len(transcript)-offset
        while low < high:
            middle = (low+high+1)//2
            if estimate_text_tokens(transcript[offset:offset+middle]) <= room:
                low = middle
            else:
                high = middle-1
        if low == 0 or time.monotonic() >= deadline:
            raise TimeoutError('摘要未能完整处理历史，原始记录保留')
        prompt = prefix + transcript[offset:offset+low]
        _bounded_summary_user(config, active_system, prompt)
        summary = _oneshot_with_timeout(config, active_system, prompt, deadline-time.monotonic())
        if not isinstance(summary,str) or not summary.strip():
            raise ValueError('摘要片段返回空内容，原始记录保留')
        if output_limit and estimate_text_tokens(summary) > output_limit:
            raise ValueError('摘要输出超过预算，原始记录保留')
        offset += low
    return summary


def summarize_history(db, config, history: list,
                      stored_summary: str | None = None,
                      stored_fingerprint: str | None = None, *,
                      threshold: int | None = None,
                      timeout: float | None = None,
                      extra_tokens: int = 0) -> tuple[list, str | None, str | None]:
    """超过轮数或 token 预算时，将较早的完整轮次压缩为有界摘要。

返回新历史、摘要文本和折叠集指纹。相同指纹可复用已有摘要；否则分块生成
并与旧摘要合并。超时或调用失败时保留原历史，由请求预算检查决定能否继续。
最新完整轮次本身超限时抛出 ContextBudgetExceeded，不静默丢弃用户输入。"""
    budget = history_budget(config, extra_tokens)
    # Validate the indivisible newest round before the best-effort summary block.
    # This error must reach the caller, never be mistaken for a model failure.
    if budget is not None:
        window_to_budget(history, budget)
    try:
        starts = _round_starts(history)
        threshold = compaction_threshold(db) if threshold is None else threshold
        over_tokens = budget is not None and estimate_messages_tokens(history) > budget
        if (len(starts) <= threshold and not over_tokens) or len(starts) < 2:
            return list(history), None, None
        # 通常折叠一半；旧长历史/调低阈值时须多折叠一些，为摘要轮预留一位。
        # 否则最终 window_model_messages 会裁掉刚生成的摘要和未摘要的中段。
        keep = max(DEFAULT_COMPACTION_THRESHOLD, threshold)
        fold_count = (max(len(starts) // 2, len(starts) - (keep - 1))
                      if len(starts) > threshold else 1)
        summary_limit = None
        if budget is not None:
            overhead = estimate_messages_tokens(summary_pair(""))
            desired = min(1024, output_reserve(config), max(64, budget // 4))
            # Keep at least the newest complete round, but fold more than half
            # when a few very long rounds require it.
            while (fold_count < len(starts) - 1
                   and estimate_messages_tokens(history[starts[fold_count]:])
                   + overhead + desired > budget):
                fold_count += 1
            room = budget - estimate_messages_tokens(history[starts[fold_count]:]) - overhead
            summary_limit = min(desired, room)
            if summary_limit < 64:
                return list(history), None, None
        old, kept = history[:starts[fold_count]], history[starts[fold_count]:]
        # Preserve system prompts in old rounds as required context, separately
        # from generated prose. Charge these before allocating summary output.
        from pydantic_ai.messages import ModelRequest, SystemPromptPart
        system_parts = [p for m in old if isinstance(m, ModelRequest)
                        for p in m.parts if isinstance(p, SystemPromptPart)]
        pinned = [ModelRequest(parts=system_parts)] if system_parts else []
        if summary_limit is not None:
            summary_limit -= estimate_messages_tokens(pinned)
            if summary_limit < 64:
                return list(history), None, None
        fingerprint = _fold_fingerprint(old)
        if stored_summary and stored_fingerprint == fingerprint:
            summary = stored_summary                    # 同一历史重放：指纹命中，直接复用
        else:
            transcript = _render_messages(old)
            if stored_summary:
                user = (f"【先前摘要】\n{stored_summary}\n\n"
                        f"【需并入的对话轮次】\n{transcript}")
                system = MERGE_INSTRUCTION
            else:
                user = f"请把以下对话轮次压缩为结构化摘要：\n\n{transcript}"
                system = SUMMARY_SYSTEM_PROMPT
            call_config = _summary_config(config, summary_limit) if summary_limit else config
            summary = _summarize_complete(call_config, system, user,
                                           compaction_timeout(db) if timeout is None else timeout)
        if not isinstance(summary, str) or not summary.strip():
            return list(history), None, None
        if summary_limit is not None:
            if estimate_text_tokens(summary) > summary_limit:
                return list(history), None, None
        result = [*pinned, *summary_pair(summary), *kept]
        if budget is not None and estimate_messages_tokens(result) > budget:
            return list(history), None, None
        return result, summary, fingerprint
    except ContextBudgetExceeded:
        raise
    except Exception:   # noqa: BLE001 — 摘要为尽力操作；预算超限已在上方单独抛出
        return list(history), None, None


def maybe_summarize(db, config, history: list) -> list:
    """超过阈值时压缩会话，失败或未触发时返回原始历史。"""
    new, _summary, _fp = summarize_history(db, config, history)
    return new


def request_compaction_hooks(
    config, *, threshold: int = DEFAULT_COMPACTION_THRESHOLD,
    timeout: float = DEFAULT_COMPACTION_TIMEOUT,
    stored_summary: str | None = None,
    stored_fingerprint: str | None = None,
    on_summary: Callable[[str, str], None] | None = None,
    on_compaction: Callable[[list, str, str], None] | None = None,
):
    """Summarize full outgoing requests before the final hard-budget capability.

    Install after media preparation and before ``context_budget_hooks(config)``.
    Only token pressure triggers this hook; the loader owns round-only triggers.
    Effective max_tokens, prepared instructions/tools, current input and current
    tool results all participate in the decision. Summary failures leave messages
    for the final budget hook, which preserves the newest round or raises overflow.

    Construct per conversation/run: summary state belongs to this hook instance.
    ``on_summary(summary, fingerprint)`` is synchronous and runs on the owner
    event-loop thread after the worker completes. It may persist conversation
    metadata; failures propagate. Cancellation while awaiting the worker skips
    both persistence and local state updates, even if a late summary arrives.
    The worker sees plain config values and messages, never an ORM entity/session.
    """
    from pydantic_ai.capabilities import Hooks

    snapshot = _summary_config(config, output_reserve(config))

    async def compact(ctx, request_context):
        nonlocal stored_summary, stored_fingerprint
        if history_budget(snapshot) is None:
            return request_context
        settings = {**(getattr(request_context.model, "settings", None) or {}),
                    **(request_context.model_settings or {})}
        effective_output = settings.get("max_tokens")
        if type(effective_output) is not int or effective_output <= 0:
            effective_output = output_reserve(snapshot)
        request_config = _summary_config(snapshot, effective_output)
        extras = request_extra_tokens(request_context.model_request_parameters)
        budget = history_budget(request_config, extra_tokens=extras)
        prepared = prepared_messages(request_context.messages, request_context.model_request_parameters)
        if estimate_messages_tokens(prepared) <= budget:
            return replace(request_context, messages=prepared)

        messages, summary, fingerprint = await asyncio.to_thread(
            summarize_history, None, request_config, prepared,
            stored_summary=stored_summary, stored_fingerprint=stored_fingerprint,
            threshold=threshold, timeout=timeout, extra_tokens=extras,
        )
        if summary is not None and fingerprint is not None:
            if on_compaction is not None:
                on_compaction(list(request_context.messages), summary, fingerprint)
            if on_summary is not None:
                on_summary(summary, fingerprint)
            stored_summary, stored_fingerprint = summary, fingerprint
        return replace(request_context, messages=messages)

    return Hooks(before_model_request=compact)
