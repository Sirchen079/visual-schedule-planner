# tests/agent/test_compaction.py
import json

import pytest

from zhishi.agent.compaction import window_history, model_message_round_start, window_model_messages


def test_summary_request_keeps_reasoning_setting_without_mutating_config():
    from types import SimpleNamespace
    from zhishi.agent.compaction import _summary_config
    config = SimpleNamespace(reasoning_effort='low', max_output_tokens=8192)
    snapshot = _summary_config(config, 1024)
    assert snapshot.reasoning_effort == 'low' and snapshot.max_output_tokens == 1024
    assert config.max_output_tokens == 8192


def test_window_history_keeps_recent_rounds():
    """降级策略：按轮截断，绝不产生孤儿 tool 消息。"""
    msgs = [{"role": "user", "text": f"u{i}"} for i in range(20)]
    kept = window_history(msgs, keep=5)
    assert len(kept) == 5 and kept[-1]["text"] == "u19"


def test_window_history_never_orphan_tool():
    msgs = [
        {"role": "user", "text": "u0"},
        {"role": "assistant", "tool_calls": [1]},
        {"role": "tool", "call_id": 1},
        {"role": "user", "text": "u1"},
    ]
    kept = window_history(msgs, keep=1)
    # 只保 1 条 user 时，前面的 assistant+tool 链必须整体丢弃，不得留孤儿
    assert kept == [{"role": "user", "text": "u1"}]


def test_model_message_round_start():
    from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart, TextPart
    assert model_message_round_start(ModelRequest(parts=[UserPromptPart(content="hi")]))
    assert not model_message_round_start(ModelResponse(parts=[TextPart(content="ok")]))


def test_window_model_messages_cuts_at_user_boundary():
    from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart, TextPart
    msgs: list = []
    for i in range(10):
        msgs.append(ModelRequest(parts=[UserPromptPart(content=f"u{i}")]))
        msgs.append(ModelResponse(parts=[TextPart(content=f"a{i}")]))
    kept = window_model_messages(msgs, keep=3)
    assert len(kept) == 6
    assert kept[0].parts[0].content == "u7"  # 从倒数第 3 个 user 轮起


# ---- 摘要压缩（清账 11：BLOCKED.md 唯一条——自研 maybe_summarize） ----

def _round_msgs(i: int, with_tools: bool = False) -> list:
    """一轮对话：user 起，可选工具链（调用→结果），assistant 文本收尾。"""
    from pydantic_ai.messages import (ModelRequest, ModelResponse, TextPart,
                                      ToolCallPart, ToolReturnPart, UserPromptPart)
    msgs: list = [ModelRequest(parts=[UserPromptPart(content=f"u{i}")])]
    if with_tools:
        msgs.append(ModelResponse(parts=[ToolCallPart(
            tool_name="atomic_read", args={"path": f"f{i}.py"}, tool_call_id=f"tc{i}")]))
        msgs.append(ModelRequest(parts=[ToolReturnPart(
            tool_name="atomic_read", content="ok", tool_call_id=f"tc{i}")]))
    msgs.append(ModelResponse(parts=[TextPart(content=f"a{i}")]))
    return msgs


def _history(n: int, tool_every: int = 0) -> list:
    msgs: list = []
    for i in range(n):
        msgs += _round_msgs(i, with_tools=bool(tool_every) and i % tool_every == 0)
    return msgs


def _config():
    from zhishi.domain.models import AIConfig
    return AIConfig(name="t", provider_kind="openai_compat", model="test-model", enabled=True)


def _capture_oneshot(monkeypatch, reply="四段式摘要：目标/已办/偏好/未完成", error=None):
    from zhishi.agent import compaction
    calls: list[dict] = []

    def fake_oneshot(model, system, user):
        calls.append({"system": system, "user": user})
        if error is not None:
            raise error
        return reply

    monkeypatch.setattr(compaction, "build_model", lambda cfg, api_key=None: object())
    monkeypatch.setattr(compaction, "oneshot_text", fake_oneshot)
    return calls


