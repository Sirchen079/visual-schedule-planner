"""Full prepared-request summaries, safe fallback and cancellation ownership."""
import asyncio
import threading
from types import SimpleNamespace

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import (
    InstructionPart,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestContext, ModelRequestParameters
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.tools import ToolDefinition

from zhishi.agent import compaction
from zhishi.agent.context_budget import (
    ContextBudgetExceeded,
    context_budget_hooks,
    estimate_messages_tokens,
    history_budget,
    request_extra_tokens,
)


def config(window=8192):
    return SimpleNamespace(context_window=window, max_output_tokens=512, model="test",
                           name="test", provider_kind="openai_compat", api_key_ref=None,
                           base_url=None)


def user(text):
    return ModelRequest(parts=[UserPromptPart(content=text)])


def history(text="old" * 1500):
    return [user(text), ModelResponse(parts=[TextPart("old answer")])]


def capture_summary(monkeypatch, error=False):
    calls = []
    def oneshot(cfg, system, prompt, timeout):
        calls.append((cfg, system, prompt, threading.get_ident()))
        if error:
            raise RuntimeError("summary unavailable")
        return "Remember the original goal"
    monkeypatch.setattr(compaction, "_oneshot_with_timeout", oneshot)
    return calls


@pytest.mark.parametrize("pressure", ["current_user", "prepared_tools"])
async def test_real_agent_summarizes_full_request_before_hard_window(monkeypatch, pressure):
    cfg = config()
    summaries = capture_summary(monkeypatch)
    requests, saved = [], []
    owner = threading.get_ident()
    def model(messages, info):
        requests.append(list(messages))
        return ModelResponse(parts=[TextPart("ok")])
    def save(summary, fp):
        saved.append((summary, fp, threading.get_ident()))
    agent = Agent(FunctionModel(model), capabilities=[
        compaction.request_compaction_hooks(cfg, on_summary=save), context_budget_hooks(cfg)])
    old = history()
    current = "中" * 1100 if pressure == "current_user" else "current"
    if pressure == "prepared_tools":
        @agent.instructions
        def rules(ctx):
            return "dynamic instructions " * 30

        def read() -> str:
            return "ok"
        read.__doc__ = "Tool schema description " * 110
        agent.tool_plain(read)
        # The ordinary loader sees a history that still fits without extras.
        assert estimate_messages_tokens([*old, user(current)]) < history_budget(cfg)
    assert estimate_messages_tokens(old) < history_budget(cfg)
    result = await agent.run(current, message_history=old)
    assert result.output == "ok"
    assert len(summaries) == len(saved) == len(requests) == 1
    assert saved[0][2] == owner != summaries[0][3]
    assert requests[0][0].parts[0].content.startswith(compaction.SUMMARY_PREFIX)
    assert requests[0][-1].parts[0].content == current
    assert "old" in summaries[0][2]
    assert current not in summaries[0][2]


async def test_tool_output_triggers_summary_preserving_current_call_ids(monkeypatch):
    cfg = config()
    summaries = capture_summary(monkeypatch)
    requests = []
    def model(messages, info):
        requests.append(list(messages))
        return ModelResponse(parts=([ToolCallPart("read", {}, "live-call")]
                                    if len(requests) == 1 else [TextPart("ok")]))
    agent = Agent(FunctionModel(model), capabilities=[
        compaction.request_compaction_hooks(cfg), context_budget_hooks(cfg)])

    @agent.tool_plain
    def read() -> str:
        return "data" * 900

    result = await agent.run("read current", message_history=history())
    assert result.output == "ok" and len(requests) == 2 and len(summaries) == 1
    outgoing = requests[-1]
    assert outgoing[0].parts[0].content.startswith(compaction.SUMMARY_PREFIX)
    assert [p.tool_call_id for m in outgoing for p in m.parts
            if isinstance(p, ToolCallPart)] == ["live-call"]
    assert [p.tool_call_id for m in outgoing for p in m.parts
            if isinstance(p, ToolReturnPart)] == ["live-call"]
    assert any(isinstance(p, UserPromptPart) and p.content == "read current"
               for m in outgoing for p in m.parts)
    assert any(isinstance(p, ToolReturnPart) and p.content == "data" * 900
               for m in outgoing for p in m.parts)


@pytest.mark.parametrize("output_override", [None, 2500])
async def test_effective_output_limits_extras_snapshot_and_hook_local_state(monkeypatch, output_override):
    cfg = config()
    parameters = ModelRequestParameters(
        instruction_parts=[InstructionPart("rules" * 100)],
        function_tools=[ToolDefinition(name="read", description="schema" * 100,
                                       parameters_json_schema={"type": "object"})])
    request = ModelRequestContext(
        model=FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("ok")]),
                            settings={"max_tokens": 1500}),
        messages=[*history(), user("current" * 100)],
        model_settings={"max_tokens": output_override} if output_override else None,
        model_request_parameters=parameters, streaming=True, model_id="original-model")
    seen = []
    def summarize(db, snapshot, messages, **kw):
        seen.append((db, snapshot, kw, threading.get_ident()))
        return [*compaction.summary_pair("new summary"), messages[-1]], "new summary", "new-fp"
    monkeypatch.setattr(compaction, "summarize_history", summarize)
    hook = compaction.request_compaction_hooks(
        cfg, threshold=7, timeout=3, stored_summary="seed", stored_fingerprint="seed-fp")
    cfg.context_window = None  # Hook already captured plain configuration values.
    cfg.model = "changed"
    output = await hook.before_model_request(None, request)
    await hook.before_model_request(None, request)
    assert len(seen) == 2
    assert seen[0][0] is None
    assert seen[0][1] is not cfg and seen[0][1].model == "test"
    assert seen[0][1].context_window == 8192
    assert seen[0][1].max_output_tokens == (output_override or 1500)
    assert seen[0][2] == {"stored_summary": "seed", "stored_fingerprint": "seed-fp",
                          "threshold": 7, "timeout": 3,
                          "extra_tokens": request_extra_tokens(parameters)}
    assert seen[1][2]["stored_summary"] == "new summary"
    assert seen[1][2]["stored_fingerprint"] == "new-fp"
    assert output.streaming and output.model_id == "original-model"
    assert output.model_settings is request.model_settings
    assert request.messages[0].parts[0].content.startswith("old")


