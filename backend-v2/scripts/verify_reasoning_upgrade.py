"""Verify old model settings survive a frozen v2.9.0 -> v2.9.1 migration."""
import argparse
import json
import tempfile
from pathlib import Path

from verify_ledger import request, start, stop


def verify(exe: Path, previous: Path, report: Path):
    root = Path(tempfile.mkdtemp(prefix='zhishi-reasoning-upgrade-'))
    body = {'name': '升级验收模型', 'model': 'test-model', 'provider_kind': 'openai_responses',
            'base_url': 'https://model.example/v1', 'context_window': 128000,
            'max_output_tokens': 8192, 'input_modalities': ['text', 'image']}
    proc, log, port = start(previous, root, 'seed')
    try:
        cid = request(port, '/ai/configs', 'POST', body, 201)['id']
        request(port, f'/ai/configs/{cid}/enable', 'POST')
        old = request(port, '/ai/configs')[0]
        assert 'reasoning_effort' not in old
    finally:
        stop(proc, log, port)
    proc, log, port = start(exe, root, 'migrate')
    try:
        saved = request(port, '/ai/configs')[0]
        assert saved == {**old, 'reasoning_effort': None}
        saved = request(port, f'/ai/configs/{cid}', 'PUT', {**body, 'reasoning_effort': 'high'})
        assert saved['reasoning_effort'] == 'high' and saved['enabled']
    finally:
        stop(proc, log, port)
    proc, log, port = start(exe, root, 'restart')
    try:
        assert request(port, '/ai/configs')[0] == saved
        cleared = request(port, f'/ai/configs/{cid}', 'PUT', {**body, 'reasoning_effort': None})
        assert cleared == {**old, 'reasoning_effort': None}
    finally:
        stop(proc, log, port)
    report.write_text(json.dumps({'passed': True, 'dataRoot': str(root), 'checks': [
        'old configuration preserved with default effort', 'explicit effort update',
        'restart persistence', 'clear effort without changing enabled state or capabilities']},
        ensure_ascii=False, indent=2), encoding='utf-8')
    print('REASONING_FROZEN_UPGRADE_PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('exe', type=Path)
    parser.add_argument('--previous-exe', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    verify(args.exe.resolve(), args.previous_exe.resolve(), args.report.resolve())