def _round_starts(msgs: list) -> list[int]:
    return [i for i, m in enumerate(msgs) if model_message_round_start(m)]


def _assert_no_orphans(msgs: list) -> None:
    """不变量：每条 ToolReturnPart 的调用必须在本消息列表更早处出现过。"""
    from pydantic_ai.messages import (ModelRequest, ModelResponse, ToolCallPart,
                                      ToolReturnPart)
    seen: set[str] = set()
    for m in msgs:
        if isinstance(m, ModelResponse):
            seen.update(p.tool_call_id for p in m.parts if isinstance(p, ToolCallPart))
        elif isinstance(m, ModelRequest):
            for p in m.parts:
                if isinstance(p, ToolReturnPart):
                    assert p.tool_call_id in seen


def test_compaction_threshold_setting(db):
    """触发阈值 settingsvc 可配，脏值/非正数回退默认 12。"""
    from zhishi.agent.compaction import compaction_threshold
    from zhishi.domain.settingsvc import set_setting
    assert compaction_threshold(db) == 12
    set_setting(db, "compaction_threshold", "8")
    assert compaction_threshold(db) == 8
    set_setting(db, "compaction_threshold", "abc")
    assert compaction_threshold(db) == 12
    set_setting(db, "compaction_threshold", "0")
    assert compaction_threshold(db) == 12


def test_maybe_summarize_triggers_over_threshold(db, monkeypatch):
    """超阈值：最旧一半轮次交 oneshot 生成摘要，新 history = 摘要对 + 保留轮。"""
    from zhishi.agent.compaction import SUMMARY_PREFIX, maybe_summarize
    calls = _capture_oneshot(monkeypatch)
    history = _history(14)                      # 14 轮 > 12 触发
    new = maybe_summarize(db, _config(), history)

    assert len(calls) == 1                      # oneshot 恰好一次
    assert "【用户目标】" in calls[0]["system"] and "【未完成事项】" in calls[0]["system"]
    assert "u0" in calls[0]["user"] and "u6" in calls[0]["user"]   # 旧一半轮次进提示词
    assert "u13" not in calls[0]["user"]                            # 保留轮不进提示词

    assert new[0].parts[0].content.startswith(SUMMARY_PREFIX)
    assert new[1].parts[0].content             # assistant 确认占位
    starts = _round_starts(new)
    assert len(starts) == 8                    # 摘要 1 轮 + 保留 7 轮（14 的一半）
    assert starts[0] == 0                      # 头部是新起的一轮（无孤儿前提）
    assert new[2:] == history[_round_starts(history)[7]:]   # 保留轮逐条完整


def test_maybe_summarize_not_triggered_at_threshold(db, monkeypatch):
    """恰等于阈值不触发：原样返回且不调模型。"""
    from zhishi.agent.compaction import maybe_summarize
    calls = _capture_oneshot(monkeypatch)
    history = _history(12)
    assert maybe_summarize(db, _config(), history) == history
    assert calls == []


def test_maybe_summarize_model_failure_returns_original(db, monkeypatch):
    """模型调用异常 → 降级返回原 history，绝不阻塞对话。"""
    from zhishi.agent.compaction import maybe_summarize
    calls = _capture_oneshot(monkeypatch, error=RuntimeError("模型挂了"))
    history = _history(14, tool_every=3)
    assert maybe_summarize(db, _config(), history) == history
    assert len(calls) >= 1


def test_summary_never_orphans_tool_messages(db, monkeypatch):
    """轮边界切分保证无孤儿：工具链要么整轮进摘要、要么整轮保留。"""
    from zhishi.agent.compaction import SUMMARY_PREFIX, maybe_summarize
    _capture_oneshot(monkeypatch)
    history = _history(14, tool_every=3)        # 第 0/3/6/9/12 轮含工具链
    new = maybe_summarize(db, _config(), history)
    assert new[0].parts[0].content.startswith(SUMMARY_PREFIX)
    _assert_no_orphans(new)
    # 保留轮结构与原尾半完全一致（调用→结果配对原样）
    kept = new[2:]
    assert kept == history[_round_starts(history)[7]:]
    _assert_no_orphans(history)


