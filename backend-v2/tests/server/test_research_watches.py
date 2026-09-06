from fastapi.testclient import TestClient

from zhishi.adapters.web import WebDocument
from zhishi.domain.research import watches
from zhishi.server.app import create_app


def test_watch_api_validation_results_and_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(watches.web_services, 'search', lambda *a, **k:[{'url':'https://example.org/guide'}])
    monkeypatch.setattr(watches.web_services, 'fetch_document', lambda *a: WebDocument('检索到的正文'))
    with TestClient(create_app(data_dir=tmp_path)) as c:
        p = c.post('/api/research/projects', json={'title':'专题', 'objective':'学习'}).json()
        base = f"/api/research/projects/{p['id']}/watch"
        assert not c.get(base).json()['config']['enabled']
        assert c.post(base+'/run').status_code == 422
        payload = {'version':0,'enabled':True,'queries':['公开主题']}
        assert c.put(base, json={**payload,'queries':[]}).status_code == 422
        saved = c.put(base, json=payload)
        assert saved.status_code == 200, saved.text
        assert c.put(base, json=payload).status_code == 409
        run = c.post(base+'/run')
        assert run.status_code == 200, run.text
        assert run.json()['status'] == 'updated'
        assert c.get('/api/tasks').json() == []
    with TestClient(create_app(data_dir=tmp_path)) as c:
        state = c.get(base).json()
        assert state['version'] == 1 and state['runs'][0] == run.json()
        assert c.post(base+'/run').json()['status'] == 'unchanged'
        assert c.put(base, json={**payload,'enabled':False,'version':1}).status_code == 200
        assert c.post(base+'/run').status_code == 422
