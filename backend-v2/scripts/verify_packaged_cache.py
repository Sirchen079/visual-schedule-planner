"""Exercise packaged chat and cache metrics with a local synthetic provider."""
import argparse
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        assert body['stream'] is True
        chunks = [
            {'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': '验收通过'},
                          'finish_reason': None}]},
            {'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]},
            {'choices': [], 'usage': {'prompt_tokens': 1000, 'completion_tokens': 10,
                'total_tokens': 1010, 'prompt_tokens_details': {'cached_tokens': 900}}},
        ]
        data = ''.join('data: ' + json.dumps({'id': 'mock', 'object': 'chat.completion.chunk',
            'created': 1, 'model': 'mock-cache-acceptance', **chunk}) + '\n\n' for chunk in chunks)
        payload = (data + 'data: [DONE]\n\n').encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def verify(exe, report_path):
    provider = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]

    def request(path, body=None, *, text=False):
        raw = None if body is None else json.dumps(body).encode()
        req = Request(f'http://127.0.0.1:{port}{path}', data=raw,
                      headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=60) as response:
            result = response.read().decode()
        return result if text else json.loads(result)

    with tempfile.TemporaryDirectory(prefix='zhishi-packaged-cache-') as root:
        env = {**os.environ, 'ZHISHI_DATA_DIR': root}
        env.pop('ZHISHI_FRONTEND_DIR', None)
        with (Path(root) / 'backend.log').open('wb') as log:
            proc = subprocess.Popen([str(exe.resolve()), '--port', str(port)], cwd=root,
                env=env, stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            try:
                deadline = time.monotonic() + 60
                while True:
                    try:
                        health = request('/health')
                        break
                    except OSError:
                        if time.monotonic() > deadline:
                            raise RuntimeError('Packaged backend did not start') from None
                        time.sleep(.2)
                assert health['version'] == '2.21.0', health
                assert request('/ai/cache/stats')['totals']['cache_hit_rate'] is None
                assert '<html' in request('/', text=True).lower()
                config = request('/ai/configs', {'name': 'Isolated cache acceptance',
                    'provider_kind': 'openai_compat', 'model': 'mock-cache-acceptance',
                    'base_url': f'http://127.0.0.1:{provider.server_port}/v1',
                    'api_key': 'synthetic-not-a-real-credential'})
                request(f"/ai/configs/{config['id']}/enable", {})
                cid = None
                for _ in range(2):
                    body = {'message': '请简短回复，不执行工具。'}
                    if cid is not None:
                        body['conversation_id'] = cid
                    stream = request('/ai/chat/stream', body, text=True)
                    events = [json.loads(line[6:]) for line in stream.splitlines()
                              if line.startswith('data: ')]
                    assert not [e for e in events if e['type'] == 'run_error'], events
                    cid = events[0]['conversation_id']
                    usage = next(e['usage'] for e in events if e['type'] == 'run_completed')
                    assert usage['cache_hit_rate'] == .9, usage
                    assert usage['requests'] == 1, usage
                totals = request('/ai/cache/stats')['totals']
                assert totals['input_tokens'] == 2000 and totals['cache_read_tokens'] == 1800
                assert totals['cache_hit_rate'] == .9 and totals['measurement_coverage'] == 1
                report_path.write_text(json.dumps({'health': health, 'totals': totals,
                    'provider': 'local synthetic streaming server', 'personal_data_used': False},
                    ensure_ascii=False, indent=2), encoding='utf8')
                print('PACKAGED_CACHE_PASS')
            finally:
                try:
                    request('/shutdown', {})
                    proc.wait(timeout=15)
                except Exception:
                    proc.terminate()
                    proc.wait(timeout=10)
                provider.shutdown()
                provider.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    verify(args.exe, args.report)
