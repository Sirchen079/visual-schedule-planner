from fastapi.testclient import TestClient

from zhishi.server.app import create_app


def test_multiple_skills_edit_disable_and_conflict(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        body = {'name': '写作方法', 'description': '写周报', 'content': '写具体进度'}
        first = client.post('/ai/skills', json=body).json()['id']
        second = client.post('/ai/skills', json={**body, 'name': '复盘方法'}).json()['id']
        client.post(f'/ai/skills/{first}/enable')
        assert client.get(f'/ai/skills/{second}').json()['enabled'] is True
        detail = client.get(f'/ai/skills/{first}').json()
        update = {**body, 'content': '先列数据再写结论', 'expected_revision': detail['revision']}
        assert client.put(f'/ai/skills/{first}', json=update).status_code == 200
        assert client.put(f'/ai/skills/{first}', json=update).status_code == 409
        assert client.post('/ai/skills', json=body).status_code == 409
        assert client.post(f'/ai/skills/{first}/disable').status_code == 200
        assert client.get(f'/ai/skills/{first}').json()['enabled'] is False
        assert client.get(f'/ai/skills/{second}').json()['enabled'] is True
        assert client.get(f'/ai/skills/{first}/resources/999').status_code == 404
        builtin = next(s for s in client.get('/ai/skills').json() if s['is_builtin'])
        assert client.post(f'/ai/skills/{builtin["id"]}/disable').status_code == 404
        assert client.put(f'/ai/skills/{builtin["id"]}', json=update).status_code == 422
        assert client.post('/ai/skills', json={**body, 'name': ' '}).status_code == 422
    with TestClient(create_app(data_dir=tmp_path)) as restarted:
        assert restarted.get(f'/ai/skills/{first}').json()['content'] == '先列数据再写结论'
