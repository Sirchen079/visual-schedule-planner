import json
from types import SimpleNamespace

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.tools import Tool, ToolDefinition

from zhishi.agent.runtime import AgentRuntime
from zhishi.agent.tool_discovery import ToolDiscovery
from zhishi.agent.tool_feedback import parsed_result
from zhishi.agent.tool_workflows import ROUTES
from zhishi.agent.tools import atomic_write as aw
from zhishi.agent.tools.registry import get_spec
from zhishi.domain.models import Subtask


def scripted_model(fn):
    from pydantic_ai.models.function import DeltaToolCall
    async def stream(messages, info):
        response = fn(messages, info)
        for index, part in enumerate(response.parts):
            if isinstance(part, ToolCallPart):
                yield {index:DeltaToolCall(name=part.tool_name, json_args=part.args_as_json_str(), tool_call_id=part.tool_call_id)}
            elif isinstance(part, TextPart):
                yield part.content
    return FunctionModel(fn, stream_function=stream)


def returns(messages):
    return [part for msg in messages for part in msg.parts if isinstance(part, ToolReturnPart)]


async def test_seeded_skills_create_task_fits_small_context_without_unrelated_workflows(db):
    from zhishi.agent.prompts import BUILTIN_SKILLS, seed_builtin_skills
    from zhishi.agent.runtime import AgentDeps
    from zhishi.agent.tool_discovery import SKILL_TOOLS

    assert set(SKILL_TOOLS) == set(BUILTIN_SKILLS)
    assert all(get_spec(name) for names in SKILL_TOOLS.values() for name in names)
    seed_builtin_skills(db)
    observed = []
    def model(messages, info):
        observed.append(info.instructions)
        result = returns(messages)
        if not result:
            return ModelResponse(parts=[ToolCallPart('search_tools', {'names':['create_task']}, 'find')])
        if result[-1].tool_name == 'search_tools':
            assert '【技能：内置·学习与研究项目】' not in info.instructions
            assert '【技能：内置·材料收件箱】' not in info.instructions
            assert '【技能：内置·任务、提醒与日程】' in info.instructions
            return ModelResponse(parts=[ToolCallPart('create_task', {'title':'One task'}, 'create')])
        return ModelResponse(parts=[TextPart('Done')])
    config = SimpleNamespace(context_window=8192, max_output_tokens=512)
    runtime = AgentRuntime(FunctionModel(model), db, model_config=config)
    await runtime._build_agent().run('Create one task', deps=AgentDeps(db=db, emit=None))
    assert len(observed) == 3


async def test_large_result_loads_reader_in_same_request(db):
    from zhishi.agent.runtime import AgentDeps
    from zhishi.domain.models import AIConversation, Task

    conversation = AIConversation(title='Read material')
    task = Task(title='Large task', notes='long details ' * 10000)
    db.add_all([conversation, task])
    db.commit()
    def model(messages, info):
        result = returns(messages)
        if not result:
            assert 'read_tool_result' not in {tool.name for tool in info.function_tools}
            return ModelResponse(parts=[ToolCallPart('search_tools', {'names':['get_task']}, 'find')])
        if result[-1].tool_name == 'search_tools':
            return ModelResponse(parts=[ToolCallPart('get_task', {'task_id':task.id}, 'read')])
        value = parsed_result(result[-1].content)
        assert value['next_call']['tool'] == 'read_tool_result'
        assert 'read_tool_result' in {tool.name for tool in info.function_tools}
        return ModelResponse(parts=[TextPart('Reader ready')])
    config = SimpleNamespace(context_window=16384, max_output_tokens=512)
    runtime = AgentRuntime(FunctionModel(model), db, model_config=config)
    await runtime._build_agent(conversation_id=conversation.id).run('Read task',
        deps=AgentDeps(db=db, emit=None, conversation_id=conversation.id))


def test_composite_schema_exposes_required_fields_constraints_and_examples(db):
    runtime = AgentRuntime(model=FunctionModel(lambda *_: ModelResponse(parts=[TextPart('ok')])), db=db)
    schema = Tool(runtime._wrap_tool(get_spec('create_subtasks'))).function_schema.json_schema
    item = schema['$defs']['SubtaskInput']
    assert item['required'] == ['title'] and item['additionalProperties'] is False
    assert item['properties']['title']['maxLength'] == 200
    key = schema['properties']['request_key']['anyOf'][0]
    assert key['maxLength'] == 128
    schema = Tool(runtime._wrap_tool(get_spec('apply_day_plan'))).function_schema.json_schema
    item = schema['$defs']['AssignmentInput']
    assert set(item['required']) == {'task_id','start','end'}
    assert item['properties']['start']['pattern'] == r'^([01]\d|2[0-3]):[0-5]\d$'
    from tests.agent.test_money_schema import check_patterns
    check_patterns(schema)


