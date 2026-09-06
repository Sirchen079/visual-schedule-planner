import json

from fastapi.testclient import TestClient
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from tests.server.test_attachments import _parse_sse, _seed_enabled_config
from tests.server.test_research import SPEC
from zhishi.server.app import create_app
from zhishi.server.routes import ai


def started(client):
    p = client.post('/api/research/projects', json=SPEC).json()
    plan = client.post(f"/api/research/projects/{p['id']}/plans", json={'version':1, 'rationale':'先动手',
        'steps':[{'title':'运行例子', 'outcome':'记录运行结果', 'minutes':45}]}).json()
    assert client.post(f"/api/research/plans/{plan['id']}/apply").status_code == 200
    return client.get(f"/api/research/projects/{p['id']}").json()


def test_feedback_extension_restart_withdraw_and_stale_preview(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        detail = started(c)
        pid = detail['project']['id']
        root = f'/api/research/projects/{pid}'
        payload = {'version':2, 'request_key':'review-one', 'note':'公式还没看懂，希望有更多例子',
            'task_link_id':detail['tasks'][0]['id'], 'difficulty':'too_hard', 'actual_minutes':80}
        for invalid in ({'note':' '}, {'actual_minutes':-1}, {'difficulty':'mastered'}):
            assert c.post(root+'/feedback', json={**payload, **invalid}).status_code == 422
        saved = c.post(root+'/feedback', json=payload)
        assert saved.status_code == 201, saved.text
        fid = saved.json()['id']
        assert c.post(root+'/feedback', json=payload).json()['id'] == fid
        preview = c.post(root+'/extensions', json={'version':3, 'rationale':'先用例子理解公式', 'feedback_ids':[fid],
            'steps':[{'title':'用例子理解公式', 'outcome':'逐步推导一个例子', 'minutes':45}]})
        assert preview.status_code == 201, preview.text
        plan = preview.json()
        assert plan['feedback_ids'] == [fid] and len(c.get('/api/tasks').json()) == 1
        assert c.post(f"/api/research/plans/{plan['id']}/apply").status_code == 200
    with TestClient(create_app(data_dir=tmp_path)) as c:
        data = c.get(root).json()
        assert data['project']['total_tasks'] == 2 and data['project']['completed_tasks'] == 0
        assert data['feedback']['items'][0]['applied_plan_ids'] == [plan['id']]
        assert c.get(f"/api/research/plans/{plan['id']}").json()['feedback_ids'] == [fid]
        stale = c.post(root+'/extensions', json={'version':4, 'rationale':'更多实践', 'feedback_ids':[fid],
            'steps':[{'title':'独立实践', 'outcome':'解决一个新例子', 'minutes':45}]}).json()
        assert c.post(root+f'/feedback/{fid}/withdraw', json={'version':4}).status_code == 200
        assert c.post(f"/api/research/plans/{stale['id']}/apply").status_code == 409
        assert c.get(root+'/feedback').json()['total'] == 0
        assert c.get(root+'/feedback?before=0').status_code == 422
        assert len(c.get('/api/tasks').json()) == 2


def test_agent_reports_feedback_repairs_extension_and_resumes_without_duplicates(tmp_path, monkeypatch):
    rounds = 0
    pid, fid, plan_id = None, None, None
    report = {'note':'做完例子后还是不理解公式，希望多一个具体例子', 'difficulty':'too_hard', 'actual_minutes':75}
    def call(name, args):
        return {0:DeltaToolCall(name=name, json_args=json.dumps(args), tool_call_id=f'learning-{rounds}')}
    async def stream(messages, info):
        nonlocal rounds, fid, plan_id
        rounds += 1
        parts = [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
        result = json.loads(parts[-1].content) if parts else None
        if rounds in (1, 2, 8):
            if rounds == 2:
                fid = result['feedback']['id']
                assert result['context']['project']['version'] == 3
            yield call('record_research_feedback', {'project_id':pid, 'version':2, 'report':report})
        elif rounds in (3, 5):
            if rounds == 3:
                assert result['feedback']['id'] == fid
            yield call('preview_research_extension', {'project_id':pid, 'plan':{'version':3,
                'rationale':'通过具体例子巩固用户提到的公式', 'feedback_ids':[999999 if rounds == 3 else fid],
                'steps':[{'title':'推导一个新例子', 'outcome':'解释每一步推导', 'minutes':45}]}})
        elif rounds == 4:
            assert result['code'] == 'research_conflict'
            yield call(result['next_call']['tool'], result['next_call']['args'])
        elif rounds == 6:
            plan_id = result['plan']['id']
            yield call(result['next_call']['tool'], result['next_call']['args'])
        elif rounds == 7:
            assert result['state'] == 'applied'
            yield call('apply_research_plan', {'plan_id':plan_id})
        elif rounds == 9:
            assert result['feedback']['id'] == fid
            assert result['context']['project']['total_tasks'] == 2
            yield '反馈已保留，补充练习已加入项目。'
        else:
            raise AssertionError(rounds)
    monkeypatch.setattr(ai, 'build_model', lambda *a, **k:FunctionModel(stream_function=stream))
    with TestClient(create_app(data_dir=tmp_path)) as c:
        _seed_enabled_config(c)
        pid = started(c)['project']['id']
        events = _parse_sse(c.post('/ai/chat/stream', json={'message':report['note'], 'research_project_id':pid}).text)
        assert not [e for e in events if e['type'] == 'run_error'], events
        approval = next(e for e in events if e['type'] == 'tool_approval_requested')
        assert len(c.get('/api/tasks').json()) == 1
        assert c.post(f"/ai/actions/{approval['action_id']}/approve").status_code == 200
        resumed = _parse_sse(c.post(f"/ai/conversations/{events[0]['conversation_id']}/resume/stream").text)
        assert not [e for e in resumed if e['type'] == 'run_error'], resumed
        assert rounds == 9
        detail = c.get(f'/api/research/projects/{pid}').json()
        assert detail['feedback']['total'] == 1 and detail['project']['total_tasks'] == 2
        assert detail['project']['completed_tasks'] == 0
