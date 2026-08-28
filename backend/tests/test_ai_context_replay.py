"""上下文回放修复测试（阶段 6）。

直接测试 build_replay_messages + _expand_assistant_for_replay：
- assistant 带 resume checkpoint → 展开为完整 tool 链（assistant+tool_calls + tool 消息）
- assistant 仅 tool_results（无 checkpoint）→ 降级纯 content（避免孤儿 tool 消息）
- 按轮截断（REPLAY_MAX_ROUNDS）+ 总消息 cap（REPLAY_MAX_MESSAGES）
- 截断后无孤儿 tool 消息（tool 必紧跟其 assistant）
"""
import json

import pytest

from app.models import AIMessage
from app.routers.ai import (
    REPLAY_MAX_MESSAGES,
    REPLAY_MAX_ROUNDS,
    _expand_assistant_for_replay,
    build_replay_messages,
)


def _msg(role, content, meta=None):
    """构造一个 AIMessage-like 对象（db row 的最小替身）。"""
    m = AIMessage(conversation_id=1, role=role, content=content)
    if meta is not None:
        m.meta = json.dumps(meta, ensure_ascii=False)
    return m


def test_expand_assistant_with_resume_checkpoint_yields_full_tool_chain():
    """带 resume checkpoint 的 assistant 消息展开为 assistant(tool_calls) + tool 消息序列。"""
    meta = {
        "resume": {
            "assistant_text": "我先建任务",
            "assistant_tool_calls": [
                {"id": "call_1", "name": "create_task", "arguments": {"title": "X"}},
            ],
            "tool_messages": [
                {"role": "tool", "tool_call_id": "call_1", "name": "create_task", "content": '{"ok":true}'},
            ],
        }
    }
    expanded = _expand_assistant_for_replay(meta, "我先建任务")
    assert len(expanded) == 2
    assert expanded[0]["role"] == "assistant"
    assert expanded[0]["tool_calls"][0]["name"] == "create_task"
    assert expanded[1]["role"] == "tool"
    assert expanded[1]["tool_call_id"] == "call_1"


def test_expand_assistant_tool_content_truncated():
    """checkpoint tool 消息内容超过限制时截断。"""
    long_content = "x" * 2000
    meta = {
        "resume": {
            "assistant_text": "t",
            "assistant_tool_calls": [{"id": "c1", "name": "list_tasks", "arguments": {}}],
            "tool_messages": [
                {"role": "tool", "tool_call_id": "c1", "name": "list_tasks", "content": long_content},
            ],
        }
    }
    expanded = _expand_assistant_for_replay(meta, "t")
    tool_msg = expanded[1]
    assert len(tool_msg["content"]) < len(long_content)
    assert tool_msg["content"].endswith("...[已截断]")


