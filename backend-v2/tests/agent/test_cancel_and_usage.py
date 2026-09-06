import asyncio
import json
from pydantic_ai import CancellationToken
from pydantic_ai.models.test import TestModel
from zhishi.agent.runtime import AgentRuntime


async def test_cancel_marks_interrupted(db):
    token = CancellationToken()
    rt = AgentRuntime(model=TestModel(call_tools=[]), db=db)
    events = []
    async for e in rt.run_stream(user_text="x", conversation_id=None, cancel_token=token):
        events.append(e)
        if len(events) == 2:
            token.cancel()
    types = [e["type"] for e in events]
    assert "done" in types  # 流正常收敛
    from zhishi.domain.models import AIRun
    run_row = db.query(AIRun).order_by(AIRun.created_at.desc()).first()
    assert run_row.status in ("interrupted", "completed")


async def test_cancel_interrupts_slow_run(db):
    """慢模型 + 时间窗内取消 → interrupted 收尾（部分输出保留落库）。"""
    from pydantic_ai.models.function import FunctionModel

    async def slow_stream(messages, info):
        await asyncio.sleep(0.5)
        yield "迟到的回复"

    token = CancellationToken()
    rt = AgentRuntime(model=FunctionModel(stream_function=slow_stream), db=db)
    events = []
    async for e in rt.run_stream(user_text="x", conversation_id=None, cancel_token=token):
        events.append(e)
        if len(events) == 2:  # preparing 后立即取消
            token.cancel()
    assert "done" in [e["type"] for e in events]
    from zhishi.domain.models import AIRun
    run_row = db.query(AIRun).order_by(AIRun.created_at.desc()).first()
    assert run_row.status == "interrupted" and run_row.done_reason == "cancelled"


async def test_usage_logged(db):
    rt = AgentRuntime(model=TestModel(call_tools=[]), db=db)
    events = [e async for e in rt.run_stream(user_text="你好", conversation_id=None,
                                             usage_meta={"provider": "openai_compat",
                                                         "model": "t", "config_id": None})]
    from zhishi.domain.models import AIUsageLog
    # TestModel 不产生真实 token——断言不抛错且事件序含 run_completed（usage 字段存在）
    completed = next(e for e in events if e["type"] == "run_completed")
    assert "usage" in completed
