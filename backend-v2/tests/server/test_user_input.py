"""Real SSE pause, restart, answer, approval and exactly-once resume."""
import json

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from tests.server.test_attachments import _parse_sse, _seed_enabled_config
from zhishi.server.app import create_app
from zhishi.server.routes import ai

QUESTIONS = [{'id': 'scope', 'question': '选择范围', 'options': [{'label': '今天'}, {'label': '本周'}]},
             {'id': 'detail', 'question': '补充要求'}]


def install_model(monkeypatch, mixed=False):
    captured = []
    async def stream(messages, info):
        results = [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
        if not any(p.tool_name == 'ask_user' for p in results):
            calls = {0: DeltaToolCall(name='ask_user', json_args=json.dumps({'questions': QUESTIONS}), tool_call_id='question-call')}
            if mixed:
                calls[1] = DeltaToolCall(name='delete_task', json_args='{"task_id":42}', tool_call_id='approval-call')
            yield calls
        else:
            captured.extend(results)
            yield '收到真实答案，继续执行。'
    monkeypatch.setattr(ai, 'build_model', lambda *a, **k: FunctionModel(stream_function=stream))
    return captured


def start(client):
    _seed_enabled_config(client)
    events = _parse_sse(client.post('/ai/chat/stream', json={'message': '按我的选择安排'}).text)
    assert not [e for e in events if e['type'] == 'run_error'], events
    question = next(e['request'] for e in events if e['type'] == 'user_input_requested')
    return events[0]['conversation_id'], question, events


def test_brainstorm_interview_keeps_readonly_mode_after_restart_and_answer(tmp_path, monkeypatch):
    modes = []
    async def stream(messages, info):
        modes.append({t.name for t in info.function_tools})
        results = [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
        if not any(p.tool_name == 'ask_user' for p in results):
            yield {0: DeltaToolCall(name='ask_user', json_args=json.dumps({'questions': QUESTIONS}), tool_call_id='plan-question')}
        else:
            yield '下一轮讨论时间和预算。'
    monkeypatch.setattr(ai, 'build_model', lambda *a, **k: FunctionModel(stream_function=stream))
    with TestClient(create_app(data_dir=tmp_path)) as client:
        _seed_enabled_config(client)
        events = _parse_sse(client.post('/ai/chat/stream', json={'message': '帮我理清需求', 'brainstorm_mode': True}).text)
        cid = events[0]['conversation_id']
        question = next(e['request'] for e in events if e['type'] == 'user_input_requested')
    with TestClient(create_app(data_dir=tmp_path)) as client:
        response = client.post(f'/ai/conversations/{cid}/questions/{question["id"]}/answer', json={
            'version': 0, 'answers': {'scope': {'selected': ['今天']}, 'detail': {'text': '保留午休'}}})
        assert response.status_code == 200
        events = _parse_sse(client.post(f'/ai/conversations/{cid}/resume/stream').text)
        assert events[-1]['type'] == 'done'
        assert not any(e['type'] in ('plan_card', 'run_error') for e in events)
    assert len(modes) == 2
    assert all('propose_plan' not in names and 'create_task' not in names for names in modes)


@pytest.mark.parametrize('mixed', [False, True])
def test_restart_answer_and_exactly_once_resume(tmp_path, monkeypatch, mixed):
    captured = install_model(monkeypatch, mixed)
    with TestClient(create_app(data_dir=tmp_path)) as client:
        cid, question, events = start(client)
        path = f'/ai/conversations/{cid}/questions/{question["id"]}/answer'
        assert client.get(f'/ai/conversations/{cid}/state').json()['status'] == 'awaiting_input'
        assert client.post(f'/ai/conversations/{cid}/resume/stream').status_code == 400
        assert client.post('/ai/chat/stream', json={'message': '新消息', 'conversation_id': cid}).status_code == 409
        draft = {'question_drafts': {str(question['id']): {'scope': {'selected': ['今天'], 'text': ''}}}}
        assert client.put('/ai/workspaces/main', json={'revision': 0, 'state': draft}).status_code == 200
    with TestClient(create_app(data_dir=tmp_path)) as client:
        state = client.get(f'/ai/conversations/{cid}/state').json()
        assert state['questions'][0]['status'] == 'pending' and not state['can_resume']
        assert client.get('/ai/workspaces/main').json()['state']['question_drafts'] == draft['question_drafts']
        body = {'version': 0, 'answers': {'scope': {'selected': ['今天'], 'text': '上午'}, 'detail': {'text': '保留午休'}}}
        assert client.post(path, json={'version': 0, 'answers': {}}).status_code == 422
        assert client.post(path.replace(f'/{cid}/', '/99999/'), json=body).status_code == 404
        reply = client.post(path, json=body)
        assert reply.status_code == 200, reply.text
        assert reply.json()['ready_to_resume'] is (not mixed)
        assert client.post(path, json=body).status_code == 200
        assert client.post(path, json={'version': 0, 'skip': True}).status_code == 409
        if mixed:
            assert client.post(f'/ai/conversations/{cid}/resume/stream').status_code == 400
            action = next(e for e in events if e['type'] == 'tool_approval_requested')
            assert client.post(f'/ai/actions/{action["action_id"]}/reject').json()['ready_to_resume']
        resumed = _parse_sse(client.post(f'/ai/conversations/{cid}/resume/stream').text)
        assert not [e for e in resumed if e['type'] == 'run_error'], resumed
        answer = next(p for p in captured if p.tool_name == 'ask_user')
        assert '保留午休' in str(answer.content) and '上午' in str(answer.content)
        assert client.post(f'/ai/conversations/{cid}/resume/stream').status_code == 400
        rows = client.get(f'/ai/conversations/{cid}').json()
        assert any(q['status'] == 'answered' for r in rows for q in r['display'].get('questions', []))


@pytest.mark.parametrize('action', ['skip', 'cancel'])
def test_explicit_skip_and_stop_do_not_invent_answers(tmp_path, monkeypatch, action):
    captured = install_model(monkeypatch)
    with TestClient(create_app(data_dir=tmp_path)) as client:
        cid, question, events = start(client)
        path = f'/ai/conversations/{cid}/questions/{question["id"]}/answer'
        if action == 'skip':
            assert client.post(path, json={'version': 0, 'skip': True}).json()['ready_to_resume']
            client.post(f'/ai/conversations/{cid}/resume/stream')
            result = next(p.content for p in captured if p.tool_name == 'ask_user')
            assert result['status'] == 'skipped' and result['answers'] == []
        else:
            assert client.post(f'/ai/conversations/{cid}/pending/cancel', json={'run_id': question['run_id']}).status_code == 200
            assert client.post(path, json={'version': 0, 'skip': True}).status_code == 409
            assert client.get(f'/ai/conversations/{cid}/state').json()['questions'] == []
