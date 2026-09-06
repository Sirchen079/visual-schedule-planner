import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from tests.server.test_attachments import _parse_sse, _seed_enabled_config
from tests.server.test_research import SPEC
from zhishi.infra import local_clock
from zhishi.server.app import create_app
from zhishi.server.routes import ai


def seed(c):
    p = c.post('/api/research/projects', json=SPEC).json()
    root = f"/api/research/projects/{p['id']}"
    plan = c.post(root+'/plans', json={'version':1, 'rationale':'先基础，再实验，再总结',
        'steps':[{'title':title,'outcome':title+'的原笔记','minutes':45} for title in ['基础','实验','总结']]}).json()
    assert c.post(f"/api/research/plans/{plan['id']}/apply").status_code == 200
    detail = c.get(root).json()
    assert c.patch(f"/api/tasks/{detail['tasks'][0]['task_id']}", json={'status':'done'}).status_code == 200
    return root, c.get(root).json()


def test_revision_api_order_history_and_restart(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        root, original = seed(c)
        target = original['tasks'][1]
        payload = {'version':2,'mode':'insert_before','target_link_id':target['id'],
            'rationale':'补基础再实验','steps':[{'title':'补充小例子','outcome':'解释一个小例子','minutes':45}]}
        preview = c.post(root+'/revisions', json=payload)
        assert preview.status_code == 201, preview.text
        assert len(c.get('/api/tasks').json()) == 3
        assert c.post(f"/api/research/plans/{preview.json()['id']}/apply").status_code == 200
        assert c.post(root+'/revisions', json=payload).status_code == 409
        payload.update(version=3,mode='replace')
        before_replace = next(t for t in c.get(root).json()['tasks'] if t['id'] == target['id'])
        payload['steps'] = [{'title':'简化实验','outcome':'先解释变量，再运行','minutes':90}]
        replaced = c.post(root+'/revisions',json=payload).json()
        result = c.post(f"/api/research/plans/{replaced['id']}/apply")
        assert result.status_code == 200, result.text
        assert result.json()['result']['replaced_tasks'] == 1
    with TestClient(create_app(data_dir=tmp_path)) as c:
        detail = c.get(root).json()
        assert [t['title'] for t in detail['tasks']] == ['基础','补充小例子','简化实验 · 1/2','简化实验 · 2/2','总结']
        assert detail['tasks'][0] == original['tasks'][0]
        assert detail['tasks'][2]['task_id'] == target['task_id']
        history = c.get(root+'/plans').json()
        assert len(history['items']) == 3 and history['next_before'] is None
        assert history['items'][0]['kind'] == 'revision'
        assert c.get(root+'/plans?before=0').status_code == 422
        old = c.get(f"/api/research/plans/{replaced['id']}").json()
        assert old['revision']['before_task'] == before_replace


def test_agent_revision_conflict_approval_and_history_with_fresh_clock(tmp_path, monkeypatch):
    rounds, pid, target, plan_id = 0, None, None, None
    now = datetime(2026, 12, 31, 23, 59, tzinfo=timezone(timedelta(hours=8)))
    monkeypatch.setattr(local_clock, 'local_now', lambda:now)
    def call(name, args):
        return {0:DeltaToolCall(name=name, json_args=json.dumps(args), tool_call_id=f'revision-{rounds}')}
    async def stream(messages, info):
        nonlocal rounds, plan_id
        rounds += 1
        parts = [p for m in messages for p in m.parts if isinstance(p,ToolReturnPart)]
        result = json.loads(parts[-1].content) if parts else None
        assert now.isoformat(timespec='seconds') in messages[-1].instructions
        if rounds in (1,3):
            yield call('preview_research_revision', {'project_id':pid,'plan':{
                'version':2, 'mode':'replace','target_link_id':99999 if rounds==1 else target,
                'rationale':'将实验改为逐步练习','steps':[{'title':'逐步练习','outcome':'记录变量与结果','minutes':45}]}})
        elif rounds == 2:
            assert result['code'] == 'research_conflict'
            yield call(result['next_call']['tool'], result['next_call']['args'])
        elif rounds == 4:
            plan_id = result['plan']['id']
            yield call(result['next_call']['tool'], result['next_call']['args'])
        elif rounds == 5:
            assert result['result']['replaced_tasks'] == 1
            yield call('list_research_plans', {'project_id':pid})
        elif rounds == 6:
            assert result['items'][0]['id'] == plan_id
            yield call(result['items'][0]['read_call']['tool'],result['items'][0]['read_call']['args'])
        else:
            assert result['revision']['before_task']['title'] == '实验'
            yield '已调整实验内容，原笔记保存在方案历史。'
    monkeypatch.setattr(ai,'build_model',lambda *a,**k:FunctionModel(stream_function=stream))
    with TestClient(create_app(data_dir=tmp_path)) as c:
        _seed_enabled_config(c)
        root, original = seed(c)
        pid, target = original['project']['id'], original['tasks'][1]['id']
        events = _parse_sse(c.post('/ai/chat/stream',json={'message':'将实验替换为逐步练习','research_project_id':pid}).text)
        assert not [e for e in events if e['type']=='run_error'], events
        approval = next(e for e in events if e['type']=='tool_approval_requested')
        assert '原内容' in approval['preview'] and '逐步练习' in approval['preview']
        assert c.get(root).json()['tasks'][1]['title'] == '实验'
        now += timedelta(minutes=2)
        assert c.post(f"/ai/actions/{approval['action_id']}/approve").status_code == 200
        resumed = _parse_sse(c.post(f"/ai/conversations/{events[0]['conversation_id']}/resume/stream").text)
        assert not [e for e in resumed if e['type']=='run_error'], resumed
        assert rounds == 7
        current = c.get(root).json()
        assert current['project']['total_tasks'] == 3 and current['project']['completed_tasks'] == 1
        assert current['tasks'][1]['task_id'] == original['tasks'][1]['task_id']