def test_stored_summary_replays_without_model_call(db, monkeypatch):
    """重放优先注入：指纹相同（同一原始历史重放）直接复用已存摘要，不再调模型。"""
    from zhishi.agent.compaction import SUMMARY_PREFIX, summarize_history
    calls = _capture_oneshot(monkeypatch)
    history = _history(14)
    _, summary, fingerprint = summarize_history(db, _config(), history)
    before = len(calls)
    new, replayed, fp2 = summarize_history(
        db, _config(), history, stored_summary=summary, stored_fingerprint=fingerprint)
    assert len(calls) == before                # 指纹相同 → 不调模型
    assert replayed == summary
    assert fp2 == fingerprint
    assert new[0].parts[0].content == f"{SUMMARY_PREFIX}{summary}"


def test_stored_summary_without_fingerprint_merges(db, monkeypatch):
    """旧数据兼容：meta 只有 summary 没有指纹 → 保守走合并路径（调模型，不盲信旧摘要）。"""
    from zhishi.agent.compaction import summarize_history
    calls = _capture_oneshot(monkeypatch, reply="合并后的新摘要")
    history = _history(14)
    new, summary, fingerprint = summarize_history(
        db, _config(), history, stored_summary="旧格式摘要")
    assert len(calls) == 1                     # 合并路径调了模型
    assert "旧格式摘要" in calls[0]["user"]     # 旧摘要是合并输入的一部分
    assert summary == "合并后的新摘要"
    assert fingerprint is not None             # 新指纹随合并摘要落定


def test_second_compaction_merges_old_summary_with_new_facts(db, monkeypatch):
    """re #066 major1 确定性例子：二次压缩的摘要输入必须同时包含
    旧摘要全文与新折叠段的中段唯一事实，不得丢弃后静默复用旧摘要。"""
    from zhishi.agent.compaction import summarize_history
    calls = _capture_oneshot(monkeypatch, reply="合并摘要")
    first = summarize_history(db, _config(), _history(14))
    assert len(calls) == 1
    grown = list(first[0]) + [m for i in range(14, 19) for m in _round_msgs(i)]   # 8+5=13 轮
    new2, summary2, fp2 = summarize_history(
        db, _config(), grown, stored_summary=first[1], stored_fingerprint=first[2])
    assert len(calls) == 2                     # 二次压缩必须重新调模型（合并）
    assert first[1] in calls[1]["user"]        # 旧摘要进合并输入
    assert "u7" in calls[1]["user"] and "u10" in calls[1]["user"]   # 新折叠段事实进输入
    assert "u18" not in calls[1]["user"]       # 保留轮不进输入（u14-u18 在 kept 段）
    assert summary2 == "合并摘要"
    assert fp2 != first[2]                     # 指纹随新折叠集更新
    assert new2[0].parts[0].content.startswith("【会话摘要】")
    _assert_no_orphans(new2)


def test_compaction_timeout_setting(db):
    """超时阈值 settingsvc 可配（compaction_timeout，秒），脏值/非正数回退默认 20.0。"""
    from zhishi.agent.compaction import DEFAULT_COMPACTION_TIMEOUT, compaction_timeout
    from zhishi.domain.settingsvc import set_setting
    assert compaction_timeout(db) == DEFAULT_COMPACTION_TIMEOUT == 20.0
    set_setting(db, "compaction_timeout", "5.5")
    assert compaction_timeout(db) == 5.5
    set_setting(db, "compaction_timeout", "abc")
    assert compaction_timeout(db) == 20.0
    set_setting(db, "compaction_timeout", "0")
    assert compaction_timeout(db) == 20.0


