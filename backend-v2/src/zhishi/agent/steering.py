"""Codex 式运行中插话（steering）。

run 活跃时受理的用户消息进入会话级 steer 队列；`before_model_request` 钩子在
「工具调用结束后的下一次模型请求前」把队列抽干，作为新的用户消息追加进采样
视图——模型当轮即可消化，turn 不结束（语义对照 openai/codex 的 input_queue
+ turn.rs 的 pending input drain）。

注入即持久化：pydantic-ai 的 `_prepare_request` 把钩子返回的消息列表整个写回
state 历史（message_history[:] = messages），因此注入的 ModelRequest 天然进入
后续请求与落库快照（checkpoint / 收尾直接存 state），既不需要账本重放，也不
需要落库缝合。模型看到的采样视图由框架把末尾连续 ModelRequest 合并（工具结果
在前、用户消息在后），插话紧跟本轮工具结果之后。

边界：
- 首个请求前不注入——本轮新鲜输入先被采样（Codex 的 turn-start 延迟排空同款）；
  若模型此后未再调工具直接收尾，消息留在队列，由前端回退为常规发送。
- 能力链序在本文件使用处位于 compaction 之前：压缩看到的是已含插话的视图，
  摘要不丢内容。
- 插话持久化为独立 user 行（display_json['steered']=True），时间线由消息路由
  按 run_id 归位到该轮助手行之前。
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import replace

from zhishi.agent.events import SteerAccepted


def _frame(model_cls, **fields) -> dict:
    return model_cls(**fields).model_dump()


class SteerInjector:
    """一次 run 的插话注入器：受理队列 → 模型采样视图（写回 state 即持久化）。"""

    def __init__(self, *, conversation_id: int, run_id: str, queue, emit, session_factory):
        self.conversation_id = conversation_id
        self.run_id = run_id
        self.queue = queue            # asyncio.Queue[(text, token)]，steer 端点投递
        self.emit = emit              # run 的 SSE 事件队列（SteerAccepted 由此到前端）
        self.session_factory = session_factory

    def capability(self):
        from pydantic_ai.capabilities import Hooks
        return Hooks(before_model_request=self.hook)

    async def hook(self, ctx, request_context):
        from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart

        messages = list(request_context.messages)
        # 首个请求（本轮用户消息尚未被模型见过）不注入，先让新鲜输入被采样
        if not any(isinstance(m, ModelResponse) for m in messages):
            return request_context
        while True:
            try:
                text, token = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            message_id = await asyncio.to_thread(self._persist_row, text)
            self.emit.put_nowait(_frame(SteerAccepted, text=text,
                                        message_id=message_id, token=token))
            messages.append(ModelRequest(parts=[UserPromptPart(f'【用户插话】{text}')]))
        if len(messages) == len(request_context.messages):
            return request_context
        return replace(request_context, messages=messages)

    def _persist_row(self, text: str) -> int:
        """插话即时落为独立 user 行（独立事务，照工具执行惯例走 session_factory）。"""
        from zhishi.domain.models import AIMessage
        with self.session_factory() as db:
            row = AIMessage(
                conversation_id=self.conversation_id, role='user', history_json='[]',
                display_json=json.dumps({'text': text, 'steered': True, 'run_id': self.run_id},
                                        ensure_ascii=False))
            db.add(row)
            db.commit()
            return row.id
