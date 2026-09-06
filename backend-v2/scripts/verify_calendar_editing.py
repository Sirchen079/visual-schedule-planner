"""Calendar editor acceptance using the frozen app and a disposable database."""
import argparse
import json
import os
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path

from verify_ledger import request, start, stop


def verify(exe, electron, qa):
    qa.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='zhishi-calendar-edit-'))
    today = date.today()
    proc, log, port = start(exe, root, 'first')
    try:
        single = request(port, '/api/schedule/events', 'POST', {
            'title': '日历编辑验收', 'date': today.isoformat(), 'start_time': '09:00',
            'end_time': '10:00', 'location': '旧会议室', 'notes': '原备注', 'remind_offsets': [30]}, 201)
        series = request(port, '/api/schedule/events', 'POST', {
            'title': '重复行程验收', 'date': (today-timedelta(days=7)).isoformat(),
            'start_time': '11:00', 'end_time': '12:00', 'recur_rrule': 'FREQ=WEEKLY;COUNT=5',
            'remind_offsets': [15]}, 201)
        state = {'port': port, 'single': single, 'series': series}
        (qa/'calendar-state.json').write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
        env = dict(os.environ)
        env.pop('ELECTRON_RUN_AS_NODE', None)
        result = subprocess.run([str(electron), str(Path(__file__).with_suffix('.cjs')), str(qa)],
            env=env, capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=150, creationflags=subprocess.CREATE_NO_WINDOW)
        (qa/'calendar-ui.log').write_text(result.stdout+'\n'+result.stderr, encoding='utf-8')
        assert result.returncode == 0, result.stdout[-1500:]+result.stderr[-2000:]
        before = [request(port, f"/api/schedule/events/{e['id']}") for e in [single, series]]
    finally:
        stop(proc, log, port)
    proc, log, port = start(exe, root, 'restart')
    try:
        after = [request(port, f"/api/schedule/events/{e['id']}") for e in [single, series]]
        assert before == after
        assert after[0]['title'] == '已修改的行程' and after[0]['remind_offsets'] == [30]
        assert after[1]['date'] == series['date'] and after[1]['recur_rrule'] == series['recur_rrule']
        assert after[1]['title'] == '已修改的重复系列' and after[1]['remind_offsets'] == [15]
    finally:
        stop(proc, log, port)
    (qa/'calendar.json').write_text(json.dumps({'passed': True, 'root': str(root),
        'checks': ['native week/day/month click editing', 'invalid time and server failure retain form',
                   'save updates visible calendar', 'date change and all-day edit',
                   'series anchor/rule and reminder preservation', 'restart preserves both edits'],
        'owned_processes_stopped': True}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('CALENDAR_EDIT_NATIVE_RESTART_PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('exe', type=Path)
    parser.add_argument('--electron', type=Path, required=True)
    parser.add_argument('--qa', type=Path, required=True)
    args = parser.parse_args()
    verify(args.exe.resolve(), args.electron.resolve(), args.qa.resolve())
