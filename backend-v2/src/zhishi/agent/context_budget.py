"""Conservative, provider-independent context budgeting.

Loader: ``window_to_budget(history, history_budget(config))``.
Runtime: append ``context_budget_hooks(config)`` to ``Agent(capabilities=...)``
after capabilities that alter requests. Unlike ProcessHistory, the request hook
sees prepared instructions, tool schemas, output schemas and current tool results.
Unknown context windows deliberately disable budgeting for legacy configurations.

These are estimates, not provider token counts: text uses UTF-8 byte length (a
conservative bound for common byte-based tokenizers), plus framing overhead.
Multimodal floors are deliberately expensive; decoded media/provider accounting
can still differ, especially for remote URLs, compressed documents and video.
"""
from __future__ import annotations

import struct
import wave
from dataclasses import fields, is_dataclass, replace
from io import BytesIO
from math import ceil
from types import SimpleNamespace
from typing import Any

from pydantic_ai.messages import (
    BinaryContent,
    FileUrl,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)


class ContextBudgetExceeded(ValueError):
    """Required context cannot fit without discarding the newest user round."""

    def __init__(self, estimated_tokens: int, budget: int, reason: str = "newest round"):
        self.estimated_tokens = estimated_tokens
        self.budget = budget
        self.reason = reason
        super().__init__(
            f"上下文超限：{reason} 估算需要 {estimated_tokens} tokens，可用 {budget} tokens；"
            "请缩短本轮输入/附件或工具结果，或选择上下文窗口更大的模型。"
        )


def _positive_int(value) -> int | None:
    return value if type(value) is int and value > 0 else None


