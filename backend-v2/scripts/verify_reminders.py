"""Frozen reminder recovery using disposable data and the real scheduler."""
import argparse
import json
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

from verify_ledger import request, start, stop


def verify(exe, previous_exe=None, report=None):
    root = Path(tempfile.mkdtemp(prefix='zhishi-reminders-frozen-'))
    proc, log, port = start(previous_exe or exe, root, 'seed')
    due = datetime.now().replace(second=0, microsecond=0) - timedelta(hours=2)
    future = datetime.now().replace(second=0, microsecond=0) + timedelta(hours=1)
    try:
        missed = request(port, '/api/tasks', 'POST', {'title':'漏过的报告提醒',
            'due_date':due.date().isoformat(), 'due_time':due.strftime('%H:%M'), 'remind_offsets':[0, 30, 60]}, 201)
        pending = request(port, '/api/tasks', 'POST', {'title':'尚未到点的提醒',
            'due_date':future.date().isoformat(), 'due_time':future.strftime('%H:%M'), 'remind_offsets':[0]}, 201)
    finally:
        stop(proc, log, port)
    # Simulate the last successful scan before sleeping. Only this temporary DB is opened.
    with sqlite3.connect(root / 'v2' / 'backend.db') as db:
        db.execute('INSERT OR REPLACE INTO app_settings(key,value,updated_at) VALUES(?,?,?)',
                   ('task_reminder_scan_at', (due-timedelta(hours=2)).isoformat(), datetime.now().isoformat()))
    proc, log, port = start(exe, root, 'recovery')
    try:
        deadline = time.monotonic()+40
        rows = []
        while time.monotonic() < deadline:
            rows = request(port, '/api/notifications')
            if any(n['task_id'] == missed['id'] for n in rows):
                break
            time.sleep(.25)
        assert len(rows) == 1, rows
        assert rows[0]['task_id'] == missed['id'] and '补发提醒' in rows[0]['body']
        assert rows[0]['remind_at'] == due.isoformat()
        assert rows[0]['target_path'] == f"/board?task={missed['id']}"
        assert due.strftime('%m-%d %H:%M') in rows[0]['body']
        request(port, f"/api/tasks/{pending['id']}", 'PATCH', {'due_date':None,'due_time':None,'remind_offsets':[]})
    finally:
        stop(proc, log, port)
    proc, log, port = start(exe, root, 'restart')
    try:
        assert request(port, '/api/notifications') == rows
        assert request(port, f"/api/tasks/{pending['id']}")['due_date'] is None
        request(port, '/api/notifications/read-all', 'POST')
        assert request(port, '/api/notifications/unread')['count'] == 0
    finally:
        stop(proc, log, port)
    result = {'passed':True, 'dataRoot':str(root), 'checks':['previous-version task preservation',
        'separate deadline time', 'real scheduler catchup', 'latest missed offset only',
        'future task silent', 'restart deduplication', 'clear settings persists', 'read all'],
        'notification':rows[0]}
    if report:
        report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('REMINDERS_FROZEN_PASS', json.dumps(result,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('exe',type=Path)
    parser.add_argument('--previous-exe',type=Path)
    parser.add_argument('--report',type=Path)
    args = parser.parse_args()
    verify(args.exe.resolve(), args.previous_exe.resolve() if args.previous_exe else None,args.report)
