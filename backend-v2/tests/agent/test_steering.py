"""Codex 式运行中插话：钩子注入窗口、当轮可见性、持久化、SteerAccepted 事件。

语义对照 openai/codex 的 pending input drain：
- 首个模型请求前不注入（本轮新鲜输入先被采样）；
- 工具调用结束后的下一次模型请求前抽干队列，作为新的用户输入当轮消化；
- 模型不再调工具直接收尾时消息留在队列（前端回退为常规发送）。

持久化机制：钩子返回的消息列表由 pydantic-ai 写回 state 历史（注入即持久化），
checkpoint 快照天然包含插话；模型看到的采样视图由框架合并末尾连续 ModelRequest
（工具结果在前、用户消息在后）。"""
import asyncio
import json

from pydantic_ai.messages import (
    ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart, UserPromptPart)
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from zhishi.agent.runtime import AgentRuntime
from zhishi.domain.models import AIConversation, AIMessage


def make_runtime(db, model):
    return AgentRuntime(model=model, db=db)


def steered_texts(messages):
    """采样视图/历史里插话 UserPromptPart 的内容列表（按出现顺序）。"""
    return [str(p.content) for m in messages for p in m.parts
            if isinstance(p, UserPromptPart) and str(p.content).startswith('【用户插话】')]


def new_conversation(db) -> int:
    conv = AIConversation(title='插话测试')
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv.id


def tool_script(step, seen, rounds, final='已按插话调整'):
    """FunctionModel 脚本：前 rounds 次请求各调一次 get_current_time，然后收尾。"""
    async def scripted(messages, info):
        step['n'] += 1
        seen.append(list(messages))
        if step['n'] <= rounds:
            yield {0: DeltaToolCall(name='get_current_time', json_args='{}',
                                    tool_call_id=f'tc{step["n"]}')}
        else:
            yield final
    return scripted


async def test_injection_after_tool_call_and_persistence(db):
    """插话在工具调用后的下一次模型请求前注入：模型当轮可见（采样视图里紧跟
    工具结果）；落库后是独立 ModelRequest，位于工具结果请求与最终回复之间；
    SteerAccepted 凭 token 外发；独立 user 行即时落库。"""
    queue: asyncio.Queue = asyncio.Queue()
    queue.put_nowait(('改用下周提醒', 'tok-1'))
    step = {'n': 0}
    seen = []

    rt = make_runtime(db, FunctionModel(stream_function=tool_script(step, seen, rounds=1)))
    events = [e async for e in rt.run_stream(user_text='现在几点',
                                             conversation_id=new_conversation(db),
                                             steer_queue=queue)]
    conv_id = events[0]['conversation_id']

    # 请求 1（视图中尚无 ModelResponse）：不注入——本轮新鲜输入先被采样
    assert steered_texts(seen[0]) == []
    # 请求 2（工具结果之后）：插话在末尾合并请求中紧跟工具结果
    assert steered_texts(seen[1]) == ['【用户插话】改用下周提醒']
    last = seen[1][-1]
    assert isinstance(last, ModelRequest)
    part_kinds = [type(p).__name__ for p in last.parts]
    assert part_kinds.index('ToolReturnPart') < part_kinds.index('UserPromptPart')

    # SteerAccepted 事件：前端凭 token 对账，message_id 指向独立 user 行
    accepted = [e for e in events if e['type'] == 'steer_accepted']
    assert len(accepted) == 1
    assert accepted[0]['token'] == 'tok-1'
    assert accepted[0]['text'] == '改用下周提醒'
    assert accepted[0]['message_id'] > 0

    msgs = db.query(AIMessage).filter_by(conversation_id=conv_id).all()
    steered_rows = [m for m in msgs if m.id == accepted[0]['message_id']]
    assert len(steered_rows) == 1 and steered_rows[0].role == 'user'
    display = json.loads(steered_rows[0].display_json)
    assert display['steered'] is True and display['run_id'] == events[0]['run_id']

    # 持久化历史：工具结果请求 → 插话（独立消息） → 最终回复
    from pydantic_ai.messages import ModelMessagesTypeAdapter
    assistant = next(m for m in msgs if m.role == 'assistant' and m.history_json != '[]')
    history = ModelMessagesTypeAdapter.validate_json(assistant.history_json)
    tool_return_idx = next(i for i, m in enumerate(history)
                           for p in m.parts if isinstance(p, ToolReturnPart))
    steered_idx = next(i for i, m in enumerate(history) if steered_texts([m]))
    assert steered_idx == tool_return_idx + 1
    assert steered_idx == len(history) - 2   # 最终回复之前
    assert steered_texts(history) == ['【用户插话】改用下周提醒']   # 恰好一次


