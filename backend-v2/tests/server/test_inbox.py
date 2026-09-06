from fastapi.testclient import TestClient

from zhishi.server.app import create_app


def test_material_upload_review_apply_and_restart(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        def upload(name):
            return client.post('/ai/attachments', files={'file': (name, b'paid CNY 28.50', 'text/plain')}).json()['file_id']
        first, second = upload('one.txt'), upload('two.txt')
        def payload(fid):
            return {'capture_key': 'chat', 'items': [{'source_file_id': fid, 'item_key': 'receipt-total',
                'source_excerpt': 'paid CNY 28.50', 'proposal': {'kind': 'ledger', 'data': {
                    'day': '2026-09-05', 'amount': '28.50', 'direction': 'expense'}}}]}
        r = client.post('/api/inbox', json=payload(first))
        assert r.status_code == 201, r.text
        row = r.json()[0]
        assert client.post('/api/inbox', json=payload(second)).json()[0]['id'] == row['id']
        assert client.get('/api/ledger').json()['total'] == 0
        applied = client.post(f"/api/inbox/{row['id']}/apply", json={'version': 1})
        assert applied.status_code == 200 and applied.json()['status'] == 'applied'
        assert client.post(f"/api/inbox/{row['id']}/apply", json={'version': 1}).status_code == 200
        assert client.get('/api/ledger').json()['total'] == 1
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.get('/api/inbox?status=applied').json()['total'] == 1
        assert client.get('/api/inbox').json()['total'] == 0
        assert client.get('/api/ledger').json()['items'][0]['source_excerpt'] == 'paid CNY 28.50'


def test_invalid_dates_and_amounts_never_create_candidates(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        for data in [
            {'kind': 'ledger', 'data': {'day': '2026-09-05', 'amount': '0.001', 'direction': 'expense'}},
            {'kind': 'event', 'data': {'title': 'bad', 'date': '2026-09-05', 'start_time': '10:00', 'end_time': '09:00'}},
        ]:
            r = c.post('/api/inbox', json={'capture_key': 'invalid', 'items': [
                {'item_key': 'one', 'source_excerpt': '原文', 'proposal': data}]})
            assert r.status_code == 422
        assert c.get('/api/inbox').json()['total'] == 0


def test_existing_v2_file_migrates_digest_without_losing_cached_text(tmp_path):
    import sqlite3
    from zhishi.domain.library.service import ensure_parsed
    from zhishi.domain.models import LibraryFile
    with TestClient(create_app(data_dir=tmp_path)) as c:
        fid = c.post('/ai/attachments', files={'file': ('old.txt', b'original material', 'text/plain')}).json()['file_id']
    with sqlite3.connect(tmp_path / 'v2' / 'backend.db') as db:
        db.execute('ALTER TABLE library_files DROP COLUMN content_sha256')
    with TestClient(create_app(data_dir=tmp_path)) as c:
        with c.app.state.session_factory() as db:
            row = db.get(LibraryFile, fid)
            assert row.content_sha256 is None
            doc = ensure_parsed(db, row, storage_root=c.app.state.storage_root)
            assert row.content_sha256 and 'original material' in doc.text
        second = c.post('/ai/attachments', files={'file': ('new.txt', b'original material', 'text/plain')}).json()['file_id']
        with c.app.state.session_factory() as db:
            assert db.get(LibraryFile, fid).content_sha256 == db.get(LibraryFile, second).content_sha256