def test_expand_assistant_with_tool_chain_yields_full_chain():
    """正常完成轮落库的 meta.tool_chain 优先展开为 assistant(tool_calls) + tool 消息。

    这是阶段 6 跨轮引用的核心路径：此前正常完成轮只写 tool_results（无 resume
    checkpoint），展开降级为纯 content，导致第二轮失忆。修复后写 tool_chain。
    """
    meta = {
        "tool_chain": [
            {
                "role": "assistant",
                "content": "已建任务",
                "tool_calls": [
                    {"id": "call_1", "name": "create_task", "arguments": {"title": "X"}},
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "name": "create_task",
                "content": '{"ok": true, "id": 5}',
            },
        ]
    }
    expanded = _expand_assistant_for_replay(meta, "已建任务")
    assert len(expanded) == 2
    assert expanded[0]["role"] == "assistant"
    assert expanded[0]["content"] == "已建任务"
    assert expanded[0]["tool_calls"][0]["name"] == "create_task"
    assert expanded[0]["tool_calls"][0]["arguments"] == {"title": "X"}
    assert expanded[1]["role"] == "tool"
    assert expanded[1]["tool_call_id"] == "call_1"
    assert expanded[1]["name"] == "create_task"
    assert expanded[1]["content"] == '{"ok": true, "id": 5}'


def test_expand_assistant_prefers_tool_chain_over_resume_checkpoint():
    """meta 同时含 tool_chain 与 resume 时，tool_chain 优先（更完整的本次真实序列）。"""
    meta = {
        "tool_chain": [
            {
                "role": "assistant",
                "content": "用 tool_chain",
                "tool_calls": [{"id": "c1", "name": "list_tasks", "arguments": {}}],
            },
            {"role": "tool", "tool_call_id": "c1", "name": "list_tasks", "content": "[]"},
        ],
        "resume": {
            "assistant_text": "用 resume（不应被采用）",
            "assistant_tool_calls": [{"id": "x", "name": "delete_task", "arguments": {}}],
            "tool_messages": [
                {"role": "tool", "tool_call_id": "x", "name": "delete_task", "content": "{}"},
            ],
        },
    }
    expanded = _expand_assistant_for_replay(meta, "fallback")
    assert expanded[0]["content"] == "用 tool_chain"
    assert expanded[1]["tool_call_id"] == "c1"


def test_expand_assistant_tool_chain_truncates_tool_content():
    """tool_chain 中 tool 消息内容超过 REPLAY_TOOL_CONTENT_LIMIT 时截断。"""
    long_content = "x" * 2000
    meta = {
        "tool_chain": [
            {
                "role": "assistant",
                "content": "t",
                "tool_calls": [{"id": "c1", "name": "list_tasks", "arguments": {}}],
            },
            {"role": "tool", "tool_call_id": "c1", "name": "list_tasks", "content": long_content},
        ]
    }
    expanded = _expand_assistant_for_replay(meta, "t")
    tool_msg = expanded[1]
    assert len(tool_msg["content"]) < len(long_content)
    assert tool_msg["content"].endswith("...[已截断]")


def test_expand_assistant_with_only_tool_results_degrades_to_content():
    """无 checkpoint、仅 tool_results 时降级为纯 content（避免孤儿 tool 消息）。"""
    meta = {"tool_results": [{"tool": "create_task", "args": {}, "result": {"ok": True}}]}
    expanded = _expand_assistant_for_replay(meta, "已建任务")
    assert expanded == [{"role": "assistant", "content": "已建任务"}]


def test_expand_assistant_no_meta_degrades_to_content():
    """老数据无 meta 时降级为纯 content。"""
    expanded = _expand_assistant_for_replay({}, "hello")
    assert expanded == [{"role": "assistant", "content": "hello"}]


def test_build_replay_messages_basic_user_assistant():
    """基本场景：user + assistant(content) → 两条消息。"""
    history = [
        _msg("user", "你好"),
        _msg("assistant", "你好，有什么可以帮你？"),
        _msg("user", "建任务"),
        _msg("assistant", "好的"),
    ]
    msgs = build_replay_messages(history)
    roles = [m["role"] for m in msgs]
    assert roles == ["user", "assistant", "user", "assistant"]
    assert msgs[0]["content"] == "你好"


def test_build_replay_messages_expands_tool_chain():
    """跨轮引用：第二轮请求的 messages 应含首轮 assistant 的 tool_calls + tool 消息。"""
    history = [
        _msg("user", "建任务"),
        _msg(
            "assistant",
            "已建",
            meta={
                "resume": {
                    "assistant_text": "已建",
                    "assistant_tool_calls": [
                        {"id": "c1", "name": "create_task", "arguments": {"title": "X"}},
                    ],
                    "tool_messages": [
                        {"role": "tool", "tool_call_id": "c1", "name": "create_task", "content": '{"ok":true}'},
                    ],
                },
                "tool_results": [{"tool": "create_task", "args": {}, "result": {"ok": True}}],
            },
        ),
        _msg("user", "把刚才那个删掉"),
    ]
    msgs = build_replay_messages(history)
    roles = [m["role"] for m in msgs]
    # 第一轮 assistant 应展开为 assistant(tool_calls) + tool
    assert "tool" in roles
    # tool 消息紧跟其 assistant
    tool_idx = roles.index("tool")
    assert roles[tool_idx - 1] == "assistant"
    # 最后一条是新的 user
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"] == "把刚才那个删掉"


def test_build_replay_messages_replays_normally_completed_round():
    """阶段 6 验收：正常完成轮（仅 tool_chain、无 resume checkpoint）第二轮回放时展开为 tool 链。

    回归场景：修复前正常完成轮只写 tool_results，_expand_assistant_for_replay 走降级分支
    返回纯 content，第一轮的 create_task 调用在第二轮上下文里消失（跨轮失忆）。
    """
    history = [
        _msg("user", "建一个叫 X 的任务"),
        _msg(
            "assistant",
            "已建任务 X",
            meta={
                # 正常完成轮：有 tool_chain + tool_results，但无 resume checkpoint
                "tool_chain": [
                    {
                        "role": "assistant",
                        "content": "已建任务 X",
                        "tool_calls": [
                            {"id": "call_1", "name": "create_task", "arguments": {"title": "X"}},
                        ],
                    },
                    {
                        "role": "tool",
                        "tool_call_id": "call_1",
                        "name": "create_task",
                        "content": '{"ok": true, "id": 5, "title": "X"}',
                    },
                ],
                "tool_results": [{"tool": "create_task", "args": {"title": "X"}, "result": {"ok": True, "id": 5}}],
            },
        ),
        _msg("user", "把刚才那个删掉"),
    ]
    msgs = build_replay_messages(history)
    roles = [m["role"] for m in msgs]
    # 第一轮 assistant 展开为 assistant(tool_calls) + tool，跨轮不再失忆
    assert "tool" in roles
    tool_idx = roles.index("tool")
    assert roles[tool_idx - 1] == "assistant"
    assistant_msg = msgs[tool_idx - 1]
    assert assistant_msg["tool_calls"][0]["name"] == "create_task"
    # tool 消息带回了第一轮的结果，第二轮可据此理解「刚才那个」
    assert msgs[tool_idx]["tool_call_id"] == "call_1"
    assert "X" in msgs[tool_idx]["content"]
    # 最后是新 user
    assert msgs[-1]["content"] == "把刚才那个删掉"


def test_build_replay_messages_truncates_by_rounds():
    """超过 REPLAY_MAX_ROUNDS 轮时从最旧的轮次丢弃。"""
    history = []
    for i in range(REPLAY_MAX_ROUNDS + 5):
        history.append(_msg("user", f"问题{i}"))
        history.append(_msg("assistant", f"回答{i}"))
    msgs = build_replay_messages(history)
    user_msgs = [m for m in msgs if m["role"] == "user"]
    # 最多 REPLAY_MAX_ROUNDS 条 user（每轮一条）
    assert len(user_msgs) <= REPLAY_MAX_ROUNDS
    # 保留的是最新的（i 较大的）
    contents = [m["content"] for m in user_msgs]
    assert f"问题{REPLAY_MAX_ROUNDS + 4}" in contents
    assert "问题0" not in contents


def test_build_replay_messages_caps_total_and_no_orphan_tool():
    """总消息数 cap REPLAY_MAX_MESSAGES，且截断后头部无孤儿 tool 消息。"""
    history = []
    # 构造大量带 tool 链的轮次
    for i in range(40):
        history.append(_msg("user", f"u{i}"))
        history.append(
            _msg(
                "assistant",
                f"a{i}",
                meta={
                    "resume": {
                        "assistant_text": f"a{i}",
                        "assistant_tool_calls": [
                            {"id": f"c{i}", "name": "list_tasks", "arguments": {}},
                        ],
                        "tool_messages": [
                            {"role": "tool", "tool_call_id": f"c{i}", "name": "list_tasks", "content": '{"ok":true}'},
                        ],
                    }
                },
            )
        )
    msgs = build_replay_messages(history)
    assert len(msgs) <= REPLAY_MAX_MESSAGES
    # 头部不是 tool 消息（无孤儿）
    assert msgs[0]["role"] != "tool"
    # 每个 tool 消息的前一条必是 assistant
    for idx, m in enumerate(msgs):
        if m["role"] == "tool":
            assert msgs[idx - 1]["role"] == "assistant"


def test_build_replay_messages_empty_history():
    assert build_replay_messages([]) == []


def test_build_replay_messages_skips_system_messages():
    """system role 消息不纳入回放（由 system_prompt 单独注入）。"""
    history = [
        _msg("system", "危险操作已执行"),
        _msg("user", "下一步"),
        _msg("assistant", "好的"),
    ]
    msgs = build_replay_messages(history)
    roles = [m["role"] for m in msgs]
    assert "system" not in roles
    assert roles == ["user", "assistant"]
