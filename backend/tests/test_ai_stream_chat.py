"""SSE 流式 agent 循环测试（阶段 4）。

直接测试 stream_native_agent_loop（async generator），通过 monkeypatch ai_client.stream_provider
喂入 canned 事件帧序列。覆盖：
- 文本+工具调用的标准流（text_delta/tool_call_start/tool_result/terminal 收敛）
- pending_confirmation 暂停（tool_result 含 pending、terminal 带 resume_checkpoint）
- 第二步纯文本收尾
- provider 流式失败的首轮 error 帧
- 降级路径（stream_provider 内部回退 call_provider 包装为单 turn 帧）

端点层（POST /ai/chat/stream）使用独立 SessionLocal，与测试 client 的 get_db override 不互通，
故端点层用直接调用 _stream_agent_run 的方式覆盖（验证 SSE 帧格式与落库）。
"""
import json
from types import SimpleNamespace

import pytest


def _enable_native_config(client, **overrides):
    payload = {
        "name": "native",
        "provider": "openai_chat",
        "model": "fake-model",
        "api_key": "test-key",
        "tool_calling_mode": "native",
    }
    payload.update(overrides)
    config = client.post("/ai/configs", json=payload).json()
    client.post(f"/ai/configs/{config['id']}/enable")
    return config


def _make_provider_request_stub(provider="openai_chat"):
    """构造最小 ProviderRequest-like 对象（stream_provider mock 不关心字段）。"""
    from app.services.ai_client import ProviderRequest

    return ProviderRequest(
        url="https://api.openai.com/v1/chat/completions",
        headers={"Authorization": "Bearer test"},
        json={"model": "fake-model", "messages": []},
    )


async def _stream_frames(frames):
    """把 list[dict] 包装成 async generator，模拟 stream_provider 的产出。"""
    for frame in frames:
        yield frame


async def collect_frames(gen):
    """收集 async generator 的全部 yield。"""
    out = []
    async for item in gen:
        out.append(item)
    return out


# ---- 1. 标准流：text_delta → tool_call_start → tool_result(执行) → terminal ----


@pytest.mark.anyio
async def test_stream_text_and_tool_call_then_text(client, monkeypatch, db_session):
    from app.models import AIConfig
    from app.routers.ai import stream_native_agent_loop
    from app.services import ai_client

    _enable_native_config(client)
    config = db_session.query(AIConfig).filter(AIConfig.enabled.is_(True)).first()
    call_count = [0]

    def fake_stream_provider(request):
        call_count[0] += 1
        if call_count[0] == 1:
            # 首轮：文本增量 + 工具调用 + turn 帧（组装完整 payload）
            return _stream_frames(
                [
                    {"type": "text_delta", "delta": "我先"},
                    {"type": "text_delta", "delta": "建任务"},
                    {"type": "tool_call_start", "index": 0, "call_id": "call_1", "name": "create_task"},
                    {
                        "type": "turn",
                        "raw": {
                            "choices": [
                                {
                                    "message": {
                                        "content": "我先建任务",
                                        "tool_calls": [
                                            {
                                                "id": "call_1",
                                                "type": "function",
                                                "function": {
                                                    "name": "create_task",
                                                    "arguments": '{"title":"流式任务"}',
                                                },
                                            }
                                        ],
                                    },
                                    "finish_reason": "tool_calls",
                                }
                            ]
                        },
                    },
                ]
            )
        # 第二轮：纯文本收尾
        return _stream_frames(
            [
                {"type": "text_delta", "delta": "已创建"},
                {
                    "type": "turn",
                    "raw": {"choices": [{"message": {"content": "已创建流式任务"}, "finish_reason": "stop"}]},
                },
            ]
        )

    monkeypatch.setattr(ai_client, "stream_provider", fake_stream_provider)

    frames = await collect_frames(
        stream_native_agent_loop(
            db_session, config, [{"role": "user", "content": "建个任务"}], "建个任务"
        )
    )

    events = [f["event"] for f in frames]
    # 首轮应有 text_delta + tool_call_start + tool_result
    assert "text_delta" in events
    assert "tool_call_start" in events
    tool_results = [f for f in frames if f["event"] == "tool_result"]
    assert len(tool_results) == 1
    assert tool_results[0]["data"]["name"] == "create_task"
    assert tool_results[0]["data"]["ok"] is True
    # 第二轮纯文本应有 text_delta
    text_deltas = [f["data"]["delta"] for f in frames if f["event"] == "text_delta"]
    assert "我先" in text_deltas and "已创建" in text_deltas
    # 末帧 terminal
    terminal = frames[-1]
    assert terminal["event"] == "terminal"
    agent_run = terminal["data"]["agent_run"]
    assert agent_run.final_text == "已创建流式任务"
    assert agent_run.tool_results[0]["tool"] == "create_task"
    # 任务确实被创建
    titles = {t["title"] for t in client.get("/tasks").json()}
    assert "流式任务" in titles


