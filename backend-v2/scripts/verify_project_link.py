"""Verify current branding, repository links, and non-migration using an isolated runtime."""
import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from verify_ledger import request, start, stop


def verify(exe, electron, qa):
    qa.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='zhishi-brand-'))
    legacy = root/'app.db'
    with sqlite3.connect(legacy) as db:
        db.execute('CREATE TABLE tasks(id INTEGER PRIMARY KEY,title TEXT)')
        db.execute('INSERT INTO tasks VALUES(1,?)', ('LEGACY_MUST_NOT_BE_IMPORTED',))
    original = hashlib.sha256(legacy.read_bytes()).hexdigest()
    proc, log, port = start(exe, root, 'brand')
    try:
        assert request(port, '/health')['version'] == '2.14.2'
        assert request(port, '/api/tasks') == []
        (qa/'brand-state.json').write_text(json.dumps({'port': port}), encoding='utf-8')
        env = dict(os.environ); env.pop('ELECTRON_RUN_AS_NODE', None)
        result = subprocess.run([str(electron), str(Path(__file__).with_suffix('.cjs')), str(qa)],
            env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120,
            creationflags=subprocess.CREATE_NO_WINDOW)
        (qa/'brand-ui.log').write_text(result.stdout+'\n'+result.stderr, encoding='utf-8')
        assert result.returncode == 0, result.stderr[-2500:]
        assert hashlib.sha256(legacy.read_bytes()).hexdigest() == original
    finally:
        stop(proc, log, port)
    (qa/'brand.json').write_text(json.dumps({'passed': True, 'root': str(root),
        'checks': ['health version 2.14.2', 'legacy database unchanged and not imported',
                   'visible global and settings Star links', 'exact repository external target',
                   '900px layout and document title'], 'owned_processes_stopped': True}, indent=2), encoding='utf-8')
    print('ZHISHI_BRAND_NATIVE_PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('exe', type=Path)
    parser.add_argument('--electron', type=Path, required=True)
    parser.add_argument('--qa', type=Path, required=True)
    args = parser.parse_args()
    verify(args.exe.resolve(), args.electron.resolve(), args.qa.resolve())
