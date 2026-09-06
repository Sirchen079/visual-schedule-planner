"""Frozen inbox acceptance, using only temporary data and a random loopback port."""
import argparse
import http.client
import json
import tempfile
from pathlib import Path

from verify_ledger import request, start, stop


def upload(port, name):
    boundary = 'zhishi-inbox-acceptance'
    data = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
            'Content-Type: text/plain\r\n\r\n2026-09-05 paid CNY 28.50\r\n'
            f'--{boundary}--\r\n').encode()
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    try:
        conn.request('POST', '/ai/attachments', data, {'Content-Type': f'multipart/form-data; boundary={boundary}'})
        r = conn.getresponse()
        raw = r.read()
        assert r.status == 201, raw
        return json.loads(raw)['file_id']
    finally:
        conn.close()


def verify(exe):
    root = Path(tempfile.mkdtemp(prefix='zhishi-inbox-frozen-'))
    print(f'INBOX_CHECK_ROOT={root}', flush=True)
    proc, log, port = start(exe, root, 'first')
    try:
        fid, duplicate = upload(port, 'original.txt'), upload(port, 'renamed.txt')
        item = {'source_file_id': fid, 'item_key': 'receipt-total',
                'source_excerpt': '2026-09-05 paid CNY 28.50', 'proposal': {'kind': 'ledger',
                    'data': {'day': '2026-09-05', 'direction': 'expense', 'amount': '28.50'}}}
        def capture(candidate):
            return request(port, '/api/inbox', 'POST', {'capture_key':'verify', 'items':[candidate]}, 201)[0]
        row = capture(item)
        assert capture({**item, 'source_file_id': duplicate})['id'] == row['id']
        assert request(port, '/api/ledger')['total'] == 0
        applied = request(port, f"/api/inbox/{row['id']}/apply", 'POST', {'version':row['version']})
        assert request(port, f"/api/inbox/{row['id']}/apply", 'POST', {'version':row['version']}) == applied
        assert capture({**item, 'source_file_id': duplicate})['status'] == 'applied'
        assert request(port, '/api/ledger')['total'] == 1
        task = capture({**item, 'item_key':'task', 'proposal': {'kind':'task', 'data':{'title':'Read research notes'}}})
        event = capture({**item, 'item_key':'event', 'uncertainty':'Confirm room', 'proposal': {
            'kind':'event', 'data':{'title':'Research meeting', 'date':'2026-09-07','start_time':'10:00','end_time':'11:00'}}})
        request(port, f"/api/inbox/{event['id']}/apply", 'POST', {'version':1}, 409)
        fixed = request(port, f"/api/inbox/{event['id']}", 'PUT', {'version':1, 'proposal':event['proposal'], 'uncertainty':''})
        request(port, f"/api/inbox/{event['id']}/apply", 'POST', {'version':1}, 409)
        assert request(port, f"/api/inbox/{event['id']}/apply", 'POST', {'version':fixed['version']})['target_state'] == 'active'
        assert request(port, f"/api/inbox/{task['id']}/apply", 'POST', {'version':1})['target_state'] == 'active'
        assert request(port, '/api/tasks')[0]['title'] == 'Read research notes'
        assert request(port, '/api/inbox?status=applied')['total'] == 3
        target_id = applied['target_id']
        request(port, f'/api/ledger/{target_id}?version=1', 'DELETE')
        assert request(port, f"/api/inbox/{row['id']}/apply", 'POST', {'version':1})['target_state'] == 'deleted'
    finally:
        stop(proc, log, port)
    proc, log, port = start(exe, root, 'restart')
    try:
        assert request(port, '/api/inbox?status=applied')['total'] == 3
        assert request(port, '/api/inbox')['total'] == 0
        assert request(port, '/api/ledger')['total'] == 0
        assert request(port, '/api/ledger?deleted=true')['items'][0]['amount'] == '28.50'
        assert request(port, f"/api/inbox/{row['id']}")['source_excerpt'] == item['source_excerpt']
    finally:
        stop(proc, log, port)
    print('INBOX_CHECK_OK: upload, renamed replay, staged writes, three domains, uncertainty, stale version, deleted target, restart', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path, default=Path('dist/zhishi-backend/zhishi-backend.exe'))
    verify(parser.parse_args().exe.resolve())