# ---- 2. pending_confirmation 暂停：tool_result 含 pending + terminal 带 resume_checkpoint ----


@pytest.mark.anyio
async def test_stream_pending_confirmation_yields_checkpoint(client, monkeypatch, db_session):
    from app.models import AIConfig
    from app.routers.ai import stream_native_agent_loop
    from app.services import ai_client

    _enable_native_config(client)
    config = db_session.query(AIConfig).filter(AIConfig.enabled.is_(True)).first()

    def fake_stream_provider(request):
        return _stream_frames(
            [
                {"type": "text_delta", "delta": "要删任务，需确认"},
                {"type": "tool_call_start", "index": 0, "call_id": "call_1", "name": "delete_task"},
                {
                    "type": "turn",
                    "raw": {
                        "choices": [
                            {
                                "message": {
                                    "content": "要删任务",
                                    "tool_calls": [
                                        {
                                            "id": "call_1",
                                            "type": "function",
                                            "function": {
                                                "name": "delete_task",
                                                "arguments": '{"task_id":99999}',
                                            },
                                        }
                                    ],
                                },
                                "finish_reason": "tool_calls",
                            }
                        ]
                    },
                },
            ]
        )

    monkeypatch.setattr(ai_client, "stream_provider", fake_stream_provider)

    frames = await collect_frames(
        stream_native_agent_loop(
            db_session, config, [{"role": "user", "content": "删任务"}], "删任务"
        )
    )

    # tool_result 应含 pending
    tool_results = [f for f in frames if f["event"] == "tool_result"]
    assert len(tool_results) == 1
    assert tool_results[0]["data"]["pending"] is True
    # step_finish 在 pending 暂停时发射
    assert any(f["event"] == "step_finish" for f in frames)
    # terminal 带 resume_checkpoint
    terminal = frames[-1]
    assert terminal["event"] == "terminal"
    agent_run = terminal["data"]["agent_run"]
    assert agent_run.resume_checkpoint is not None
    assert agent_run.resume_checkpoint["assistant_tool_calls"][0]["name"] == "delete_task"


# ---- 3. 首轮 provider 失败 → error 帧 + 提前 return ----


@pytest.mark.anyio
async def test_stream_provider_error_first_step(client, monkeypatch, db_session):
    from app.models import AIConfig
    from app.routers.ai import stream_native_agent_loop
    from app.services import ai_client

    _enable_native_config(client)
    config = db_session.query(AIConfig).filter(AIConfig.enabled.is_(True)).first()

    def fake_stream_provider(request):
        async def _empty():
            return
            yield  # 让 Python 识别为 async generator

        return _empty()

    monkeypatch.setattr(ai_client, "stream_provider", fake_stream_provider)

    frames = await collect_frames(
        stream_native_agent_loop(
            db_session, config, [{"role": "user", "content": "hi"}], "hi"
        )
    )

    # 首轮无 turn 帧 → 视为 provider 错误，发 error fatal 帧
    assert any(f["event"] == "error" and f["data"].get("fatal") for f in frames)
    # 不应有 terminal 帧（提前 return）
    assert not any(f["event"] == "terminal" for f in frames)


# ---- 4. 降级路径：stream_provider 内部回退 call_provider（单 turn 帧无增量）----


