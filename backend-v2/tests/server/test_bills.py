from fastapi.testclient import TestClient

from zhishi.server.app import create_app


def test_bills_api_survives_restart_and_ledger_is_separate(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        created = c.post('/api/bills',json={'title':'云盘','first_due':'2026-01-31',
            'cycle':'monthly','request_key':'cloud','amount':'12.50'})
        assert created.status_code == 201, created.text
        b = created.json()
        assert c.get('/api/ledger').json()['total'] == 0
        base = f"/api/bills/occurrences/{b['pending']['id']}"
        payload = {'version':1,'day':'2026-01-31','amount':'12.50','account':'默认账户'}
        paid = c.post(base+'/pay',json=payload)
        assert paid.status_code == 200, paid.text
        assert c.post(base+'/pay',json=payload).json() == paid.json()
        assert c.post(base+'/skip',json={'version':1,'reason':'x'}).status_code == 409
    with TestClient(create_app(data_dir=tmp_path)) as c:
        current = c.get(f"/api/bills/{b['id']}").json()
        assert current['pending']['due'] == '2026-02-28'
        assert c.get('/api/ledger').json()['total'] == 1
        assert len(c.get(f"/api/bills/{b['id']}/history").json()['items']) == 2
        assert c.put(f"/api/bills/{b['id']}",json={**current['details'],
            'version':current['version'],'enabled':False}).status_code == 200
        assert c.get(f"/api/bills/{b['id']}").json()['details']['enabled'] is False
