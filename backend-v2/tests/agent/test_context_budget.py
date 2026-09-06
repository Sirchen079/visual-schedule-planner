"""Budget invariants and real pydantic-ai request-hook integration (no network)."""
from types import SimpleNamespace

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import (
    BinaryContent,
    ImageUrl,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import FunctionModel

from zhishi.agent.compaction import summary_pair
from zhishi.agent.context_budget import (
    ContextBudgetExceeded,
    context_budget_hooks,
    estimate_messages_tokens,
    estimate_text_tokens,
    history_budget,
    output_reserve,
    request_extra_tokens,
    safe_round_starts,
    window_to_budget,
)


def config(window=8192, output=512):
    return SimpleNamespace(context_window=window, max_output_tokens=output)


def test_prepared_instructions_do_not_accumulate_historical_copies():
    from pydantic_ai.messages import InstructionPart
    from pydantic_ai.models import ModelRequestParameters
    from zhishi.agent.context_budget import prepared_messages
    messages = [ModelRequest(parts=[UserPromptPart('hello')],instructions='OLD_INSTRUCTIONS'*1000)
                for _ in range(8)]
    params = ModelRequestParameters(instruction_parts=[InstructionPart(content='CURRENT')])
    prepared = prepared_messages(messages,params)
    assert estimate_messages_tokens(prepared)<1000
    assert all(m.instructions is None for m in prepared)
    assert all(m.instructions is not None for m in messages)
    assert [m.parts for m in prepared] == [m.parts for m in messages]


def user(text):
    return ModelRequest(parts=[UserPromptPart(content=text)])


def round_(text, call_id=None, result="result"):
    messages = [user(text)]
    if call_id:
        messages += [ModelResponse(parts=[ToolCallPart("read", {}, call_id)]),
                     ModelRequest(parts=[ToolReturnPart("read", result, call_id)])]
    return [*messages, ModelResponse(parts=[TextPart("done")])]


def test_unknown_window_and_zero_budget_are_distinct():
    messages = round_("中" * 5000)
    assert history_budget(config(None)) is None
    assert history_budget(SimpleNamespace()) is None
    assert window_to_budget(messages, None) == messages
    assert window_to_budget([], 0) == []
    with pytest.raises(ContextBudgetExceeded) as exc:
        window_to_budget(messages, 0)
    assert exc.value.budget == 0
    assert exc.value.estimated_tokens == estimate_messages_tokens(messages)


def test_output_safety_and_extras_reservations():
    assert history_budget(config(10000, 2000), 1000) == 6500
    assert output_reserve(config(1024, None)) == 256
    assert history_budget(config(1024, None)) == 704
    assert history_budget(config(1024, 1000), 9999) == 0


@pytest.mark.parametrize("invalid", [-1, 1.5, True])
def test_budget_rejects_invalid_inputs(invalid):
    with pytest.raises(ValueError):
        history_budget(config(), invalid)
    with pytest.raises(ValueError):
        window_to_budget([], invalid)


def test_cjk_emoji_json_and_tool_payloads_are_charged():
    assert estimate_text_tokens("abc") == 3
    assert estimate_text_tokens("中文🙂") == 10
    small = round_("read", "call", {"data": "x"})
    large = round_("read", "call", {"data": "中" * 10000})
    assert estimate_messages_tokens(large) - estimate_messages_tokens(small) >= 29999
    assert estimate_messages_tokens([user("中文🙂")]) > 10


def test_binary_and_remote_media_are_not_counted_as_short_repr():
    text = estimate_messages_tokens([user("attachment")])
    image = estimate_messages_tokens([user([BinaryContent(b"x", media_type="image/png")])])
    larger = estimate_messages_tokens([user([BinaryContent(b"x" * 10000, media_type="image/png")])])
    remote = estimate_messages_tokens([user([ImageUrl("https://example.com/image.png")])])
    pdf = estimate_messages_tokens([user([BinaryContent(b"pdf", media_type="application/pdf")])])
    assert text < image == larger  # Unknown native image: bytes are not text tokens.
    assert remote >= 16384
    assert pdf >= 32768


def _png(width, height, payload_size=0):
    import struct
    import zlib
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data)))
    header = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    return b"\x89PNG\r\n\x1a\n" + header + b"x" * payload_size


def test_moderate_200kib_png_fits_128k_window_but_extreme_pixels_do_not():
    image = BinaryContent(_png(1024, 768, 200 * 1024), media_type="image/png")
    messages = [user(["describe this", image])]
    assert 5120 <= estimate_messages_tokens(messages) < 6000
    assert window_to_budget(messages, history_budget(config(128000, 4096))) == messages
    giant = [user([BinaryContent(_png(100000, 100000), media_type="image/png")])]
    with pytest.raises(ContextBudgetExceeded):
        window_to_budget(giant, history_budget(config(128000, 4096)))