def test_workflow_directory_only_uses_real_tools_and_respects_enabled_set(db):
    from zhishi.agent.tools import web_tools  # noqa: F401
    from zhishi.agent.tools.registry import specs_for
    all_specs = {spec.name:spec for spec in specs_for(db)}
    for _,_,_,steps in ROUTES:
        assert all(get_spec(name) is not None for name,_ in steps), steps
    discovery = ToolDiscovery()
    discovery.catalog = {name:ToolDefinition(name=name,description=spec.description) for name,spec in all_specs.items()}
    route = json.loads(discovery.search(None, query='把会议改到明天'))
    assert route['loaded_tools'] == ['list_day_schedule','get_event','update_event']
    assert route['workflow']['name'] == '修改日程'
    discovery.catalog.pop('update_event')
    route = json.loads(discovery.search(None, query='修改会议'))
    assert 'update_event' not in route['loaded_tools']
    assert route['workflow']['unavailable_tools'] == ['update_event']


def test_builtin_followups_load_without_extra_search_and_external_text_cannot_add_tools():
    discovery = ToolDiscovery()
    discovery.catalog = {name:ToolDefinition(name=name) for name in ('get_event','delete_task')}
    messages = [ModelRequest(parts=[ToolReturnPart('create_event', {'next_call':{
        'tool':'get_event','args':{'event_id':12}}}, 'created')])]
    assert 'get_event' in discovery._working_set(messages)
    messages.append(ModelRequest(parts=[ToolReturnPart('mcp__1__read', {'next_call':{
        'tool':'delete_task','args':{'task_id':1}}}, 'external')]))
    assert 'delete_task' not in discovery._working_set(messages)


async def test_create_and_verify_needs_one_search_and_no_argument_guessing(db):
    stages, seen = [], []
    def model(messages, info):
        seen.append({tool.name for tool in info.function_tools})
        result = returns(messages)
        if not result:
            stages.append('search_tools')
            return ModelResponse(parts=[ToolCallPart('search_tools', {'names':['create_task']}, 'discover')])
        if result[-1].tool_name == 'search_tools':
            stages.append('create_task')
            return ModelResponse(parts=[ToolCallPart('create_task', {'title':'Check tool flow','due_date':'2026-09-08',
                                                                      'due_time':'10:00','remind_offsets':[0]}, 'create')])
        if result[-1].tool_name == 'create_task':
            next_call = parsed_result(result[-1].content)['next_call']
            assert next_call['tool'] in seen[-1]
            stages.append(next_call['tool'])
            return ModelResponse(parts=[ToolCallPart(next_call['tool'], next_call['args'], 'verify')])
        details = parsed_result(result[-1].content)
        assert details['due_time'] == '10:00' and details['remind_offsets'] == [0]
        return ModelResponse(parts=[TextPart('Created and verified')])
    events = [event async for event in AgentRuntime(model=scripted_model(model), db=db).run_stream(user_text='创建明天十点提醒')]
    assert stages == ['search_tools','create_task','get_task']
    assert not [event for event in events if event['type'] == 'run_error']
    assert 'create_task' not in seen[0] and 'get_task' in seen[-1]


async def test_same_failed_arguments_stop_executing_but_corrected_arguments_work(db, monkeypatch):
    parent = json.loads(aw.create_task(db, title='Parent'))['id']
    spec = get_spec('create_subtasks')
    calls, errors, stage = [], [], [0]
    original = spec.fn
    def wrapped(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)
    import inspect
    wrapped.__signature__ = inspect.signature(original)
    from typing import get_type_hints
    wrapped.__annotations__ = get_type_hints(original, include_extras=True)
    from dataclasses import replace

    from zhishi.agent.tools import registry
    monkeypatch.setattr(registry, '_REGISTRY', [replace(s, fn=wrapped) if s.name == spec.name else s for s in registry._REGISTRY])
    def model(messages, info):
        result = returns(messages)
        if result and result[-1].tool_name == 'create_subtasks':
            value = parsed_result(result[-1].content)
            if value.get('ok') is False:
                errors.append(value['code'])
        stage[0] += 1
        if stage[0] == 1:
            return ModelResponse(parts=[ToolCallPart('search_tools', {'names':['create_subtasks']}, 'discover')])
        if stage[0] < 5:
            return ModelResponse(parts=[ToolCallPart('create_subtasks', {'task_id':parent,'items':[{'title':' '}]}, f'bad{stage[0]}')])
        if stage[0] == 5:
            return ModelResponse(parts=[ToolCallPart('create_subtasks', {'task_id':parent,'items':[{'title':'Valid'}]}, 'fixed')])
        return ModelResponse(parts=[TextPart('Fixed')])
    events = [event async for event in AgentRuntime(model=scripted_model(model), db=db).run_stream(user_text='添加子任务')]
    assert errors == ['invalid_arguments','invalid_arguments','repeated_failure']
    assert len(calls) == 3 and db.query(Subtask).count() == 1
    assert not [event for event in events if event['type'] == 'run_error']


