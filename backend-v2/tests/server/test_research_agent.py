import json

from fastapi.testclient import TestClient
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from tests.server.test_attachments import _parse_sse, _seed_enabled_config
from tests.server.test_research import SPEC
from zhishi.domain.research import sources
from zhishi.server.app import create_app
from zhishi.server.routes import ai


def test_selected_project_context_is_latest_and_invalid_id_releases_slot(tmp_path, monkeypatch):
    observed = []
    async def stream(messages, info):
        from pydantic_ai.messages import UserPromptPart
        observed.extend(p.content for m in messages for p in m.parts if isinstance(p, UserPromptPart))
        yield '已读取当前项目。'
    monkeypatch.setattr(ai, 'build_model', lambda *a, **k: FunctionModel(stream_function=stream))
    with TestClient(create_app(data_dir=tmp_path)) as c:
        _seed_enabled_config(c)
        p = c.post('/api/research/projects', json=SPEC).json()
        response = c.post('/ai/chat/stream', json={'message': '读一下这个项目', 'research_project_id': p['id']})
        events = _parse_sse(response.text)
        assert not [e for e in events if e['type'] == 'run_error'], events
        cid = events[0]['conversation_id']
        assert '【当前打开的学习/研究项目】' in observed[-1]
        assert SPEC['objective'] in observed[-1]
        invalid = c.post('/ai/chat/stream', json={'message': '继续', 'conversation_id': cid, 'research_project_id': 999999})
        assert invalid.status_code == 404
        assert c.post('/ai/chat/stream', json={'message': '继续', 'conversation_id': cid, 'research_project_id': 0}).status_code == 422
        changed = {**SPEC, 'objective': '新的目标：独立完成练习'}
        assert c.put(f"/api/research/projects/{p['id']}", json={'version': p['version'], 'spec': changed}).status_code == 200
        fresh = c.post('/ai/chat/stream', json={'message': '读一下新目标', 'conversation_id': cid, 'research_project_id': p['id']})
        assert fresh.status_code == 200 and '新的目标：独立完成练习' in observed[-1]


def test_guided_research_chain_repairs_source_id_and_resumes_once(tmp_path,monkeypatch):
    monkeypatch.setattr(sources.web,'search',lambda *a,**k:[{'title':'测试教程','url':'https://example.org/tutorial'}])
    monkeypatch.setattr(sources.web,'fetch_document',lambda url:sources.web.WebDocument('这份测试正文讲解如何阅读、实践和复盘。'))
    calls = 0
    pid, plan_id = None, None
    def call(name,args):
        return {0:DeltaToolCall(name=name,json_args=json.dumps(args),tool_call_id=f'research-{calls}')}
    async def stream(messages,info):
        nonlocal calls,pid,plan_id
        calls += 1
        parts = [p for m in messages for p in m.parts if isinstance(p,ToolReturnPart)]
        latest = json.loads(parts[-1].content) if parts else None
        if calls == 1:
            yield call('create_research_project',{'spec':SPEC})
        elif calls == 2:
            pid = latest['project']['id']
            step = latest['next_step']
            assert step['tool'] == 'research_project_sources'
            yield call(step['tool'],step['args'])
        elif calls in (3,5):
            if calls == 3:
                assert '测试正文' in latest['sources'][0]['content']
                sid, version = 999999, latest['context']['version']
            else:
                sid, version = latest['sources'][0]['id'], latest['project']['version']
            yield call('preview_research_plan',{'project_id':pid,'plan':{'version':version,
                'rationale':'先阅读，再在实践中验证理解。','steps':[
                    {'title':'阅读并实践','outcome':'完成一个可运行例子','minutes':90,'source_ids':[sid]}]}})
        elif calls == 4:
            assert latest['ok'] is False and latest['code'] == 'research_conflict'
            recovery = latest['next_call']
            yield call(recovery['tool'],recovery['args'])
        elif calls == 6:
            plan_id = latest['plan']['id']
            yield call(latest['next_call']['tool'],latest['next_call']['args'])
        elif calls == 7:
            assert latest['state'] == 'applied'
            yield call('apply_research_plan',{'plan_id':plan_id})
        elif calls == 8:
            yield call('get_research_project',{'project_id':pid})
        else:
            assert latest['project']['total_tasks'] == 2 and latest['project']['verified_sources'] == 1
            yield '资料已入库，两个学习时段已加入真实日历。'
    monkeypatch.setattr(ai,'build_model',lambda *a,**k:FunctionModel(stream_function=stream))
    with TestClient(create_app(data_dir=tmp_path)) as c:
        _seed_enabled_config(c)
        events = _parse_sse(c.post('/ai/chat/stream',json={'message':'帮我制定测试主题的学习项目并安排时间'}).text)
        assert not [e for e in events if e['type'] == 'run_error'], events
        assert c.get('/api/tasks').json() == []
        assert len(c.get('/api/files').json()) == 1
        approval = next(e for e in events if e['type'] == 'tool_approval_requested')
        assert c.post(f"/ai/actions/{approval['action_id']}/approve").status_code == 200
        resumed = _parse_sse(c.post(f"/ai/conversations/{events[0]['conversation_id']}/resume/stream").text)
        assert not [e for e in resumed if e['type'] == 'run_error'], resumed
        assert calls == 9 and len(c.get('/api/tasks').json()) == 2
        assert c.get(f'/api/research/projects/{pid}').json()['project']['total_tasks'] == 2
