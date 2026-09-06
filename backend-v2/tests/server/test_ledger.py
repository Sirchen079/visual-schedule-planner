from fastapi.testclient import TestClient

from zhishi.server.app import create_app

ENTRY = {"day": "2026-09-05", "direction": "expense", "amount": "28.50",
         "category": "餐饮", "idempotency_key": "request-1"}


def test_ledger_rest_and_restart(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        r = c.post('/api/ledger', json=ENTRY)
        assert r.status_code == 201, r.text
        row = r.json()
        assert row['amount'] == '28.50' and row['amount_minor'] == 2850
        assert c.post('/api/ledger', json=ENTRY).json()['id'] == row['id']
        assert c.post('/api/ledger', json={**ENTRY, 'amount': '30'}).status_code == 409
        assert c.post('/api/ledger', json={**ENTRY, 'amount': '1.234'}).status_code == 422
        assert c.post('/api/ledger', json={**ENTRY, 'category': '   '}).status_code == 422
        assert c.get('/api/ledger?limit=201').status_code == 422
        assert c.get('/api/ledger?start=2026-09-06&end=2026-09-05').status_code == 422
        assert c.get('/api/ledger/999999').status_code == 404
    with TestClient(create_app(data_dir=tmp_path)) as c:
        assert c.get('/api/ledger').json()['total'] == 1
        change = {k: v for k, v in ENTRY.items() if k != 'idempotency_key'}
        r = c.put(f"/api/ledger/{row['id']}", json={**change, 'amount': '29.00', 'version': 1})
        assert r.status_code == 200 and r.json()['version'] == 2
        assert c.delete(f"/api/ledger/{row['id']}?version=1").status_code == 409
        r = c.delete(f"/api/ledger/{row['id']}?version=2")
        assert r.status_code == 200
        assert c.get('/api/ledger').json()['total'] == 0
        assert c.get('/api/ledger?deleted=true').json()['total'] == 1
        assert c.post(f"/api/ledger/{row['id']}/restore", json={'version': 3}).status_code == 200
        r = c.get('/api/ledger/summary?start=2026-09-01&end=2026-09-30')
        assert r.status_code == 200 and r.json()['currencies'][0]['expense'] == '29.00'


def test_existing_v2_database_gains_ledger_table(tmp_path):
    import sqlite3

    from zhishi.domain.models import LedgerEntry
    with TestClient(create_app(data_dir=tmp_path)) as c:
        assert c.post('/api/tasks', json={'title': '保留任务'}).status_code == 201
        LedgerEntry.__table__.drop(c.app.state.engine)
    with TestClient(create_app(data_dir=tmp_path)) as c:
        assert c.get('/api/tasks').json()[0]['title'] == '保留任务'
        assert c.post('/api/ledger', json=ENTRY).status_code == 201
    with sqlite3.connect(tmp_path / 'v2' / 'backend.db') as db:
        assert db.execute('select amount_minor from ledger_entries').fetchone()[0] == 2850


def test_receipt_attachment_to_ledger_and_replay(tmp_path, monkeypatch):
    import json

    from pydantic_ai.models.function import DeltaToolCall, FunctionModel

    from tests.server.test_attachments import _parse_sse
    from zhishi.domain.models import AIConfig
    from zhishi.server.routes import ai
    with TestClient(create_app(data_dir=tmp_path)) as c:
        receipt = '2026-09-05 测试午餐店\n实付 CNY 28.50'
        upload = c.post('/ai/attachments', files={'file': ('receipt.txt', receipt.encode(), 'text/plain')})
        assert upload.status_code == 201
        file_id = upload.json()['file_id']
        assert upload.json()['parse_status'] == 'parsed'
        with c.app.state.session_factory() as db:
            db.add(AIConfig(name='test', provider_kind='openai_compat', model='test', enabled=True))
            db.commit()
        def model_factory(*args, **kwargs):
            calls = 0
            async def stream(messages, info):
                nonlocal calls
                calls += 1
                if calls == 1:
                    assert '实付 CNY 28.50' in str(messages)
                    yield {0: DeltaToolCall(name='record_transaction', json_args=json.dumps({'entry': {
                        **ENTRY, 'source_file_id': file_id, 'source_excerpt': receipt,
                        'idempotency_key': f'receipt:{file_id}:0'}}), tool_call_id='receipt')}
                else:
                    yield '收据已记到账本。'
            return FunctionModel(stream_function=stream)
        monkeypatch.setattr(ai, 'build_model', model_factory)
        for _ in range(2):
            result = c.post('/ai/chat/stream', json={'message': '请把这张收据记到账本', 'attachment_ids': [file_id]})
            events = _parse_sse(result.text)
            assert not [e for e in events if e['type'] == 'run_error']
            assert any(e['type'] == 'tool_call_result' for e in events)
        page = c.get('/api/ledger').json()
        assert page['total'] == 1
        assert page['items'][0]['source_file_id'] == file_id
        assert page['items'][0]['source_excerpt'] == receipt