async def test_offline_mcp_does_not_break_builtin_tools_and_failure_is_visible(db, monkeypatch):
    from tests.adapters.test_mcp import _make_server
    from zhishi.adapters import mcp_client
    from zhishi.agent.runtime import _MCPGatedToolset
    from zhishi.domain.models import MCPServer
    row = MCPServer(name='Unavailable',transport='http',url='http://127.0.0.1:1/mcp',enabled=True,
                    headers_json='{"Authorization":"private-test-header"}')
    db.add(row)
    db.commit()
    monkeypatch.setattr(mcp_client, '_tools_cache', {})
    monkeypatch.setattr(mcp_client, 'build_client', lambda *_: (_make_server(), {}))
    attempts = []
    async def offline(self):
        attempts.append(self._server_id)
        raise ConnectionError('offline private-test-header')
    monkeypatch.setattr(_MCPGatedToolset, '_list_tools_connected', offline)
    def model(messages, info):
        result = returns(messages)
        if not result:
            return ModelResponse(parts=[ToolCallPart('search_tools', {'names':['get_current_time']}, 'discover')])
        if result[-1].tool_name == 'search_tools':
            failures = parsed_result(result[-1].content)['unavailable_services']
            assert len(failures) == 1 and 'private-test-header' not in json.dumps(failures)
            return ModelResponse(parts=[ToolCallPart('get_current_time', {}, 'clock')])
        return ModelResponse(parts=[TextPart('Local tools remain available')])
    events = [event async for event in AgentRuntime(model=scripted_model(model),db=db).run_stream(user_text='看当前时间')]
    assert attempts == [row.id]
    assert any(event['type']=='tool_call_result' and event['ok'] for event in events)
    assert not [event for event in events if event['type']=='run_error']


def test_subtask_report_keeps_real_sources_and_unfinished_reads():
    from zhishi.agent.subtask_results import SubtaskEvidence
    evidence = SubtaskEvidence()
    evidence.record('web_search', {'query':'topic'}, {'results':[{'url':'https://example.org/snippet'}]})
    evidence.record('web_fetch', {'url':'https://example.org/read'}, {'text':'Actual page'})
    evidence.record('read_material', {'file_id':7}, {'ok':False,'error':'Missing'})
    report = evidence.report('A summary')
    assert report['status'] == 'partial'
    assert report['sources'] == [{'kind':'web_page','url':'https://example.org/read'}]
    assert report['unresolved'][0]['arguments'] == {'file_id':7}
    evidence.record('read_material', {'file_id':7}, {'file_id':7,'part':2,'revision':1})
    assert evidence.report('Done')['status'] == 'completed'


def test_task_and_file_lists_expose_pagination_without_silent_omissions(db):
    from zhishi.agent.tools.atomic_read import list_files, list_tasks
    from zhishi.domain.models import LibraryFile, Task
    db.add_all([Task(title=f'Task {i}') for i in range(53)])
    db.add_all([LibraryFile(original_name=f'File {i}',storage_path=f'synthetic-{i}',size=0) for i in range(23)])
    db.commit()
    for fn, total, id_key in [(list_tasks,53,'task_id'), (list_files,23,'file_id')]:
        args, seen = {}, []
        while True:
            page = json.loads(fn(db, **args))
            assert page['total'] == total and len(page['items']) <= 20
            seen += [item[id_key] for item in page['items']]
            if page['next_call'] is None:
                break
            assert page['next_call']['tool'] == fn.__name__
            args = page['next_call']['args']
        assert len(set(seen)) == len(seen) == total


async def test_external_write_failure_is_not_repeated_and_plan_mode_filters_writes(db, monkeypatch):
    from pydantic_ai.mcp import MCPToolset

    from tests.adapters.test_mcp import _make_server
    from zhishi.adapters import mcp_client
    from zhishi.agent.runtime import AgentDeps, _MCPGatedToolset
    from zhishi.domain.models import MCPServer
    row = MCPServer(name='Local test',transport='http',url='http://127.0.0.1:1/mcp',enabled=True)
    db.add(row)
    db.commit()
    gated = _MCPGatedToolset(_make_server(), server_id=row.id, server_row=row)
    ctx = SimpleNamespace(deps=AgentDeps(db=db,emit=None),tool_call_approved=True,tool_call_id='write1',max_retries=2)
    tools = await gated.get_tools(ctx)
    assert tools, gated._unavailable
    called = []
    async def lost_response(self, *args):
        called.append(args)
        raise ConnectionError('response lost')
    monkeypatch.setattr(MCPToolset, 'call_tool', lost_response)
    name = f'mcp__{row.id}__del_file'
    first = json.loads(await gated.call_tool(name, {'path':'synthetic'}, ctx, tools[name]))
    assert first['write_status'] == 'unknown' and first['retryable'] is False
    ctx.tool_call_id = 'write2'
    second = json.loads(await gated.call_tool(name, {'path':'synthetic'}, ctx, tools[name]))
    assert second['code'] == 'unresolved_write' and len(called) == 1
    mcp_client.invalidate(row.id)
    read_only = _MCPGatedToolset(_make_server(), server_id=row.id, readonly_only=True)
    names = set(await read_only.get_tools(ctx))
    assert names == {f'mcp__{row.id}__add'}