async def test_multiple_injections_stay_visible_without_duplication(db):
    """同一 run 多次插话 / 多次工具调用：注入已随 state 持久化，后续请求天然可见
    ——不重放（重放会双份），每条插话在整个历史与采样视图中恰好一次。"""
    queue: asyncio.Queue = asyncio.Queue()
    queue.put_nowait(('第一条插话', 'tok-a'))
    step = {'n': 0}
    seen = []

    async def scripted(messages, info):
        step['n'] += 1
        seen.append(list(messages))
        if step['n'] == 1:
            yield {0: DeltaToolCall(name='get_current_time', json_args='{}', tool_call_id='t1')}
        if step['n'] == 2:
            queue.put_nowait(('第二条插话', 'tok-b'))   # 模拟工具执行期间前端继续插话
            yield {0: DeltaToolCall(name='get_current_time', json_args='{}', tool_call_id='t2')}
        if step['n'] == 3:
            yield '收尾'

    rt = make_runtime(db, FunctionModel(stream_function=scripted))
    events = [e async for e in rt.run_stream(user_text='开始', conversation_id=new_conversation(db),
                                             steer_queue=queue)]
    assert [e['token'] for e in events if e['type'] == 'steer_accepted'] == ['tok-a', 'tok-b']
    assert steered_texts(seen[1]) == ['【用户插话】第一条插话']
    # 请求 3：两条插话各一次，分别紧跟两次工具结果（框架合并的采样视图）
    assert steered_texts(seen[2]) == ['【用户插话】第一条插话', '【用户插话】第二条插话']

    from pydantic_ai.messages import ModelMessagesTypeAdapter
    assistant = db.query(AIMessage).filter_by(role='assistant').order_by(AIMessage.id.desc()).first()
    history = ModelMessagesTypeAdapter.validate_json(assistant.history_json)
    assert steered_texts(history) == ['【用户插话】第一条插话', '【用户插话】第二条插话']
    assert steered_texts([history[-2]]) == ['【用户插话】第二条插话']
    assert history[-1].parts[0].content == '收尾'
    assert any(isinstance(p, ToolReturnPart) and p.tool_call_id == 't2'
               for p in history[-3].parts)


async def test_no_injection_when_model_finishes_without_tools(db):
    """模型不再调工具直接收尾：消息留在队列、无事件、无独立 user 行——
    前端凭「无 SteerAccepted」回退为常规发送。"""
    queue: asyncio.Queue = asyncio.Queue()
    queue.put_nowait(('这条应该排队', 'tok-x'))
    step = {'n': 0}
    seen = []

    rt = make_runtime(db, FunctionModel(stream_function=tool_script(step, seen, rounds=0,
                                                                    final='直接回答')))
    events = [e async for e in rt.run_stream(user_text='你好', conversation_id=new_conversation(db),
                                             steer_queue=queue)]

    assert steered_texts(seen[0]) == []
    assert not [e for e in events if e['type'] == 'steer_accepted']
    assert queue.qsize() == 1
    msgs = db.query(AIMessage).filter_by(conversation_id=events[0]['conversation_id']).all()
    assert not [m for m in msgs if m.role == 'user'
                and json.loads(m.display_json).get('steered')]
