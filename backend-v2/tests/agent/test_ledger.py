import json

import pytest
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from zhishi.agent.permissions import classify
from zhishi.agent.runtime import AgentRuntime
from zhishi.agent.tools.registry import get_spec
from zhishi.domain.ledger import service


def test_permissions(db):
    assert get_spec('record_transaction') is not None
    assert classify(db, 'record_transaction', {}) == 'allow'
    assert classify(db, 'summarize_transactions', {}) == 'allow'
    assert classify(db, 'delete_transaction', {}) == 'confirm'


@pytest.mark.asyncio
async def test_model_tool_records_and_summarizes_real_ledger(db):
    calls = 0
    async def model(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            yield {0: DeltaToolCall(name='record_transaction', json_args=json.dumps({'entry': {
                'day': '2026-09-05', 'direction': 'expense', 'amount': '28.50',
                'category': '餐饮', 'idempotency_key': 'conversation-lunch-1'}}), tool_call_id='record')}
        elif calls == 2:
            yield {0: DeltaToolCall(name='summarize_transactions', json_args=json.dumps({
                'start': '2026-09-01', 'end': '2026-09-30'}), tool_call_id='sum')}
        else:
            assert '28.50' in str(messages)
            yield '已记下本次午饭支出 28.50 元。'
    runtime = AgentRuntime(model=FunctionModel(stream_function=model), db=db)
    events = [e async for e in runtime.run_stream(user_text='午饭花了28.50元', conversation_id=None)]
    assert not [e for e in events if e['type'] == 'run_error']
    assert service.list_entries(db).total == 1
    assert service.list_entries(db).items[0].amount == '28.50'