def test_compaction_timeout_falls_back_and_writes_nothing(db, monkeypatch):
    """re #066 major2：摘要调用超时 → 返回原 history，meta_json 不写任何摘要/指纹，
    后续请求（重试）仍可正常压缩。"""
    import time
    from pydantic_ai.messages import ModelMessagesTypeAdapter
    from zhishi.domain.models import AIConversation, AIMessage
    from zhishi.agent import compaction
    from zhishi.domain.settingsvc import set_setting
    from zhishi.server.routes.ai import load_conversation_history

    set_setting(db, "compaction_timeout", "0.2")
    conv = AIConversation(title="超时会话")
    db.add(conv); db.commit(); db.refresh(conv)
    db.add(AIMessage(conversation_id=conv.id, role="assistant", display_json="{}",
                     history_json=ModelMessagesTypeAdapter.dump_json(_history(14)).decode()))
    db.commit()

    def slow_oneshot(model, system, user):
        time.sleep(1.5)
        return "迟到的摘要"

    monkeypatch.setattr(compaction, "build_model", lambda cfg, api_key=None: object())
    monkeypatch.setattr(compaction, "oneshot_text", slow_oneshot)

    loaded = load_conversation_history(db, conv.id, _config())
    # Summary failure preserves every round; the runtime validates request size.
    assert loaded[0].parts[0].content == "u0"
    assert len(_round_starts(loaded)) == 14
    meta = json.loads(db.get(AIConversation, conv.id).meta_json or "{}")
    assert "summary" not in meta and "summary_fingerprint" not in meta   # 绝不补写

    # 后续请求换回正常 oneshot：仍可正常压缩（锁/路径未被卡死）
    calls = _capture_oneshot(monkeypatch)
    loaded2 = load_conversation_history(db, conv.id, _config())
    assert loaded2[0].parts[0].content.startswith("【会话摘要】")
    assert len(calls) == 1
    meta2 = json.loads(db.get(AIConversation, conv.id).meta_json)
    assert meta2["summary"] == "四段式摘要：目标/已办/偏好/未完成"
    assert meta2["summary_fingerprint"]


def test_window_keep_tracks_threshold(db, monkeypatch):
    """re #066：硬截断 keep=max(12, compaction_threshold)，高阈值下摘要触发条件可达。"""
    from zhishi.domain.settingsvc import set_setting
    from pydantic_ai.messages import ModelMessagesTypeAdapter
    from zhishi.domain.models import AIConversation, AIMessage
    from zhishi.server.routes.ai import load_conversation_history

    set_setting(db, "compaction_threshold", "20")
    conv = AIConversation(title="高阈值会话")
    db.add(conv); db.commit(); db.refresh(conv)
    db.add(AIMessage(conversation_id=conv.id, role="assistant", display_json="{}",
                     history_json=ModelMessagesTypeAdapter.dump_json(_history(14)).decode()))
    db.commit()
    _capture_oneshot(monkeypatch)
    loaded = load_conversation_history(db, conv.id)              # 无 config → 只走安全网
    assert len(_round_starts(loaded)) == 14                      # 14 轮 ≤ keep=20，不被砍
    assert loaded[0].parts[0].content == "u0"


def test_pending_tool_tail_untouched(db, monkeypatch):
    """待批工具尾段不动：未结算的调用（有调用无结果）在压缩后原样保留在尾段。"""
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from zhishi.agent.compaction import maybe_summarize
    _capture_oneshot(monkeypatch)
    history = _history(14, tool_every=3)
    history.append(ModelResponse(parts=[ToolCallPart(
        tool_name="atomic_write", args={"path": "x"}, tool_call_id="tcd")]))
    new = maybe_summarize(db, _config(), history)
    assert new[-1] == history[-1]               # 未结算调用逐字保留
    assert new[2:] == history[_round_starts(history)[7]:]
    _assert_no_orphans(history)


