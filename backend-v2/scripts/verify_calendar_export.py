"""Exercise the visible export button and real Electron download in an isolated app."""
import argparse
import json
import os
import subprocess
import tempfile
from datetime import date, datetime
from pathlib import Path

from icalendar import Calendar
from verify_ledger import request, start, stop


def verify(exe, electron, qa):
    qa.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='zhishi-export-'))
    proc, log, port = start(exe, root, 'export')
    try:
        today = date.today().isoformat()
        for event in [
            {'title': '导出会议', 'date': today, 'start_time': '09:00', 'end_time': '10:00',
             'notes': '中文备注\n第二行', 'location': '会议室', 'recur_rrule': 'FREQ=WEEKLY;COUNT=3'},
            {'title': '全天日程', 'date': today},
            {'title': '只有开始时间', 'date': today, 'start_time': '16:30'},
        ]:
            request(port, '/api/schedule/events', 'POST', event, 201)
        (qa/'export-state.json').write_text(json.dumps({'port': port}), encoding='utf-8')
        env = dict(os.environ); env.pop('ELECTRON_RUN_AS_NODE', None)
        result = subprocess.run([str(electron), str(Path(__file__).with_suffix('.cjs')), str(qa)],
            env=env, capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
        (qa/'export-ui.log').write_text(result.stdout+'\n'+result.stderr, encoding='utf-8')
        assert result.returncode == 0, result.stderr[-2500:]
        events = Calendar.from_ical((qa/'downloaded-calendar.ics').read_bytes()).walk('VEVENT')
        by_title = {str(e['SUMMARY']): e for e in events}
        assert len(by_title) == 3
        assert by_title['导出会议']['RRULE']['COUNT'] == [3]
        assert str(by_title['导出会议']['DESCRIPTION']) == '中文备注\n第二行'
        assert type(by_title['全天日程'].decoded('DTSTART')) is date
        assert by_title['只有开始时间'].decoded('DTSTART').time() == datetime.strptime('16:30', '%H:%M').time()
        assert len({str(e['UID']) for e in events}) == 3
        assert all('DTSTAMP' in e for e in events)
    finally:
        stop(proc, log, port)
    (qa/'export.json').write_text(json.dumps({'passed': True, 'root': str(root),
        'checks': ['visible button', 'blocked request and retry', 'actual Electron download',
                   'Chinese notes and recurrence', 'all-day DATE and start-only time', 'stable UID fields',
                   '900px toolbar visibility'], 'owned_processes_stopped': True}, indent=2), encoding='utf-8')
    print('CALENDAR_EXPORT_NATIVE_PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('exe', type=Path)
    parser.add_argument('--electron', type=Path, required=True)
    parser.add_argument('--qa', type=Path, required=True)
    args = parser.parse_args()
    verify(args.exe.resolve(), args.electron.resolve(), args.qa.resolve())