def output_reserve(config) -> int:
    """Configured output allowance, else min(4096, one quarter of the window)."""
    explicit = _positive_int(getattr(config, "max_output_tokens", None))
    window = _positive_int(getattr(config, "context_window", None))
    return explicit or (min(4096, max(1, window // 4)) if window else 4096)


def history_budget(config, extra_tokens: int = 0) -> int | None:
    """Input allowance after output, 5% safety (at least 64), and request extras.

    ``extra_tokens`` accounts for instructions/tools not already in messages.
    None means unknown capacity; zero means no input capacity, never unlimited.
    """
    if type(extra_tokens) is not int or extra_tokens < 0:
        raise ValueError("extra_tokens must be a nonnegative integer")
    window = _positive_int(getattr(config, "context_window", None))
    if window is None:
        return None
    return max(0, window - output_reserve(config) - max(64, ceil(window * .05)) - extra_tokens)


def estimate_text_tokens(text: str) -> int:
    """No chars/4 assumption: CJK, emoji and escaped/structured text cost bytes."""
    return len(text.encode("utf-8", errors="replace"))


def _media_floor(media_type: str) -> int:
    if media_type.startswith("image/"):
        return 16384
    if media_type.startswith(("audio/", "video/")):
        return 65536
    return 32768


def _image_dimensions(data: bytes) -> tuple[int, int] | None:
    """Read common raster headers without decoding pixels or importing Pillow.

    Header-only parsing also handles extreme pixel dimensions without allocating
    an image or having a decoder's decompression-bomb guard hide its dimensions.
    """
    try:
        if data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR":
            return struct.unpack_from(">II", data, 16)
        if data.startswith((b"GIF87a", b"GIF89a")):
            return struct.unpack_from("<HH", data, 6)
        if data.startswith(b"BM"):
            width, height = struct.unpack_from("<ii", data, 18)
            return abs(width), abs(height)
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            if data[12:16] == b"VP8X" and len(data) >= 30:
                return (1 + int.from_bytes(data[24:27], "little"),
                        1 + int.from_bytes(data[27:30], "little"))
            if data[12:16] == b"VP8L" and len(data) >= 25 and data[20] == 0x2f:
                bits = int.from_bytes(data[21:25], "little")
                return (bits & 0x3fff) + 1, ((bits >> 14) & 0x3fff) + 1
            if data[12:16] == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
                width, height = struct.unpack_from("<HH", data, 26)
                return width & 0x3fff, height & 0x3fff
        if data.startswith(b"\xff\xd8"):
            offset = 2
            while offset + 4 <= len(data):
                if data[offset] != 0xff:
                    break
                while offset < len(data) and data[offset] == 0xff:
                    offset += 1
                marker = data[offset]
                offset += 1
                if marker in (0xd9, 0xda):
                    break
                if marker == 0x01 or 0xd0 <= marker <= 0xd8:
                    continue
                size = int.from_bytes(data[offset:offset + 2], "big")
                if size < 2:
                    break
                if marker in (0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7,
                              0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf):
                    height, width = struct.unpack_from(">HH", data, offset + 3)
                    return width, height
                offset += size
    except (IndexError, struct.error):
        pass
    return None


def _binary_tokens(value: BinaryContent) -> int:
    if value.media_type.startswith("image/"):
        dimensions = _image_dimensions(value.data)
        if dimensions and all(n > 0 for n in dimensions):
            width, height = dimensions
            return 1024 + 1024 * ceil(width / 512) * ceil(height / 512)
        return 16384
    if value.media_type.startswith("audio/"):
        # Native audio is not base64 text. WAV permits an exact duration without
        # decoding samples. Other codecs reserve 64k; this is not a duration cap.
        try:
            with wave.open(BytesIO(value.data), "rb") as audio:
                duration = audio.getnframes() / audio.getframerate()
            return 1024 + ceil(duration * 100)
        except (wave.Error, EOFError, ZeroDivisionError):
            return 65536
    if value.media_type.startswith("video/"):
        return 65536
    return _media_floor(value.media_type) + ceil(len(value.data) * 4 / 3)


def estimate_value_tokens(value: Any) -> int:
    """Estimate nested content/schemas without repr-ing binary payloads."""
    if value is None:
        return 0
    if isinstance(value, str):
        return estimate_text_tokens(value)
    if isinstance(value, BinaryContent):
        return _binary_tokens(value)
    if isinstance(value, FileUrl):
        return _media_floor(value.media_type) + estimate_text_tokens(value.url)
    if isinstance(value, bytes):
        return 32768 + ceil(len(value) * 4 / 3)
    if isinstance(value, dict):
        return 2 + sum(estimate_value_tokens(k) + estimate_value_tokens(v) + 4
                       for k, v in value.items())
    if isinstance(value, (list, tuple, set, frozenset)):
        return 2 + sum(estimate_value_tokens(v) + 2 for v in value)
    if is_dataclass(value):
        return 8 + sum(estimate_value_tokens(getattr(value, f.name)) + 4
                       for f in fields(value) if not f.name.startswith("_"))
    if hasattr(value, "model_dump"):
        return estimate_value_tokens(value.model_dump(mode="python"))
    return estimate_text_tokens(str(value)) + 4


def estimate_messages_tokens(messages: list) -> int:
    """Count message parts and the effective fallback instructions exactly once."""
    from pydantic_ai.models import Model, ModelRequestParameters
    instructions = Model._get_instruction_parts(messages, ModelRequestParameters())
    return sum(12 + sum(8 + estimate_value_tokens(p) for p in m.parts)
               for m in messages) + estimate_value_tokens(instructions)


def prepared_messages(messages: list, parameters) -> list:
    """Current prepared instructions supersede historical instruction metadata.

    OpenAI and Anthropic adapters use instruction_parts when present. The real
    SystemPromptParts remain untouched; only redundant replay metadata is cleared.
    """
    if getattr(parameters, 'instruction_parts', None) is None:
        return list(messages)
    return [replace(m, instructions=None) if isinstance(m, ModelRequest) else m for m in messages]


def safe_round_starts(messages: list) -> list[int]:
    """User boundaries that do not cross a tool call/result (including retries).

    A pending call pins its round until it is resolved. A mixed user/tool-return
    request belongs to the prior call's round for cutting purposes.
    """
    pending: set[str] = set()
    starts: list[int] = []
    for i, message in enumerate(messages):
        if (isinstance(message, ModelRequest) and not pending
                and any(isinstance(p, UserPromptPart) for p in message.parts)):
            starts.append(i)
        for part in message.parts:
            kind = getattr(part, "part_kind", "")
            if isinstance(part, ToolCallPart) or kind == "native-tool-call":
                pending.add(part.tool_call_id)
            elif (isinstance(part, ToolReturnPart) or kind == "native-tool-return"
                  or isinstance(part, RetryPromptPart) and part.tool_name):
                pending.discard(part.tool_call_id)
    return starts


def _with_system_prefix(messages: list, cut: int) -> list:
    """Pin system prompts that lived in a removed round, without mutating history."""
    parts = [p for m in messages[:cut] if isinstance(m, ModelRequest)
             for p in m.parts if isinstance(p, SystemPromptPart)]
    return ([ModelRequest(parts=parts)] if parts else []) + messages[cut:]


def _summary_span(messages: list) -> tuple[int, int]:
    # Only the exact synthetic, text-only two-message shape can move as a unit.
    from zhishi.agent.compaction import SUMMARY_PREFIX
    start = 0
    while (start < len(messages) and isinstance(messages[start], ModelRequest)
           and all(isinstance(p, SystemPromptPart) for p in messages[start].parts)):
        start += 1
    if (len(messages) >= start + 2 and isinstance(messages[start], ModelRequest)
            and len(messages[start].parts) == 1
            and isinstance(messages[start].parts[0], UserPromptPart)
            and isinstance(messages[start].parts[0].content, str)
            and messages[start].parts[0].content.startswith(SUMMARY_PREFIX)
            and isinstance(messages[start + 1], ModelResponse)
            and all(isinstance(p, TextPart) for p in messages[start + 1].parts)):
        return start, start + 2
    return 0, 0


def window_to_budget(messages: list, budget: int | None) -> list:
    """Keep a complete recent suffix, preferring a leading summary if it fits.

    No message/part is sliced. All user input in the newest round, current tool
    output and pending calls survive. Cross-round tool dependencies extend that
    indivisible suffix. Raise ContextBudgetExceeded when even this cannot fit.
    System prompts survive even when embedded in a discarded first user request.
    """
    if budget is None:
        return list(messages)
    if type(budget) is not int or budget < 0:
        raise ValueError("budget must be a nonnegative integer or None")
    if estimate_messages_tokens(messages) <= budget:
        return list(messages)
    starts = safe_round_starts(messages)
    newest = starts[-1] if starts else 0
    required = _with_system_prefix(messages, newest)
    cost = estimate_messages_tokens(required)
    if cost > budget:
        raise ContextBudgetExceeded(cost, budget, "newest round and required system prompts")
    summary_start, summary_end = _summary_span(messages)
    summary = messages[summary_start:summary_end] if summary_end and newest >= summary_end else []
    preserve_summary = bool(summary and estimate_messages_tokens([*summary, *required]) <= budget)
    selected = required
    # Suffix costs are monotonic except for tiny system framing differences; walk
    # all safe boundaries to retain as much complete recent history as possible.
    for cut in reversed(starts):
        if preserve_summary and cut < summary_end:
            continue
        candidate = _with_system_prefix(messages, cut)
        if preserve_summary:
            candidate = [*summary, *candidate]
        if estimate_messages_tokens(candidate) <= budget:
            selected = candidate
    return selected


def request_extra_tokens(parameters) -> int:
    """Prepared instructions + all tool/output schemas, including native tools."""
    return 32 + sum(estimate_value_tokens(getattr(parameters, name, None)) for name in (
        "instruction_parts", "function_tools", "output_tools", "native_tools",
        "output_object", "prompted_output_template",
    ))


def context_budget_hooks(config, *, allow_truncation: bool = True):
    """Return a pydantic-ai Hooks capability enforcing every outgoing request.

    Snapshot only limit values, so hooks do not lazy-load SQLAlchemy objects.
    Install last: ``Agent(..., capabilities=[..., context_budget_hooks(config)])``.
    Raises before network I/O on overflow, including tool-result/resume requests.
    """
    from pydantic_ai.capabilities import Hooks

    window = _positive_int(getattr(config, "context_window", None))
    configured_output = _positive_int(getattr(config, "max_output_tokens", None))

    def enforce(ctx, request_context):
        if window is None:
            return request_context
        # Model defaults are merged by prepare_request later in some adapters;
        # account for both defaults and the per-request override here.
        settings = {**(getattr(request_context.model, "settings", None) or {}),
                    **(request_context.model_settings or {})}
        reserve_config = SimpleNamespace(context_window=window, max_output_tokens=configured_output)
        settings["max_tokens"] = (_positive_int(settings.get("max_tokens"))
                                  or output_reserve(reserve_config))
        reserve_config.max_output_tokens = settings["max_tokens"]
        extras = request_extra_tokens(request_context.model_request_parameters)
        available = history_budget(reserve_config, extras)
        prepared = prepared_messages(request_context.messages, request_context.model_request_parameters)
        if not allow_truncation and estimate_messages_tokens(prepared) > available:
            raise ContextBudgetExceeded(estimate_messages_tokens(prepared), available,
                '历史尚未成功压缩，原会话记录已保留')
        messages = window_to_budget(prepared, available)
        return replace(request_context, messages=messages, model_settings=settings)

    return Hooks(before_model_request=enforce)
