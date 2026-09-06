import json

from fastapi.testclient import TestClient
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from tests.server.test_attachments import _parse_sse, _seed_enabled_config
from tests.server.test_followups import make_missed
from zhishi.server.app import create_app
from zhishi.server.routes import ai


def test_guided_followup_approval_resume_and_terminal_retry(tmp_path, monkeypatch):
    calls = 0
    followup_id = None
    project_id = None
    async def stream(messages, info):
        nonlocal calls, followup_id
        calls += 1
        parts = [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
        latest = json.loads(parts[-1].content) if parts else None
        if calls == 1:
            name, args = 'check_research_progress', {'project_id':project_id}
        elif calls == 2:
            followup_id = latest['id']
            assert latest['plan_summary']['state'] == 'draft'
            name, args = latest['next_call']['tool'], latest['next_call']['args']
        elif calls == 3:
            assert latest['status'] == 'applied'
            name, args = 'apply_secretary_followup', {'followup_id':followup_id, 'version':1}
        elif calls == 4:
            assert latest['status'] == 'applied'
            name, args = latest['next_call']['tool'], latest['next_call']['args']
        else:
            assert latest['project']['total_tasks'] == 1
            yield '已调整原来的学习任务，完成记录和任务编号保留。'
            return
        yield {0:DeltaToolCall(name=name, json_args=json.dumps(args), tool_call_id=f'followup-{calls}')}
    monkeypatch.setattr(ai, 'build_model', lambda *a, **k:FunctionModel(stream_function=stream))
    with TestClient(create_app(data_dir=tmp_path)) as c:
        _seed_enabled_config(c)
        project_id = make_missed(c)['id']
        before = c.get('/api/tasks').json()
        events = _parse_sse(c.post('/ai/chat/stream', json={'message':'跟进学习项目并调整错过的安排'}).text)
        assert not [e for e in events if e['type'] == 'run_error'], events
        approval = next(e for e in events if e['type'] == 'tool_approval_requested')
        assert c.post(f"/ai/actions/{approval['action_id']}/approve").status_code == 200
        resumed = _parse_sse(c.post(f"/ai/conversations/{events[0]['conversation_id']}/resume/stream").text)
        assert not [e for e in resumed if e['type'] in ('run_error', 'tool_approval_requested')], resumed
        assert calls == 5
        assert [t['id'] for t in c.get('/api/tasks').json()] == [t['id'] for t in before]
        assert c.get(f'/api/followups/{followup_id}').json()['status'] == 'applied'