def test_image_dimensions_not_compression_size_determine_visual_tokens():
    small = [user([BinaryContent(_png(512, 512, 500000), media_type="image/png")])]
    large = [user([BinaryContent(_png(2048, 2048, 100), media_type="image/png")])]
    assert estimate_messages_tokens(small) < estimate_messages_tokens(large)


def test_wav_duration_and_mp3_fallback_do_not_charge_base64_tokens():
    import wave
    from io import BytesIO
    data = BytesIO()
    with wave.open(data, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(48000)
        audio.writeframes(b"\x00\x00" * 48000 * 12)
    wav = [user([BinaryContent(data.getvalue(), media_type="audio/wav")])]
    mp3 = [user([BinaryContent(b"x" * 1024 * 1024, media_type="audio/mpeg")])]
    assert 2224 <= estimate_messages_tokens(wav) < 3000
    assert 65536 <= estimate_messages_tokens(mp3) < 66000
    assert window_to_budget(mp3, history_budget(config(128000, 4096))) == mp3


def test_window_keeps_complete_tool_round_and_does_not_mutate():
    newest = round_("current", "new")
    messages = round_("old" * 1000, "old") + newest
    original = list(messages)
    result = window_to_budget(messages, estimate_messages_tokens(newest))
    assert result == newest
    assert messages == original
    assert result[-1] is messages[-1]


def test_newest_user_and_large_tool_output_raise_instead_of_being_sliced():
    newest = round_("current", "new", "中" * 5000)
    messages = round_("old") + newest
    with pytest.raises(ContextBudgetExceeded, match="上下文超限"):
        window_to_budget(messages, 4096)
    assert messages[-2].parts[0].content == "中" * 5000


def test_mixed_user_return_request_cannot_orphan_previous_call():
    messages = [user("first"), ModelResponse(parts=[ToolCallPart("read", {}, "id")]),
                ModelRequest(parts=[ToolReturnPart("read", "ok", "id"),
                                    UserPromptPart(content="new question")])]
    assert safe_round_starts(messages) == [0]
    with pytest.raises(ContextBudgetExceeded):
        window_to_budget(messages, estimate_messages_tokens(messages[2:]))


def test_pending_call_pins_round_even_if_new_user_arrives():
    messages = [user("first"), ModelResponse(parts=[ToolCallPart("read", {}, "id")]),
                user("new question")]
    with pytest.raises(ContextBudgetExceeded):
        window_to_budget(messages, estimate_messages_tokens(messages[2:]))


def test_retry_closes_call_and_parallel_calls_are_preserved():
    older = [user("first"), ModelResponse(parts=[ToolCallPart("read", {}, "a"),
                                                ToolCallPart("read", {}, "b")]),
             ModelRequest(parts=[ToolReturnPart("read", "ok", "a"),
                                 RetryPromptPart("retry", tool_name="read", tool_call_id="b")])]
    latest = round_("now")
    assert window_to_budget(older + latest, estimate_messages_tokens(latest)) == latest


def test_system_prompt_embedded_in_removed_user_round_is_pinned():
    system = SystemPromptPart("Always obey these instructions")
    older = [ModelRequest(parts=[system, UserPromptPart(content="old" * 1000)])]
    latest = round_("current")
    expected = [ModelRequest(parts=[system]), *latest]
    assert window_to_budget(older + latest, estimate_messages_tokens(expected)) == expected
    with pytest.raises(ContextBudgetExceeded):
        window_to_budget(older + latest, estimate_messages_tokens(latest))


def test_summary_preferred_when_it_fits_and_dropped_only_as_a_pair():
    summary = summary_pair("Remember the original goal")
    latest = round_("current")
    messages = summary + round_("old" * 2000, "id") + latest
    assert window_to_budget(messages, estimate_messages_tokens(summary + latest)) == summary + latest
    assert window_to_budget(messages, estimate_messages_tokens(latest)) == latest


def test_round_without_user_is_indivisible():
    messages = [ModelResponse(parts=[ToolCallPart("read", {}, "id")]),
                ModelRequest(parts=[ToolReturnPart("read", "x" * 1000, "id")])]
    with pytest.raises(ContextBudgetExceeded):
        window_to_budget(messages, 100)


def test_request_overhead_grows_with_actual_tools_and_instructions():
    from pydantic_ai.messages import InstructionPart
    from pydantic_ai.models import ModelRequestParameters
    from pydantic_ai.tools import ToolDefinition
    empty = request_extra_tokens(ModelRequestParameters())
    full = request_extra_tokens(ModelRequestParameters(
        instruction_parts=[InstructionPart("rules" * 100)],
        function_tools=[ToolDefinition(name=f"tool_{i}", description="文" * 100,
                                      parameters_json_schema={"type": "object"}) for i in range(40)],
        output_tools=[ToolDefinition(name="result", parameters_json_schema={"type": "object"})],
    ))
    assert full - empty > 12500


def test_real_agent_hook_counts_current_input_before_first_request():
    calls = []
    def model(messages, info):
        calls.append(messages)
        return ModelResponse(parts=[TextPart("ok")])
    agent = Agent(FunctionModel(model), capabilities=[context_budget_hooks(config(2048, 256))])
    with pytest.raises(ContextBudgetExceeded):
        agent.run_sync("中" * 1000, message_history=round_("old"))
    assert calls == []


def test_real_agent_tool_output_is_checked_before_next_model_request():
    calls = []
    def model(messages, info):
        calls.append(messages)
        return ModelResponse(parts=[ToolCallPart("read", {}, "id")])
    agent = Agent(FunctionModel(model), capabilities=[context_budget_hooks(config(4096, 256))])

    @agent.tool_plain
    def read() -> str:
        return "中" * 3000

    with pytest.raises(ContextBudgetExceeded):
        agent.run_sync("read")
    assert len(calls) == 1


def test_real_agent_dynamic_instructions_and_large_tool_schema_block_request():
    calls = []
    def model(messages, info):
        calls.append(messages)
        return ModelResponse(parts=[TextPart("ok")])
    agent = Agent(FunctionModel(model), capabilities=[context_budget_hooks(config(4096, 256))])

    @agent.instructions
    def instructions(ctx):
        return "dynamic rules" * 200

    def read() -> str:
        return "ok"
    read.__doc__ = "Long tool description " * 200
    agent.tool_plain(read)
    with pytest.raises(ContextBudgetExceeded):
        agent.run_sync("hi")
    assert calls == []


def test_real_agent_hook_windows_history_and_applies_default_output_cap():
    calls = []
    def model(messages, info):
        calls.append((list(messages), info.model_settings))
        return ModelResponse(parts=[TextPart("ok")])
    agent = Agent(FunctionModel(model), capabilities=[context_budget_hooks(config(4096, None))])
    result = agent.run_sync("current", message_history=round_("old" * 2000))
    assert result.output == "ok"
    assert len(calls[0][0]) == 1
    assert calls[0][0][0].parts[0].content == "current"
    assert calls[0][1]["max_tokens"] == 1024


def test_model_output_override_and_unknown_window_legacy():
    calls = []
    def model(messages, info):
        calls.append(info.model_settings)
        return ModelResponse(parts=[TextPart("ok")])
    agent = Agent(FunctionModel(model, settings={"max_tokens": 1234}),
                  capabilities=[context_budget_hooks(config(8192, 512))])
    agent.run_sync("current")
    assert calls[-1]["max_tokens"] == 1234
    legacy = Agent(FunctionModel(model), capabilities=[context_budget_hooks(config(None, None))])
    legacy.run_sync("x" * 20000)
    assert not calls[-1] or "max_tokens" not in calls[-1]


def test_real_agent_deferred_approval_resume_checks_tool_output():
    from pydantic_ai import DeferredToolRequests, DeferredToolResults
    calls = []
    def model(messages, info):
        calls.append(messages)
        return ModelResponse(parts=[ToolCallPart("read", {}, "id")])
    agent = Agent(FunctionModel(model), output_type=[str, DeferredToolRequests],
                  capabilities=[context_budget_hooks(config(4096, 256))])

    @agent.tool_plain(requires_approval=True)
    def read() -> str:
        return "中" * 3000

    pending = agent.run_sync("read")
    assert isinstance(pending.output, DeferredToolRequests)
    with pytest.raises(ContextBudgetExceeded):
        agent.run_sync(None, message_history=pending.all_messages(),
                       deferred_tool_results=DeferredToolResults(approvals={"id": True}))
    assert len(calls) == 1


def test_summary_after_pinned_system_prompt_survives_where_it_fits():
    system = ModelRequest(parts=[SystemPromptPart("rules")])
    summary = summary_pair("original goal")
    latest = round_("current")
    messages = [system, *summary, *round_("old" * 3000), *latest]
    result = window_to_budget(messages, estimate_messages_tokens([system, *summary, *latest]))
    assert all(m in result for m in summary + latest)
    assert any(isinstance(p, SystemPromptPart) for m in result for p in m.parts)


def test_legacy_round_window_also_preserves_cross_round_tool_pairs():
    from zhishi.agent.compaction import window_model_messages
    messages = [user("first"), ModelResponse(parts=[ToolCallPart("read", {}, "id")]),
                ModelRequest(parts=[ToolReturnPart("read", "ok", "id"),
                                    UserPromptPart(content="new question")])]
    assert window_model_messages(messages, keep=1) == messages
