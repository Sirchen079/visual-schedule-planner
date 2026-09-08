import asyncio
import json
from datetime import date
from decimal import Decimal

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic import ValidationError
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_core import SchemaValidator, core_schema

from zhishi.agent.runtime import AgentDeps, AgentRuntime
from zhishi.domain.ledger.bill_schemas import BillCreate, BillPayment, BillUpdate
from zhishi.domain.ledger.schemas import EntryCreate, EntryReplace


def check_patterns(schema):
    if isinstance(schema, dict):
        if 'pattern' in schema:
            SchemaValidator(core_schema.str_schema(pattern=schema['pattern'], regex_engine='rust-regex'))
        for value in schema.values():
            check_patterns(value)
    elif isinstance(schema, list):
        for value in schema:
            check_patterns(value)


@pytest.mark.parametrize('model', [EntryCreate, EntryReplace, BillCreate, BillUpdate, BillPayment])
@pytest.mark.parametrize('mode', ['validation', 'serialization'])
def test_money_schema_patterns_compile_without_lookaround(model, mode):
    check_patterns(model.model_json_schema(mode=mode))


@pytest.mark.parametrize('model,fields', [
    (EntryCreate, {'day': date(2026, 1, 1), 'direction': 'expense'}),
    (EntryReplace, {'day': date(2026, 1, 1), 'direction': 'expense', 'version': 1}),
    (BillCreate, {'title': '示例账单', 'first_due': date(2026, 1, 1), 'request_key': 'test'}),
    (BillUpdate, {'title': '示例账单', 'version': 1}),
    (BillPayment, {'day': date(2026, 1, 1), 'account': '测试账户', 'version': 1}),
])
def test_money_schema_does_not_weaken_decimal_validation(model, fields):
    for value in ('0', '-1', 'NaN', 'Infinity', '0.001', '1000000000'):
        with pytest.raises(ValidationError):
            model(**fields, amount=value)
    for value in ('28.50', '0.100', '+000.10', '1e2', '999999999.99'):
        entry = model(**fields, amount=value)
        assert entry.amount == Decimal(value)
        schema = model.model_json_schema()['properties']['amount']
        string_schema = next(branch for branch in schema['anyOf'] if branch.get('type') == 'string')
        validator = SchemaValidator(core_schema.str_schema(pattern=string_schema['pattern'], regex_engine='rust-regex'))
        assert validator.validate_python(value) == value


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', ['chat', 'responses'])
async def test_discovered_financial_tools_use_gateway_compatible_wire_schemas(db, protocol):
    requests = []

    def gateway(request):
        body = json.loads(request.content)
        requests.append(body)
        tools = body['tools']
        functions = [tool.get('function', tool) for tool in tools]
        names = {tool['name'] for tool in functions}
        financial = {'record_transaction', 'create_bill', 'update_bill', 'confirm_bill_payment'}
        if len(requests) == 1:
            assert not financial & names
            assert 'search_tools' in names and len(names) <= 6
        else:
            assert financial <= names
        assert all(tool['type'] == 'function' for tool in tools)
        # Gateways may validate every tool before processing even a plain greeting.
        for tool in functions:
            check_patterns(tool['parameters'])
        search_args = json.dumps({'names': sorted(financial)})
        if len(requests) == 1:
            if protocol == 'chat':
                return httpx.Response(200, json={
                    'id': 'chatcmpl-discover', 'object': 'chat.completion', 'created': 0, 'model': 'example-model',
                    'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': {
                        'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'discover', 'type': 'function',
                        'function': {'name': 'search_tools', 'arguments': search_args}}]}}]})
            return httpx.Response(200, json={
                'id': 'resp_discover', 'object': 'response', 'created_at': 0, 'status': 'completed', 'model': 'example-model',
                'output': [{'id': 'fc_discover', 'call_id': 'discover', 'type': 'function_call',
                            'name': 'search_tools', 'arguments': search_args, 'status': 'completed'}]})
        if protocol == 'chat':
            return httpx.Response(200, json={
                'id': 'chatcmpl-test', 'object': 'chat.completion', 'created': 0,
                'model': 'example-model',
                'choices': [{'index': 0, 'finish_reason': 'stop',
                             'message': {'role': 'assistant', 'content': '你好'}}],
            })
        return httpx.Response(200, json={
            'id': 'resp_test', 'object': 'response', 'created_at': 0, 'status': 'completed',
            'model': 'example-model',
            'output': [{'id': 'msg_test', 'type': 'message', 'role': 'assistant',
                        'status': 'completed',
                        'content': [{'type': 'output_text', 'text': '你好', 'annotations': []}]}],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(gateway)) as client:
        sdk = AsyncOpenAI(api_key='test-only', base_url='https://gateway.example/v1', http_client=client)
        provider = OpenAIProvider(openai_client=sdk)
        model_class = OpenAIChatModel if protocol == 'chat' else OpenAIResponsesModel
        model = model_class('example-model', provider=provider)
        agent = AgentRuntime(model=model, db=db)._build_agent()
        result = await agent.run('你好', deps=AgentDeps(db=db, emit=asyncio.Queue()))
        assert result.output == '你好'
    assert len(requests) == 2