def test_load_conversation_history_compacts_and_persists(db, monkeypatch):
    """接线：load_conversation_history 带 config 时压缩 + meta_json 持久化；
    第二次加载（重放）优先用已存摘要，不再调模型。"""
    from pydantic_ai.messages import ModelMessagesTypeAdapter
    from zhishi.domain.models import AIConversation, AIMessage
    from zhishi.server.routes.ai import load_conversation_history

    conv = AIConversation(title="长会话")
    db.add(conv); db.commit(); db.refresh(conv)
    db.add(AIMessage(conversation_id=conv.id, role="assistant", display_json="{}",
                     history_json=ModelMessagesTypeAdapter.dump_json(_history(14)).decode()))
    db.commit()

    calls = _capture_oneshot(monkeypatch)
    loaded = load_conversation_history(db, conv.id, _config())
    assert loaded[0].parts[0].content.startswith("【会话摘要】")
    assert len(_round_starts(loaded)) == 8
    meta = json.loads(db.get(AIConversation, conv.id).meta_json)
    assert meta["summary"] == "四段式摘要：目标/已办/偏好/未完成"       # 已持久化

    before = len(calls)
    loaded2 = load_conversation_history(db, conv.id, _config())
    assert len(calls) == before                                  # 重放不重复调模型
    assert loaded2[0].parts[0].content.startswith("【会话摘要】")
    _assert_no_orphans(loaded2)


def test_load_conversation_history_without_config_preserves_all_rounds(db, monkeypatch):
    """An absent model configuration is never permission to discard history."""
    from pydantic_ai.messages import ModelMessagesTypeAdapter
    from zhishi.domain.models import AIConversation, AIMessage
    from zhishi.server.routes.ai import load_conversation_history

    conv = AIConversation(title="短会话")
    db.add(conv); db.commit(); db.refresh(conv)
    db.add(AIMessage(conversation_id=conv.id, role="assistant", display_json="{}",
                     history_json=ModelMessagesTypeAdapter.dump_json(_history(14)).decode()))
    db.commit()

    calls = _capture_oneshot(monkeypatch)
    loaded = load_conversation_history(db, conv.id)
    assert len(_round_starts(loaded)) == 14
    assert loaded[0].parts[0].content == "u0"
    assert calls == []
    assert json.loads(db.get(AIConversation, conv.id).meta_json) == {}   # 未写摘要


def test_unchanged_summary_persists_new_fingerprint(db, monkeypatch):
    """摘要措辞不变也必须推进覆盖指纹，随后重放不能重复收费调用。"""
    from pydantic_ai.messages import ModelMessagesTypeAdapter
    from zhishi.domain.models import AIConversation, AIMessage
    from zhishi.server.routes.ai import load_conversation_history

    conv = AIConversation(title="相同摘要")
    db.add(conv)
    db.commit()
    message = AIMessage(conversation_id=conv.id, role="assistant", display_json="{}",
                        history_json=ModelMessagesTypeAdapter.dump_json(_history(14)).decode())
    db.add(message)
    db.commit()
    calls = _capture_oneshot(monkeypatch, reply="仍然有效的摘要")
    first = load_conversation_history(db, conv.id, _config())
    original_fp = json.loads(conv.meta_json)["summary_fingerprint"]
    grown = first + [m for i in range(14, 19) for m in _round_msgs(i)]
    message.history_json = ModelMessagesTypeAdapter.dump_json(grown).decode()
    db.commit()
    load_conversation_history(db, conv.id, _config())
    assert json.loads(conv.meta_json)["summary_fingerprint"] != original_fp
    assert len(calls) == 2
    load_conversation_history(db, conv.id, _config())
    assert len(calls) == 2


def test_large_history_keeps_summary_inside_window(db, monkeypatch):
    """导入旧长会话或调低阈值时，生成摘要不能再被最终安全网裁掉。"""
    from pydantic_ai.messages import ModelMessagesTypeAdapter
    from zhishi.domain.models import AIConversation, AIMessage
    from zhishi.server.routes.ai import load_conversation_history

    conv = AIConversation(title="旧长会话")
    db.add(conv)
    db.commit()
    history = _history(40, tool_every=3)
    db.add(AIMessage(conversation_id=conv.id, role="assistant", display_json="{}",
                     history_json=ModelMessagesTypeAdapter.dump_json(history).decode()))
    db.commit()
    calls = _capture_oneshot(monkeypatch)
    loaded = load_conversation_history(db, conv.id, _config())
    assert loaded[0].parts[0].content.startswith("【会话摘要】")
    assert len(_round_starts(loaded)) <= 12
    assert "u28" in calls[0]["user"]
    assert loaded[-1] == history[-1]
    _assert_no_orphans(loaded)


