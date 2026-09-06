"""Frozen event reminders, real scheduler recovery and old candidate compatibility."""
# ruff: noqa: DTZ005 -- v2 notification deadlines use local wall time.
import argparse
import json
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

from verify_ledger import request, start, stop


def verify(exe, previous, report):
    root = Path(tempfile.mkdtemp(prefix='zhishi-event-reminders-'))
    due = datetime.now().replace(second=0, microsecond=0) - timedelta(hours=2)
    body = {'title': '重复会议升级验收', 'date': due.date().isoformat(),
            'start_time': due.strftime('%H:%M'), 'recur_rrule': 'FREQ=DAILY;COUNT=3', 'location': '办公室'}
    candidate = {'capture_key': 'old-event-source', 'items': [{'item_key': 'meeting-1',
        'source_excerpt': '2032年1月1日上午9点到10点安排会议。', 'proposal': {'kind': 'event',
        'data': {'title': '原候选', 'date': '2032-01-01', 'start_time': '09:00', 'end_time': '10:00'}}}]}
    proc, log, port = start(previous, root, 'seed-old')
    try:
        old = request(port, '/api/schedule/events', 'POST', body, 201)
        assert 'remind_offsets' not in old
        item = request(port, '/api/inbox', 'POST', candidate, 201)[0]
    finally:
        stop(proc, log, port)
    proc, log, port = start(exe, root, 'migrate-and-remind')
    try:
        saved = request(port, f"/api/schedule/events/{old['id']}")
        assert saved == {**old, 'remind_offsets': [], 'reminder_time': None}
        assert request(port, '/api/inbox', 'POST', candidate, 201)[0]['id'] == item['id']
        revision = {**candidate['items'][0]['proposal'], 'data': {**candidate['items'][0]['proposal']['data'], 'remind_offsets': [30]}}
        item = request(port, f"/api/inbox/{item['id']}", 'PUT', {'version': item['version'], 'proposal': revision})
        applied = request(port, f"/api/inbox/{item['id']}/apply", 'POST', {'version': item['version']})
        assert request(port, f"/api/schedule/events/{applied['target_id']}")['remind_offsets'] == [30]
        request(port, f"/api/schedule/events/{old['id']}", 'PATCH', {'remind_offsets': [0, 30, 60]})
        # Simulate sleep in this disposable database after settings have been saved.
        with sqlite3.connect(root/'v2'/'backend.db') as db:
            db.execute('INSERT OR REPLACE INTO app_settings(key,value,updated_at) VALUES(?,?,?)',
                       ('task_reminder_scan_at', (due-timedelta(hours=2)).isoformat(), datetime.now().isoformat()))
        rows = []
        for _ in range(160):
            rows = request(port, '/api/notifications')
            if rows:
                break
            time.sleep(.25)
        assert len(rows) == 1, rows
        assert rows[0]['kind'] == 'event_reminder' and rows[0]['task_id'] is None
        assert rows[0]['remind_at'] == due.isoformat() and '补发提醒' in rows[0]['body']
        assert rows[0]['target_path'] == f"/calendar?date={due.date().isoformat()}&event={old['id']}"
        assert request(port, '/api/tasks') == []
    finally:
        stop(proc, log, port)
    proc, log, port = start(exe, root, 'restart-and-disable')
    try:
        assert request(port, '/api/notifications') == rows
        assert request(port, f"/api/schedule/events/{old['id']}")['remind_offsets'] == [0, 30, 60]
        assert request(port, f"/api/inbox/{item['id']}/apply", 'POST', {'version': item['version']}) == applied
        request(port, f"/api/schedule/events/{old['id']}", 'PATCH', {'remind_offsets': []})
        request(port, '/api/notifications/read-all', 'POST')
        assert request(port, '/api/notifications/unread')['count'] == 0
    finally:
        stop(proc, log, port)
    proc, log, port = start(exe, root, 'disabled-restart')
    try:
        assert request(port, f"/api/schedule/events/{old['id']}")['remind_offsets'] == []
        assert len(request(port, '/api/notifications')) == 1
    finally:
        stop(proc, log, port)
    report.write_text(json.dumps({'passed': True, 'dataRoot': str(root), 'checks': [
        'old event remains unchanged with reminders off', 'old pending candidate recapture',
        'candidate reminders apply without duplicate tasks', 'real scheduler latest catchup only',
        'occurrence link', 'restart deduplication', 'disable and restart', 'mark read']},
        ensure_ascii=False, indent=2), encoding='utf-8')
    print('EVENT_REMINDERS_FROZEN_PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('exe', type=Path)
    parser.add_argument('--previous-exe', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    verify(args.exe.resolve(), args.previous_exe.resolve(), args.report.resolve())
