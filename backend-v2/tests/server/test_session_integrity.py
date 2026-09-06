"""Session integrity at the real runtime/HTTP boundary, without external model calls."""
import json

from fastapi.testclient import TestClient
from pydantic_ai.messages import UserPromptPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from tests.server.test_attachments import _parse_sse, _seed_enabled_config
from zhishi.server.app import create_app
from zhishi.server.routes import ai


def test_provider_failure_keeps_accepted_input_partial_reply_and_next_turn(tmp_path, monkeypatch):
    observed = []
    calls = 0

    async def stream(messages, info):
        nonlocal calls
        calls += 1
        observed.append([p.content for m in messages for p in m.parts if isinstance(p, UserPromptPart)])
        if calls == 1:
            yield '已开始处理这条消息'
            raise RuntimeError('injected provider disconnect')
        yield '继续处理已保存的消息'

    monkeypatch.setattr(ai, 'build_model', lambda *a, **k: FunctionModel(stream_function=stream))
    with TestClient(create_app(data_dir=tmp_path)) as client:
        _seed_enabled_config(client)
        events = _parse_sse(client.post('/ai/chat/stream',json={'message':'KEEP_FAILED_INPUT_291'}).text)
        cid = events[0]['conversation_id']
        rows = client.get(f'/ai/conversations/{cid}').json()
        assert any(r['role']=='user' and r['display']['text']=='KEEP_FAILED_INPUT_291' for r in rows)
        assert any('已开始处理这条消息' in r['display']['text'] for r in rows)
        continued = _parse_sse(client.post('/ai/chat/stream',json={'message':'接着处理','conversation_id':cid}).text)
        assert not [e for e in continued if e['type']=='run_error'], continued
        assert 'KEEP_FAILED_INPUT_291' in str(observed[-1])