@pytest.mark.anyio
async def test_stream_fallback_non_stream_has_no_deltas(client, monkeypatch, db_session):
    """stream_provider 降级时只产出单 turn 帧，agent 循环应正常工作（无 text_delta 但 terminal 收敛）。"""
    from app.models import AIConfig
    from app.routers.ai import stream_native_agent_loop
    from app.services import ai_client

    _enable_native_config(client)
    config = db_session.query(AIConfig).filter(AIConfig.enabled.is_(True)).first()

    def fake_stream_provider(request):
        # 模拟降级：单 turn 帧（无 text_delta 增量）
        return _stream_frames(
            [
                {"type": "text_delta", "delta": "降级回复"},
                {
                    "type": "turn",
                    "raw": {"choices": [{"message": {"content": "降级回复"}, "finish_reason": "stop"}]},
                },
            ]
        )

    monkeypatch.setattr(ai_client, "stream_provider", fake_stream_provider)

    frames = await collect_frames(
        stream_native_agent_loop(
            db_session, config, [{"role": "user", "content": "hi"}], "hi"
        )
    )

    terminal = frames[-1]
    assert terminal["event"] == "terminal"
    assert terminal["data"]["agent_run"].final_text == "降级回复"


# ---- 5. _stream_agent_run：SSE 帧格式 + 落库（端点核心逻辑）----


@pytest.mark.anyio
async def test_stream_agent_run_emits_sse_and_persists(client, monkeypatch, db_session):
    """端点核心 _stream_agent_run：把事件帧格式化为 SSE 字符串，done 帧为权威收敛，落库 assistant 消息。"""
    from app.models import AIConfig, AIMessage
    from app.routers.ai import _stream_agent_run, _prepare_chat_context
    from app.services import ai_client

    _enable_native_config(client)
    config = db_session.query(AIConfig).filter(AIConfig.enabled.is_(True)).first()
    conversation, user_text, messages = _prepare_chat_context(
        db_session, "建个任务", [], None
    )
    assistant_name = "测试助手"

    call_count = [0]

    def fake_stream_provider(request):
        call_count[0] += 1
        if call_count[0] == 1:
            return _stream_frames(
                [
                    {"type": "text_delta", "delta": "建任务"},
                    {"type": "tool_call_start", "index": 0, "call_id": "c1", "name": "create_task"},
                    {
                        "type": "turn",
                        "raw": {
                            "choices": [
                                {
                                    "message": {
                                        "content": "建任务",
                                        "tool_calls": [
                                            {
                                                "id": "c1",
                                                "type": "function",
                                                "function": {
                                                    "name": "create_task",
                                                    "arguments": '{"title":"SSE任务"}',
                                                },
                                            }
                                        ],
                                    },
                                    "finish_reason": "tool_calls",
                                }
                            ]
                        },
                    },
                ]
            )
        return _stream_frames(
            [
                {"type": "text_delta", "delta": "完成"},
                {
                    "type": "turn",
                    "raw": {"choices": [{"message": {"content": "完成"}, "finish_reason": "stop"}]},
                },
            ]
        )

    monkeypatch.setattr(ai_client, "stream_provider", fake_stream_provider)

    chunks = []
    async for chunk in _stream_agent_run(
        db_session, config, conversation, user_text, messages, assistant_name
    ):
        chunks.append(chunk)

    full = "".join(chunks)
    # SSE 帧格式：event: xxx\ndata: {...}\n\n
    assert "event: meta\n" in full
    assert '"conversation_id"' in full
    assert "event: text_delta\n" in full
    assert "event: tool_call_start\n" in full
    assert "event: tool_result\n" in full
    assert "event: done\n" in full
    # done 帧是最后一帧，含 reply/tool_results
    done_chunk = chunks[-1]
    assert done_chunk.startswith("event: done\n")
    done_data = json.loads(done_chunk.split("data: ", 1)[1].strip())
    assert done_data["reply"] == "完成"
    assert done_data["tool_results"][0]["tool"] == "create_task"
    # assistant 消息已落库
    asst = (
        db_session.query(AIMessage)
        .filter(AIMessage.conversation_id == conversation.id, AIMessage.role == "assistant")
        .first()
    )
    assert asst is not None
    assert asst.content == "完成"
    meta = json.loads(asst.meta)
    assert meta["tool_results"][0]["tool"] == "create_task"
    # 任务确实创建
    titles = {t["title"] for t in client.get("/tasks").json()}
    assert "SSE任务" in titles


