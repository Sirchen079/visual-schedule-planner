# ruff: noqa: DTZ011 -- dates follow the user's local v2 calendar.
from datetime import date, timedelta

from fastapi.testclient import TestClient

from zhishi.domain.research import sources
from zhishi.server.app import create_app

SPEC = {'title':'研究测试项目','objective':'完成一份有来源的小报告','start_date':str(date.today()+timedelta(days=2)),
        'end_date':str(date.today()+timedelta(days=14)),'window_start':'18:30','window_end':'21:00','daily_minutes':60}


def test_project_material_plan_apply_restart_and_archive(tmp_path,monkeypatch):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        created = c.post('/api/research/projects',json={**SPEC,'request_key':'request-one'})
        assert created.status_code == 201, created.text
        p = created.json()
        assert c.post('/api/research/projects',json={**SPEC,'request_key':'request-one'}).json()['id'] == p['id']
        fid = c.post('/ai/attachments',files={'file':('reading.txt',b'Read, practice, then write a short report.','text/plain')}).json()['file_id']
        src = c.post(f"/api/research/projects/{p['id']}/materials",json={'file_id':fid})
        assert src.status_code == 201 and src.json()['kind'] == 'file'
        drafted = c.post(f"/api/research/projects/{p['id']}/plans",json={'version':1,'rationale':'先阅读再实践',
            'steps':[{'title':'阅读资料','outcome':'写下三个要点','minutes':90,'source_ids':[src.json()['id']]}]})
        assert drafted.status_code == 201, drafted.text
        plan = drafted.json()
        assert len(plan['units']) == 2 and c.get('/api/tasks').json() == []
        applied = c.post(f"/api/research/plans/{plan['id']}/apply")
        assert applied.status_code == 200 and applied.json()['result']['scheduled'] == 2
        assert c.post(f"/api/research/plans/{plan['id']}/apply").json()['result'] == applied.json()['result']
        detail = c.get(f"/api/research/projects/{p['id']}").json()
        assert detail['project']['total_tasks'] == 2
        assert detail['next_step']['tool'] == 'preview_research_replan'
    with TestClient(create_app(data_dir=tmp_path)) as c:
        detail = c.get(f"/api/research/projects/{p['id']}").json()
        assert detail['latest_plan']['state'] == 'applied'
        assert detail['sources'][0]['content'].startswith('Read, practice')
        assert c.post(f"/api/research/projects/{p['id']}/archive",json={'version':1}).status_code == 409
        assert c.post(f"/api/research/projects/{p['id']}/archive",json={'version':2}).status_code == 200
        assert c.get('/api/research/projects').json() == []
        assert len(c.get('/api/research/projects?archived=true').json()) == 1
        assert len(c.get('/api/tasks').json()) == 2
        assert c.post(f"/api/research/projects/{p['id']}/replan",json={'version':3}).status_code == 409
        assert c.post(f"/api/research/projects/{p['id']}/archive",json={'version':3,'archived':False}).status_code == 200


def test_api_rejects_bad_constraints_and_preserves_source_failures(tmp_path,monkeypatch):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        for change in ({'daily_minutes':0},{'weekdays':[1,1]},{'end_date':'2020-01-01'},
                       {'window_start':'21:00','window_end':'18:00'}):
            assert c.post('/api/research/projects',json={**SPEC,**change}).status_code == 422
        p = c.post('/api/research/projects',json=SPEC).json()
        monkeypatch.setattr(sources.web,'search',lambda *a,**k:[{'error':'暂时不可用'}])
        r = c.post(f"/api/research/projects/{p['id']}/sources/gather",json={})
        assert r.status_code == 200 and r.json()['ok'] is False
        assert r.json()['errors'][0]['error'] == '搜索服务返回错误，请检查服务配置或稍后重试'
        assert c.get('/api/files').json() == []
        assert c.get('/api/research/projects/999').status_code == 404