def test_committed_tool_before_provider_failure_survives_context_reload(tmp_path, monkeypatch):
    calls = 0
    captured = []

    async def stream(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            yield {0:DeltaToolCall(name='record_transaction',json_args=json.dumps({'entry':{
                'day':'2026-01-01','direction':'expense','amount':'12.50',
                'idempotency_key':'session-integrity-expense'}}),tool_call_id='paid-call')}
        elif calls == 2:
            raise RuntimeError('injected failure after committed tool')
        else:
            captured.extend(messages)
            yield '这笔支出已保存，不重复记账'

    monkeypatch.setattr(ai,'build_model',lambda *a,**k:FunctionModel(stream_function=stream))
    with TestClient(create_app(data_dir=tmp_path)) as client:
        _seed_enabled_config(client)
        events = _parse_sse(client.post('/ai/chat/stream',json={'message':'记录已经支付的12.50元'}).text)
        cid = events[0]['conversation_id']
        assert client.get('/api/ledger').json()['total'] == 1
        client.post('/ai/chat/stream',json={'message':'刚才处理到哪里了','conversation_id':cid})
        parts = [p for m in captured for p in m.parts]
        assert any(getattr(p,'part_kind','')=='tool-return' and p.tool_call_id=='paid-call' for p in parts)
        assert client.get('/api/ledger').json()['total'] == 1


def test_first_turn_is_locked_by_real_conversation_id_and_missing_id_rejected(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path)
    snapshots = []

    async def stream(messages, info):
        snapshots.append(dict(app.state.active_runs))
        yield '正常回复'

    monkeypatch.setattr(ai,'build_model',lambda *a,**k:FunctionModel(stream_function=stream))
    with TestClient(app) as client:
        _seed_enabled_config(client)
        events = _parse_sse(client.post('/ai/chat/stream',json={'message':'首次发送'}).text)
        cid = events[0]['conversation_id']
        assert snapshots[0].get(cid) == events[0]['run_id']
        assert app.state.active_runs == {}
        assert client.post('/ai/chat/stream',json={'message':'不应隐式丢弃历史','conversation_id':99999}).status_code == 404


def test_cancellation_waits_for_started_write_and_keeps_its_receipt(tmp_path, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from zhishi.agent.tools import registry
    from zhishi.domain.models import AIToolExecution, Task

    written, release = threading.Event(), threading.Event()

    def slow_write(db: Session) -> str:
        task = Task(title='cancelled-write-still-committed')
        db.add(task); db.commit()
        written.set()
        assert release.wait(10)
        return json.dumps({'ok': True, 'task_id': task.id})

    monkeypatch.setattr(registry, '_REGISTRY', [*registry._REGISTRY,
        registry.ToolSpec('session_probe_write', '测试已经开始的写入', 'safe', None, slow_write)])
    calls = 0

    async def stream(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            yield {0:DeltaToolCall(name='session_probe_write',json_args='{}',tool_call_id='slow-write')}
        else:
            yield '已保存，不重复执行'

    monkeypatch.setattr(ai,'build_model',lambda *a,**k:FunctionModel(stream_function=stream))
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as client, ThreadPoolExecutor() as pool:
        _seed_enabled_config(client)
        future = pool.submit(client.post, '/ai/chat/stream', json={'message':'执行慢操作'})
        try:
            assert written.wait(10)
            cid, rid = next(iter(app.state.active_runs.items()))
            assert client.post(f'/ai/runs/{rid}/cancel').json()['ok']
            assert client.post('/ai/chat/stream',json={'message':'不应与未结束写入并发','conversation_id':cid}).status_code == 409
            assert client.delete(f'/ai/conversations/{cid}').status_code == 409
        finally:
            release.set()
        events = _parse_sse(future.result(timeout=15).text)
        assert next(e for e in events if e['type']=='run_completed')['done_reason'] == 'cancelled'
        assert not app.state.active_runs
        with app.state.session_factory() as db:
            receipt = db.scalar(select(AIToolExecution).where(AIToolExecution.call_id=='slow-write'))
            assert receipt.status == 'completed'
            history = ai.load_conversation_history(db,cid)
            returns = [p for m in history for p in m.parts if getattr(p,'tool_call_id',None)=='slow-write' and p.part_kind=='tool-return']
            assert returns and 'task_id' in str(returns[-1].content)
            assert len(list(db.scalars(select(Task).where(Task.title=='cancelled-write-still-committed')))) == 1


def test_restart_recovers_checkpoint_and_separate_window_selections(tmp_path):
    from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart

    from zhishi.agent import session_store
    from zhishi.domain.models import AIConversation, AIToolExecution
    with TestClient(create_app(data_dir=tmp_path)) as client:
        with client.app.state.session_factory() as db:
            a, b = AIConversation(title='MAIN'), AIConversation(title='WIDGET')
            db.add_all([a,b]); db.commit()
            cid, other = a.id,b.id
            run, assistant = session_store.begin_turn(db,cid,'crashed-run','保留原始输入',None)
            history = ai.load_conversation_history(db,cid)
            history.append(ModelResponse(parts=[TextPart('未完成的片段'),ToolCallPart('record_transaction',{},'written')]))
            session_store.checkpoint(db,run,assistant,history,[{'type':'text_delta','delta':'未完成的片段'}])
            db.add(AIToolExecution(run_id=run.run_id,call_id='written',tool='record_transaction',
                status='completed',result_json='{"entry_id": 123}')); db.commit()
        for surface, selected in [('main',cid),('widget',other)]:
            result = client.put(f'/ai/workspaces/{surface}',json={'revision':0,'state':{'active_id':selected,
                'drafts':{str(selected):{'text':surface+'未发送草稿','attachments':[]}}}})
            assert result.status_code == 200, result.text
        assert client.put('/ai/workspaces/main',json={'revision':0,'state':{'active_id':None}}).status_code == 409
    with TestClient(create_app(data_dir=tmp_path)) as restarted:
        assert restarted.get('/ai/workspaces/main').json()['state']['active_id'] == cid
        assert restarted.get('/ai/workspaces/widget').json()['state']['active_id'] == other
        state = restarted.get(f'/ai/conversations/{cid}/state').json()
        assert state['status'] == 'interrupted' and state['active_run_id'] is None
        messages = restarted.get(f'/ai/conversations/{cid}').json()
        assert messages[-1]['display']['text'] == '未完成的片段'
        with restarted.app.state.session_factory() as db:
            history = ai.load_conversation_history(db,cid)
            assert any(getattr(p,'content',None)=={'entry_id':123} for m in history for p in m.parts)


def test_pending_approval_restores_after_restart_and_can_be_stopped(tmp_path, monkeypatch):
    from tests.server.test_approval_flow import _stream_delete
    monkeypatch.setattr(ai,'build_model',lambda *a,**k:FunctionModel(stream_function=_stream_delete))
    with TestClient(create_app(data_dir=tmp_path)) as client:
        _seed_enabled_config(client)
        events = _parse_sse(client.post('/ai/chat/stream',json={'message':'删除任务42'}).text)
        cid,rid = events[0]['conversation_id'], events[0]['run_id']
        action = next(e for e in events if e['type']=='tool_approval_requested')
    with TestClient(create_app(data_dir=tmp_path)) as client:
        state = client.get(f'/ai/conversations/{cid}/state').json()
        assert state['approvals'][0]['action_id'] == action['action_id']
        assert state['approvals'][0]['status'] == 'pending'
        assert client.post('/ai/chat/stream',json={'message':'新一轮','conversation_id':cid}).status_code == 409
        assert client.post(f'/ai/conversations/{cid}/pending/cancel',json={'run_id':rid}).status_code == 200
        assert client.get(f'/ai/conversations/{cid}/state').json()['approvals'] == []
        continued = _parse_sse(client.post('/ai/chat/stream',json={'message':'继续聊天','conversation_id':cid}).text)
        assert not any(e['type']=='run_error' for e in continued), continued


def test_compaction_archives_original_and_history_tool_stays_in_current_session(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from pydantic_ai.messages import ModelMessagesTypeAdapter
    from sqlalchemy import select

    from tests.agent.test_compaction import _config, _history
    from zhishi.agent import compaction
    from zhishi.agent.tools.session_tools import read_conversation_history
    from zhishi.domain.models import AIContextCheckpoint, AIConversation, AIMessage
    monkeypatch.setattr(compaction,'build_model',lambda *a,**k: object())
    monkeypatch.setattr(compaction,'oneshot_text',lambda *a,**k:'有效摘要')
    with TestClient(create_app(data_dir=tmp_path)) as client:
        with client.app.state.session_factory() as db:
            a,b = AIConversation(title='A'), AIConversation(title='B')
            db.add_all([a,b]); db.commit()
            original = _history(16)
            db.add(AIMessage(conversation_id=a.id,role='assistant',display_json='{"text":"A_FACT"}',
                history_json=ModelMessagesTypeAdapter.dump_json(original).decode()))
            other = AIMessage(conversation_id=b.id,role='user',display_json='{"text":"B_SECRET"}',history_json='[]')
            db.add(other); db.commit()
            compacted = ai.load_conversation_history(db,a.id,_config())
            assert len(compacted)<len(original)
            archive = db.scalar(select(AIContextCheckpoint).where(AIContextCheckpoint.conversation_id==a.id))
            assert ModelMessagesTypeAdapter.validate_json(archive.history_json)==original
            ctx = SimpleNamespace(deps=SimpleNamespace(conversation_id=a.id))
            assert 'A_FACT' in read_conversation_history(db,ctx=ctx)
            assert 'B_SECRET' not in read_conversation_history(db,query='B_SECRET',ctx=ctx)
            assert 'B_SECRET' not in read_conversation_history(db,message_id=other.id,ctx=ctx)
