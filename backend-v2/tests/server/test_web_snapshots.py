from fastapi.testclient import TestClient

from zhishi.adapters.web import WebDocument
from zhishi.domain.research import sources
from zhishi.server.app import create_app


def test_api_snapshot_refresh_read_after_restart_and_error_recovery(tmp_path, monkeypatch):
    body = '教程基础。' * 8000 + '后段要求：完成独立练习。'
    monkeypatch.setattr(sources.web_services, 'fetch_document', lambda *a: WebDocument(body, True, ['服务未确认全文范围']))
    with TestClient(create_app(data_dir=tmp_path)) as c:
        p = c.post('/api/research/projects', json={'title':'专题','objective':'完成练习'}).json()
        base = f"/api/research/projects/{p['id']}"
        first = c.post(base+'/sources', json={'url':'https://example.org/guide'}).json()
        assert first['document']['total_parts'] > 4 and first['document']['partial']
        hit = c.get('/api/materials/search', params={'project_id':p['id'],'query':'后段要求'}).json()['hits'][0]
        original = c.get(f"/api/materials/{first['library_file_id']}", params={'part':hit['part'],'revision':hit['revision']})
        assert original.status_code == 200 and '独立练习' in original.text
        monkeypatch.setattr(sources.web_services, 'fetch_document', lambda *a: WebDocument(body + '新增检查点'))
        response = c.post(base + f"/sources/{first['id']}/fetch?refresh=true")
        assert response.status_code == 200, response.text
        second = response.json()
        assert second['id'] != first['id']
        assert c.post(base+'/sources', json={'url':first['url'],'refresh':True}).json()['id'] == second['id']
    monkeypatch.setattr(sources.web_services, 'fetch_document', lambda *a: (_ for _ in ()).throw(ValueError('离线')))
    with TestClient(create_app(data_dir=tmp_path)) as c:
        detail = c.get(base).json()
        assert detail['project']['verified_sources'] == 1 and len(detail['sources']) == 2
        assert detail['sources'][0]['id'] == second['id'] and detail['sources'][1]['superseded_by'] == second['id']
        retained = c.post(base + f"/sources/{second['id']}/fetch?refresh=true").json()
        assert retained['status'] == 'verified' and '已保留原版本' in retained['error']
        assert c.get(f"/api/materials/{first['library_file_id']}", params={'part':hit['part'],'revision':hit['revision']}).json() == original.json()
        assert c.get('/api/tasks').json() == []