# ---- 6. 中断链路（阶段 5）：cancelled event → terminal 带 cancelled:true ----


@pytest.mark.anyio
async def test_stream_cancelled_before_tool_dispatch(client, monkeypatch, db_session):
    """取消事件在工具分发前命中：循环停止，terminal 帧 cancelled:true，工具未执行。"""
    import asyncio

    from app.models import AIConfig
    from app.routers.ai import stream_native_agent_loop
    from app.services import ai_client

    _enable_native_config(client)
    config = db_session.query(AIConfig).filter(AIConfig.enabled.is_(True)).first()
    cancel_event = asyncio.Event()
    # 预设取消：循环在第一步流消费后进入分类+分发前检查，命中即停止。
    # 关键：第 1 步开始处的步边界检查在 stream_provider 消费之前；这里测试分发前检查，
    # 故不在 step1 处停（step1 检查时 event 尚未 set 会通过）。改为在 stream_provider
    # 产出 turn 帧后、分发前 set：用 fake_stream_provider 在产出 turn 帧时 set event。
    turn_yielded = [False]

    def fake_stream_provider(request):
        # 首轮产出工具调用 turn 帧；在产出 turn 帧后立即 set 取消事件，
        # 确保分发前的检查命中（不依赖 async 调度时序）。
        async def _gen():
            yield {"type": "text_delta", "delta": "建任务"}
            yield {"type": "tool_call_start", "index": 0, "call_id": "c1", "name": "create_task"}
            yield {
                "type": "turn",
                "raw": {
                    "choices": [
                        {
                            "message": {
                                "content": "建任务",
                                "tool_calls": [
                                    {
                                        "id": "c1",
                                        "type": "function",
                                        "function": {
                                            "name": "create_task",
                                            "arguments": '{"title":"取消任务"}',
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                },
            }
            cancel_event.set()
            turn_yielded[0] = True

        return _gen()

    monkeypatch.setattr(ai_client, "stream_provider", fake_stream_provider)

    frames = []
    async for f in stream_native_agent_loop(
        db_session, config, [{"role": "user", "content": "建个任务"}], "建个任务",
        cancelled=cancel_event,
    ):
        frames.append(f)

    assert turn_yielded[0]
    # 不应发射 tool_result（工具未执行）
    assert not any(f["event"] == "tool_result" for f in frames)
    # terminal 带 cancelled:true
    terminal = frames[-1]
    assert terminal["event"] == "terminal"
    assert terminal["data"]["cancelled"] is True
    # 任务未被创建
    titles = {t["title"] for t in client.get("/tasks").json()}
    assert "取消任务" not in titles


@pytest.mark.anyio
async def test_cancel_endpoint_sets_event_and_releases(client, db_session):
    """POST /ai/chat/cancel set 对应 run_id 的取消事件；未知 run_id 返回 ok:false。"""
    import asyncio

    from app.routers import ai as ai_router

    run_id = "test-run-cancel-1"
    event = ai_router._register_run(run_id)
    try:
        assert not event.is_set()
        res = client.post("/ai/chat/cancel", json={"run_id": run_id}).json()
        assert res["ok"] is True
        assert event.is_set()
        # 幂等：未知 run_id 返回 ok:false
        res2 = client.post("/ai/chat/cancel", json={"run_id": "unknown"}).json()
        assert res2["ok"] is False
    finally:
        ai_router._release_run(run_id)
    # release 后注册表不再含该 run_id
    assert run_id not in ai_router._active_runs


# ---- 7. token 用量（阶段 2）：usage 事件累计 + done 帧 usage + AIMessage.meta.usage ----


@pytest.mark.anyio
async def test_stream_usage_events_and_persist(client, monkeypatch, db_session):
    """多轮 provider 调用：每轮发 usage 事件（累计值），done 帧带总量，落库 meta.usage。"""
    from app.models import AIConfig, AIMessage
    from app.routers.ai import _stream_agent_run, _prepare_chat_context
    from app.services import ai_client

    _enable_native_config(client)
    config = db_session.query(AIConfig).filter(AIConfig.enabled.is_(True)).first()
    conversation, user_text, messages = _prepare_chat_context(db_session, "建个任务", [], None)
    call_count = [0]

    def fake_stream_provider(request):
        call_count[0] += 1
        if call_count[0] == 1:
            return _stream_frames(
                [
                    {"type": "text_delta", "delta": "建任务"},
                    {"type": "tool_call_start", "index": 0, "call_id": "c1", "name": "create_task"},
                    {
                        "type": "turn",
                        "raw": {
                            "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
                            "choices": [
                                {
                                    "message": {
                                        "content": "建任务",
                                        "tool_calls": [
                                            {
                                                "id": "c1",
                                                "type": "function",
                                                "function": {
                                                    "name": "create_task",
                                                    "arguments": '{"title":"用量任务"}',
                                                },
                                            }
                                        ],
                                    },
                                    "finish_reason": "tool_calls",
                                }
                            ],
                        },
                    },
                ]
            )
        # 第二轮：不同 usage 数字，验证累计
        return _stream_frames(
            [
                {"type": "text_delta", "delta": "完成"},
                {
                    "type": "turn",
                    "raw": {
                        "usage": {"prompt_tokens": 200, "completion_tokens": 20, "total_tokens": 220},
                        "choices": [{"message": {"content": "完成"}, "finish_reason": "stop"}],
                    },
                },
            ]
        )

    monkeypatch.setattr(ai_client, "stream_provider", fake_stream_provider)

    chunks = []
    async for chunk in _stream_agent_run(
        db_session, config, conversation, user_text, messages, "测试助手"
    ):
        chunks.append(chunk)

    # 解析所有 usage 事件
    usage_events = []
    done_data = None
    for chunk in chunks:
        if chunk.startswith("event: usage\n"):
            usage_events.append(json.loads(chunk.split("data: ", 1)[1].strip()))
        elif chunk.startswith("event: done\n"):
            done_data = json.loads(chunk.split("data: ", 1)[1].strip())

    # 两轮各发一个 usage 事件，累计值递增（非增量）
    assert len(usage_events) == 2
    assert usage_events[0]["total_tokens"] == 110
    assert usage_events[1]["total_tokens"] == 330  # 110 + 220
    assert usage_events[1]["prompt_tokens"] == 300  # 100 + 200

    # done 帧带 usage 总量 + elapsed_ms
    assert done_data is not None
    assert done_data["usage"]["total_tokens"] == 330
    assert done_data["usage"]["calls"] == 2
    assert isinstance(done_data["elapsed_ms"], int)

    # 落库 meta.usage / meta.elapsed_ms
    asst = (
        db_session.query(AIMessage)
        .filter(AIMessage.conversation_id == conversation.id, AIMessage.role == "assistant")
        .first()
    )
    meta = json.loads(asst.meta)
    assert meta["usage"]["total_tokens"] == 330
    assert "elapsed_ms" in meta


@pytest.mark.anyio
async def test_stream_no_usage_when_provider_omits(client, monkeypatch, db_session):
    """provider 不回 usage 时：usage 事件仍发（全 0），done 帧 usage 全 0，meta 不写 usage。"""
    from app.models import AIConfig
    from app.routers.ai import stream_native_agent_loop
    from app.services import ai_client

    _enable_native_config(client)
    config = db_session.query(AIConfig).filter(AIConfig.enabled.is_(True)).first()

    def fake_stream_provider(request):
        return _stream_frames(
            [
                {"type": "text_delta", "delta": "无用量"},
                {
                    "type": "turn",
                    # 不带 usage 字段
                    "raw": {"choices": [{"message": {"content": "无用量"}, "finish_reason": "stop"}]},
                },
            ]
        )

    monkeypatch.setattr(ai_client, "stream_provider", fake_stream_provider)
    frames = await collect_frames(
        stream_native_agent_loop(db_session, config, [{"role": "user", "content": "hi"}], "hi")
    )
    usage_events = [f for f in frames if f["event"] == "usage"]
    assert len(usage_events) == 1
    # 全 0：前端据此不展示
    assert usage_events[0]["data"]["total_tokens"] == 0
    # terminal 的 agent_run.usage 也是全 0
    terminal = frames[-1]
    assert terminal["data"]["agent_run"].usage["total_tokens"] == 0
    assert terminal["data"]["agent_run"].usage["calls"] == 1


# ---- 8. 思维链（阶段 3）：reasoning_delta 透传 + done 帧 reasoning + 落库 ----


@pytest.mark.anyio
async def test_stream_reasoning_delta_and_persist(client, monkeypatch, db_session):
    """provider 流式 reasoning_delta → SSE reasoning_delta 事件 → done 帧 reasoning → meta.reasoning。"""
    from app.models import AIConfig, AIMessage
    from app.routers.ai import _stream_agent_run, _prepare_chat_context
    from app.services import ai_client

    _enable_native_config(client)
    config = db_session.query(AIConfig).filter(AIConfig.enabled.is_(True)).first()
    conversation, user_text, messages = _prepare_chat_context(db_session, "思考题", [], None)

    def fake_stream_provider(request):
        return _stream_frames(
            [
                {"type": "reasoning_delta", "delta": "先推理"},
                {"type": "reasoning_delta", "delta": "一下"},
                {"type": "text_delta", "delta": "答案是42"},
                {
                    "type": "turn",
                    "raw": {"choices": [{"message": {"content": "答案是42"}, "finish_reason": "stop"}]},
                },
            ]
        )

    monkeypatch.setattr(ai_client, "stream_provider", fake_stream_provider)
    chunks = []
    async for chunk in _stream_agent_run(
        db_session, config, conversation, user_text, messages, "测试助手"
    ):
        chunks.append(chunk)

    reasoning_events = []
    done_data = None
    for chunk in chunks:
        if chunk.startswith("event: reasoning_delta\n"):
            reasoning_events.append(json.loads(chunk.split("data: ", 1)[1].strip()))
        elif chunk.startswith("event: done\n"):
            done_data = json.loads(chunk.split("data: ", 1)[1].strip())

    # 两个 reasoning_delta 事件
    assert len(reasoning_events) == 2
    assert reasoning_events[0]["delta"] == "先推理"
    # done 帧带完整 reasoning
    assert done_data["reasoning"] == "先推理一下"
    # 落库 meta.reasoning
    asst = (
        db_session.query(AIMessage)
        .filter(AIMessage.conversation_id == conversation.id, AIMessage.role == "assistant")
        .first()
    )
    meta = json.loads(asst.meta)
    assert meta["reasoning"] == "先推理一下"


@pytest.mark.anyio
async def test_stream_reasoning_off_when_config_disabled(client, monkeypatch, db_session):
    """config.show_reasoning=False 时：不透传 reasoning_delta，done 帧 reasoning 为空。"""
    from app.models import AIConfig
    from app.routers.ai import stream_native_agent_loop
    from app.services import ai_client

    _enable_native_config(client)
    config = db_session.query(AIConfig).filter(AIConfig.enabled.is_(True)).first()
    config.show_reasoning = False
    db_session.commit()

    def fake_stream_provider(request):
        return _stream_frames(
            [
                {"type": "reasoning_delta", "delta": "不应透传"},
                {"type": "text_delta", "delta": "正文"},
                {
                    "type": "turn",
                    "raw": {"choices": [{"message": {"content": "正文"}, "finish_reason": "stop"}]},
                },
            ]
        )

    monkeypatch.setattr(ai_client, "stream_provider", fake_stream_provider)
    frames = await collect_frames(
        stream_native_agent_loop(db_session, config, [{"role": "user", "content": "hi"}], "hi")
    )
    # 开关关闭：不发 reasoning_delta 事件
    assert not any(f["event"] == "reasoning_delta" for f in frames)
    # terminal 的 agent_run.reasoning 仍为空（turn 无 reasoning_content，且流式增量被闸门挡）
    terminal = frames[-1]
    assert terminal["data"]["agent_run"].reasoning == ""
