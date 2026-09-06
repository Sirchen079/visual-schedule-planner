"""Exercise the frozen learning-project workflow against temporary data only."""
# ruff: noqa: DTZ011 -- v2 uses local calendar dates.
import argparse
import http.client
import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

from verify_ledger import request, start, stop


def upload(port):
    boundary = 'zhishi-research-acceptance'
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="study-notes.txt"\r\n'
            'Content-Type: text/plain\r\n\r\nRead the concepts, run an example, write three findings.\r\n'
            f'--{boundary}--\r\n').encode()
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    try:
        conn.request('POST', '/ai/attachments', body, {'Content-Type':f'multipart/form-data; boundary={boundary}'})
        response = conn.getresponse()
        raw = response.read()
        assert response.status == 201, raw
        return json.loads(raw)['file_id']
    finally:
        conn.close()


def verify(exe):
    root = Path(tempfile.mkdtemp(prefix='zhishi-research-frozen-'))
    print(f'RESEARCH_CHECK_ROOT={root}', flush=True)
    proc, log, port = start(exe, root, 'first')
    try:
        day = date.today() + timedelta(days=2)
        spec = {'title':'Frozen learning project', 'objective':'Complete an example and explain the findings',
                'start_date':str(day), 'end_date':str(day+timedelta(days=13)), 'daily_minutes':60,
                'window_start':'18:30', 'window_end':'21:00'}
        p = request(port, '/api/research/projects', 'POST', {**spec, 'request_key':'frozen-project'}, 201)
        assert request(port, '/api/research/projects', 'POST', {**spec, 'request_key':'frozen-project'}, 201)['id'] == p['id']
        pid = p['id']
        base = f'/api/research/projects/{pid}'
        src = request(port, base+'/materials', 'POST', {'file_id':upload(port)}, 201)
        assert src['kind'] == 'file' and src['status'] == 'verified'
        assert request(port, base+'/materials', 'POST', {'file_id':upload(port)}, 201)['id'] == src['id']
        draft = {'version':1, 'rationale':'Read, practice, reflect.', 'steps':[
            {'title':'Read and practice', 'outcome':'Run an example', 'minutes':90, 'source_ids':[src['id']]},
            {'title':'Reflect', 'outcome':'Write three findings', 'minutes':30, 'source_ids':[src['id']]}]}
        initial = request(port, base+'/plans', 'POST', draft, 201)
        assert request(port, '/api/tasks') == []
        request(port, '/api/schedule/events', 'POST', {'title':'New conflict', 'date':str(day), 'start_time':'18:30', 'end_time':'20:00'}, 201)
        request(port, f"/api/research/plans/{initial['id']}/apply", 'POST', expected=409)
        plan = request(port, base+'/plans', 'POST', draft, 201)
        assert plan['assignments'][0]['start'] == '20:00'
        applied = request(port, f"/api/research/plans/{plan['id']}/apply", 'POST')
        assert request(port, f"/api/research/plans/{plan['id']}/apply", 'POST') == applied
        detail = request(port, base)
        assert detail['project']['total_tasks'] == 3
        tasks = detail['tasks']
        request(port, f"/api/tasks/{tasks[0]['task_id']}", 'PATCH', {'status':'done'})
        manual = tasks[1]['slots'][0]
        manual_day = str(day+timedelta(days=5))
        request(port, f"/api/schedule/entries/{manual['id']}", 'PATCH', {'date':manual_day, 'start_time':'19:00', 'end_time':'19:45'})
        replanned = request(port, base+'/replan', 'POST', {'version':2}, 201)
        assert len(replanned['preserved']) == 2
        request(port, f"/api/research/plans/{replanned['id']}/apply", 'POST')
        detail = request(port, base)
        assert len(request(port, '/api/tasks')) == 3 and detail['project']['completed_tasks'] == 1
        assert detail['tasks'][1]['slots'][0]['date'] == manual_day
        assert detail['tasks'][2]['slots'][0]['date'] > manual_day
        request(port, base+'/archive', 'POST', {'version':3})
        assert request(port, '/api/research/projects') == []
    finally:
        stop(proc, log, port)
    proc, log, port = start(exe, root, 'restart')
    try:
        detail = request(port, base)
        assert detail['project']['status'] == 'archived' and detail['project']['completed_tasks'] == 1
        assert detail['sources'][0]['content'].startswith('Read the concepts')
        assert len(request(port, '/api/tasks')) == 3
        request(port, base+'/archive', 'POST', {'version':4, 'archived':False})
        assert len(request(port, '/api/research/projects')) == 1
        request(port, f"/api/tasks/{tasks[2]['task_id']}", 'DELETE', expected=204)
        r = request(port, base+'/replan', 'POST', {'version':5}, 201)
        request(port, f"/api/research/plans/{r['id']}/apply", 'POST')
        assert len(request(port, '/api/tasks')) == 2
        assert request(port, base)['project']['missing_tasks'] == 1
    finally:
        stop(proc, log, port)
    print('RESEARCH_FROZEN_PASS: material deduplication, stale calendar, atomic apply, completion, manual slot preservation, replan, restart, archive, deleted task stays deleted', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('exe', type=Path)
    verify(parser.parse_args().exe.resolve())