@pytest.mark.parametrize("reply", ["", " \n\t"])
def test_empty_summary_preserves_original_history(db, monkeypatch, reply):
    from zhishi.agent.compaction import summarize_history
    _capture_oneshot(monkeypatch, reply=reply)
    history = _history(14)
    assert summarize_history(db, _config(), history) == (history, None, None)


@pytest.mark.parametrize("value", ["inf", "-inf", "nan"])
def test_compaction_timeout_rejects_nonfinite(db, value):
    from zhishi.agent.compaction import compaction_timeout, DEFAULT_COMPACTION_TIMEOUT
    from zhishi.domain.settingsvc import set_setting
    set_setting(db, "compaction_timeout", value)
    assert compaction_timeout(db) == DEFAULT_COMPACTION_TIMEOUT


def _budget_config(window=8192, output=512):
    cfg = _config()
    cfg.context_window = window
    cfg.max_output_tokens = output
    return cfg


def test_token_pressure_compacts_two_long_rounds_below_round_threshold(monkeypatch):
    from zhishi.agent.compaction import summarize_history
    from zhishi.agent.context_budget import estimate_messages_tokens, history_budget
    history = _history(2, tool_every=1)
    history[0].parts[0].content = "旧事实" * 2000
    history[-1].parts[0].content = "new answer" * 30
    calls = _capture_oneshot(monkeypatch, reply="保留的旧事实")
    cfg = _budget_config()
    result, summary, fingerprint = summarize_history(None, cfg, history, threshold=12, timeout=2)
    assert len(calls) > 1
    assert summary == "保留的旧事实"
    assert fingerprint
    assert result[2:] == history[_round_starts(history)[1]:]
    assert estimate_messages_tokens(result) <= history_budget(cfg)
    _assert_no_orphans(result)


def test_summary_chunks_include_middle_and_end_of_long_messages(monkeypatch):
    from zhishi.agent import compaction
    from zhishi.agent.context_budget import estimate_text_tokens, history_budget
    history = _history(2)
    text = 'HEAD_SENTINEL\n' + '长内容' * 2500 + '\nMIDDLE_SENTINEL\n' + '长内容' * 2500 + '\nTAIL_SENTINEL'
    history[0].parts[0].content = text
    calls = _capture_oneshot(monkeypatch,reply='逐段合并摘要')
    cfg = _budget_config(8192,512)
    result,summary,_ = compaction.summarize_history(None,cfg,history,threshold=12,timeout=2)
    assert summary and len(calls)>2 and len(result)<len(history)+3
    joined = ''.join(c['user'] for c in calls)
    assert all(marker in joined for marker in ('HEAD_SENTINEL','MIDDLE_SENTINEL','TAIL_SENTINEL'))
    assert '内容因上下文预算截短' not in joined
    assert all(estimate_text_tokens(c['user'])<=history_budget(cfg) for c in calls)


def test_token_cut_can_fold_more_than_half_the_rounds(monkeypatch):
    from zhishi.agent.compaction import summarize_history
    from zhishi.agent.context_budget import estimate_messages_tokens, history_budget
    history = _history(6, tool_every=1)
    for start in _round_starts(history)[:-1]:
        history[start].parts[0].content += "长文本" * 900
    calls = _capture_oneshot(monkeypatch, reply="摘要")
    cfg = _budget_config()
    result, summary, _ = summarize_history(None, cfg, history, threshold=12, timeout=2)
    assert len(calls) >= 1 and summary
    assert result[2:] == history[_round_starts(history)[-1]:]
    assert estimate_messages_tokens(result) <= history_budget(cfg)