@pytest.mark.parametrize("window", [None, 1000000])
async def test_no_round_only_trigger_or_unknown_window_summary(monkeypatch, window):
    def unexpected(*args, **kwargs):
        pytest.fail("No request summary should be attempted")
    monkeypatch.setattr(compaction, "summarize_history", unexpected)
    agent = Agent(FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("ok")])),
                  capabilities=[compaction.request_compaction_hooks(config(window), threshold=1)])
    await agent.run("current", message_history=[m for _ in range(14) for m in history("old")])


async def test_summary_failure_uses_final_budget_fallback_without_save(monkeypatch):
    cfg = config()
    summaries = capture_summary(monkeypatch, error=True)
    requests, saved = [], []
    def model(messages, info):
        requests.append(list(messages))
        return ModelResponse(parts=[TextPart("ok")])
    agent = Agent(FunctionModel(model), capabilities=[
        compaction.request_compaction_hooks(cfg, on_summary=lambda s, f: saved.append((s, f))),
        context_budget_hooks(cfg)])
    current = "中" * 1100
    await agent.run(current, message_history=history())
    assert len(summaries) == 1 and saved == []
    assert len(requests[0]) == 1 and requests[0][0].parts[0].content == current


async def test_newest_round_overflow_remains_explicit(monkeypatch):
    cfg = config()
    summaries = capture_summary(monkeypatch)
    requests = []
    def model(messages, info):
        requests.append(messages)
        return ModelResponse(parts=[TextPart("ok")])
    agent = Agent(FunctionModel(model), capabilities=[
        compaction.request_compaction_hooks(cfg), context_budget_hooks(cfg)])
    with pytest.raises(ContextBudgetExceeded):
        await agent.run("中" * 5000, message_history=history())
    assert summaries == requests == []


async def test_cancelled_worker_cannot_save_or_advance_summary_state(monkeypatch):
    entered, finished = asyncio.Event(), asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    seen, saved = [], []
    def summarize(db, snapshot, messages, **kw):
        seen.append(kw)
        if len(seen) == 1:
            loop.call_soon_threadsafe(entered.set)
            try:
                assert release.wait(5)
                return messages, "late summary", "late-fp"
            finally:
                loop.call_soon_threadsafe(finished.set)
        return messages, None, None
    monkeypatch.setattr(compaction, "summarize_history", summarize)
    hook = compaction.request_compaction_hooks(
        config(), stored_summary="seed", stored_fingerprint="seed-fp",
        on_summary=lambda s, f: saved.append((s, f)))
    request = ModelRequestContext(
        model=FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("ok")])),
        messages=[*history(), user("中" * 1100)], model_settings=None,
        model_request_parameters=ModelRequestParameters())
    pending = asyncio.create_task(hook.before_model_request(None, request))
    try:
        await asyncio.wait_for(entered.wait(), 3)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    finally:
        release.set()
        await asyncio.wait_for(finished.wait(), 3)
    assert saved == []
    await hook.before_model_request(None, request)
    assert seen[-1]["stored_summary"] == "seed"
    assert seen[-1]["stored_fingerprint"] == "seed-fp"
