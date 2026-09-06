"""Frozen followup lifecycle with startup detection and autonomous restart, isolated data only."""
# ruff: noqa: DTZ005, DTZ011 -- local calendar dates are the application contract.
import argparse
import json
import sqlite3
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from verify_ledger import request, start, stop


def verify(exe):
    root = Path(tempfile.mkdtemp(prefix='zhishi-followup-frozen-'))
    print(f'FOLLOWUP_CHECK_ROOT={root}', flush=True)
    proc, log, port = start(exe, root, 'seed')
    try:
        p = request(port, '/api/research/projects', 'POST', {'title':'Frozen followup',
            'objective':'Practice and report findings', 'start_date':str(date.today()+timedelta(days=2))}, 201)
        pid = p['id']
        plan = request(port, f'/api/research/projects/{pid}/plans', 'POST', {'version':1,
            'rationale':'Read then practice', 'steps':[{'title':'Read', 'outcome':'Explain findings', 'minutes':45}]}, 201)
        request(port, f"/api/research/plans/{plan['id']}/apply", 'POST')
        tid = request(port, '/api/tasks')[0]['id']
    finally:
        stop(proc, log, port)
    # Change only the fixture database while its backend is stopped, simulating elapsed time.
    with sqlite3.connect(root/'v2/backend.db') as db:
        db.execute('UPDATE task_schedule_entries SET date=? WHERE task_id=?', (str(date.today()-timedelta(days=1)), tid))
    proc, log, port = start(exe, root, 'detect')
    try:
        for _ in range(100):
            rows = request(port, f'/api/followups?project_id={pid}')
            if rows and rows[0]['plan_id']:
                break
            time.sleep(.05)
        row = rows[0]
        assert row['status'] == 'pending' and row['plan_id']
        detail = request(port, f"/api/followups/{row['id']}")
        assert detail['plan']['state'] == 'draft'
        for _ in range(2):
            request(port, '/api/followups/check', 'POST', {'project_id':pid})
        assert len([n for n in request(port, '/api/notifications') if n['kind']=='followup']) == 1
        row = request(port, f"/api/followups/{row['id']}")
        snoozed = request(port, f"/api/followups/{row['id']}/respond", 'POST', {'version':row['version'],
            'snooze_until':(datetime.now()+timedelta(hours=2)).isoformat()})
        request(port, f"/api/followups/{row['id']}/apply", 'POST', {'version':row['version']}, 409)
    finally:
        stop(proc, log, port)
    proc, log, port = start(exe, root, 'snooze-restart')
    try:
        assert request(port, f"/api/followups/{row['id']}")['status'] == 'snoozed'
        assert len(request(port, '/api/tasks')) == 1
        request(port, '/api/settings', 'PUT', {'settings':{'agent_autonomy':'autonomous','feature_autopilot_enabled':'true'}})
    finally:
        stop(proc, log, port)
    with sqlite3.connect(root/'v2/backend.db') as db:
        db.execute('UPDATE secretary_followups SET snoozed_until=? WHERE id=?',
            ((datetime.now()-timedelta(minutes=1)).isoformat(), snoozed['id']))
    proc, log, port = start(exe, root, 'autonomous-restart')
    try:
        for _ in range(100):
            final = request(port, f"/api/followups/{row['id']}")
            if final['status'] == 'applied':
                break
            time.sleep(.05)
        assert final['status'] == 'applied' and final['plan']['state'] == 'applied'
        assert [t['id'] for t in request(port, '/api/tasks')] == [tid]
        assert request(port, f"/api/followups/{row['id']}/apply", 'POST', {'version':1})['status'] == 'applied'
        notes = [n for n in request(port, '/api/notifications') if n['kind']=='followup']
        assert len(notes) == 2 and sum(n['read_at'] is None for n in notes) == 1
        assert all(n['target_path'].startswith(f'/research?project={pid}&followup=') for n in notes)
        request(port, '/api/followups/check', 'POST', {'project_id':pid})
        assert len([n for n in request(port, '/api/notifications') if n['kind']=='followup']) == 2
        (root/'result.json').write_text(json.dumps({'ok':True,'project_id':pid,'task_id':tid,
            'followup_id':row['id'],'notifications':len(notes)}), encoding='utf8')
    finally:
        stop(proc, log, port)
    print('FOLLOWUP_FROZEN_PASS: startup, preview, deduplication, snooze, stale rejection, persistence, authorized autonomous restart, terminal retry', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('exe', type=Path)
    verify(parser.parse_args().exe.resolve())