def test_summary_request_and_output_are_bounded_by_actual_config(monkeypatch):
    from pydantic_ai.messages import ModelRequest, UserPromptPart
    from zhishi.agent import compaction
    from zhishi.agent.context_budget import estimate_messages_tokens, estimate_text_tokens, history_budget
    captured = []
    def build(cfg):
        return cfg
    def oneshot(cfg, system, prompt):
        captured.append((cfg, system, prompt))
        return "过长摘要" * 10000
    monkeypatch.setattr(compaction, "build_model", build)
    monkeypatch.setattr(compaction, "oneshot_text", oneshot)
    cfg = _budget_config(4096, 256)
    history = _history(60)
    for start in _round_starts(history)[:-1]:
        history[start].parts[0].content = "旧内容" * 1000
    result, summary, fp = compaction.summarize_history(
        None, cfg, history, stored_summary="合并旧摘要" * 3000, threshold=12, timeout=2)
    assert len(captured) == 1
    bounded_cfg, system, prompt = captured[0]
    assert bounded_cfg is not cfg
    assert 1 <= bounded_cfg.max_output_tokens <= cfg.max_output_tokens
    assert cfg.max_output_tokens == 256
    request_cost = estimate_messages_tokens([ModelRequest(parts=[UserPromptPart(content=prompt)])])
    assert request_cost <= history_budget(bounded_cfg, estimate_text_tokens(system) + 32)
    assert "内容因上下文预算截短" not in prompt
    # A provider violating the output budget cannot authorize dropping old rounds.
    assert summary is None and fp is None and result == history


def test_newest_round_overflow_is_not_swallowed_as_summary_failure(monkeypatch):
    from zhishi.agent.compaction import summarize_history
    from zhishi.agent.context_budget import ContextBudgetExceeded
    calls = _capture_oneshot(monkeypatch)
    history = _history(2)
    history[-2].parts[0].content = "中" * 10000
    with pytest.raises(ContextBudgetExceeded):
        summarize_history(None, _budget_config(), history, threshold=12, timeout=2)
    assert calls == []


def test_token_summary_failure_preserves_original_for_budget_window(monkeypatch):
    from zhishi.agent.compaction import summarize_history
    from zhishi.agent.context_budget import history_budget, window_to_budget
    history = _history(2)
    history[0].parts[0].content = "中" * 10000
    _capture_oneshot(monkeypatch, error=RuntimeError("offline"))
    cfg = _budget_config()
    assert summarize_history(None, cfg, history, threshold=12, timeout=2) == (history, None, None)
    assert window_to_budget(history, history_budget(cfg)) == history[-2:]


def test_unknown_window_preserves_legacy_round_trigger(monkeypatch):
    from zhishi.agent.compaction import summarize_history
    history = _history(2)
    history[0].parts[0].content = "中" * 10000
    calls = _capture_oneshot(monkeypatch)
    assert summarize_history(None, _budget_config(None), history, threshold=12) == (history, None, None)
    assert calls == []


def test_binary_summary_transcript_uses_metadata_not_raw_payload():
    from pydantic_ai.messages import BinaryContent, ModelRequest, UserPromptPart
    from zhishi.agent.compaction import _render_messages
    transcript = _render_messages([ModelRequest(parts=[UserPromptPart(content=[
        "explain attachment", BinaryContent(b"UNIQUE_RAW_PAYLOAD", media_type="image/png")])])])
    assert "explain attachment" in transcript and "image/png" in transcript
    assert "UNIQUE_RAW_PAYLOAD" not in transcript


def test_token_summary_replay_uses_same_fingerprint_without_new_request(monkeypatch):
    from zhishi.agent.compaction import summarize_history
    calls = _capture_oneshot(monkeypatch, reply="摘要")
    history = _history(2)
    history[0].parts[0].content = "中" * 10000
    cfg = _budget_config()
    first = summarize_history(None, cfg, history, threshold=12, timeout=2)
    first_calls = len(calls)
    second = summarize_history(None, cfg, history, first[1], first[2], threshold=12, timeout=2)
    assert first[1:] == second[1:]
    assert first[0][0].parts[0].content == second[0][0].parts[0].content
    assert first[0][2:] == second[0][2:]
    assert len(calls) == first_calls
