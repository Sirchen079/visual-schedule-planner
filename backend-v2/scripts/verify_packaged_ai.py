"""Exercise the frozen backend against a loopback-only fake OpenAI provider, with isolated data."""
import argparse
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        resumed = any(m.get('role') == 'tool' for m in request['messages'])
        delta = {'content': 'Created the approved test task.'} if resumed else {
            'role': 'assistant', 'tool_calls': [{'index': 0, 'id': 'release-call', 'type': 'function',
                'function': {'name': 'create_task', 'arguments': '{"title":"packaged-ai-check"}'}}]}
        def chunk(part, reason=None):
            return {'id': 'chatcmpl-release', 'object': 'chat.completion.chunk', 'created': 0,
                    'model': 'release-check', 'choices': [{'index': 0, 'delta': part, 'finish_reason': reason}]}
        payload = ''.join('data: ' + json.dumps(c) + '\n\n' for c in (
            chunk(delta), chunk({}, 'stop' if resumed else 'tool_calls'))) + 'data: [DONE]\n\n'
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Content-Length', str(len(payload.encode())))
        self.end_headers()
        self.wfile.write(payload.encode())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('exe', type=Path)
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix='zhishi-packaged-ai-'))
    print(f'AI_CHECK_ROOT={root}', flush=True)
    provider = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    def call(method, path, body=None):
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=45)
        try:
            conn.request(method, path, None if body is None else json.dumps(body),
                         {'Content-Type': 'application/json'})
            response = conn.getresponse()
            raw = response.read().decode()
            return response.status, raw
        finally:
            conn.close()
    def api(method, path, body=None):
        code, raw = call(method, path, body)
        assert 200 <= code < 300, (path, code, raw)
        return json.loads(raw)
    def events(raw):
        return [json.loads(line[6:]) for line in raw.splitlines() if line.startswith('data: ')]
    env = dict(os.environ, ZHISHI_DATA_DIR=str(root))
    env.pop('ZHISHI_FRONTEND_DIR', None)
    with (root / 'backend.log').open('wb') as log:
        process = subprocess.Popen([str(args.exe.resolve()), '--port', str(port)], cwd=root,
                                   env=env, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            for _ in range(180):
                try:
                    if api('GET', '/health')['ok']:
                        break
                except (OSError, AssertionError):
                    time.sleep(0.25)
            else:
                raise AssertionError('Backend failed to start')
            # Only this newly created isolated configuration stores a disposable dummy credential.
            config = api('POST', '/ai/configs', {'name': 'release-check-disposable', 'model': 'release-check',
                'base_url': f'http://127.0.0.1:{provider.server_port}/v1',
                'api_key': 'release-check-placeholder-not-a-real-key'})
            api('POST', f'/ai/configs/{config["id"]}/enable')
            api('PUT', '/api/settings', {'settings': {'agent_autonomy': 'careful'}})
            code, raw = call('POST', '/ai/chat/stream', {'message': 'Create packaged-ai-check after approval.'})
            assert code == 200, raw
            first = events(raw)
            assert first[0]['type'] == 'run_started' and first[-1]['type'] == 'done', first
            approval = next(e for e in first if e['type'] == 'tool_approval_requested')
            assert api('GET', '/api/tasks') == [], 'Tool executed before approval'
            api('POST', f'/ai/actions/{approval["action_id"]}/approve')
            cid = first[0]['conversation_id']
            code, raw = call('POST', f'/ai/conversations/{cid}/resume/stream')
            assert code == 200, raw
            resumed = events(raw)
            assert resumed[-1]['type'] == 'done' and not any(e['type'] == 'run_error' for e in resumed), resumed
            tasks = api('GET', '/api/tasks')
            assert len(tasks) == 1 and tasks[0]['title'] == 'packaged-ai-check', tasks
            code, _ = call('POST', f'/ai/conversations/{cid}/resume/stream')
            assert code == 400, 'Duplicate resume accepted'
            print('PACKAGED_AI_APPROVAL_RESUME_PASS provider=loopback-fake tasks=1 duplicate_resume=400', flush=True)
        finally:
            try:
                call('POST', '/shutdown')
                process.wait(timeout=20)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)
                provider.shutdown()
                provider.server_close()
                # Delete only the dummy credentials referenced by this fresh test database.
                db_path = root / 'v2' / 'backend.db'
                if db_path.exists():
                    from zhishi.infra.secrets import delete_api_key
                    with sqlite3.connect(db_path) as db:
                        for (ref,) in db.execute('SELECT api_key_ref FROM ai_configs WHERE name = ?',
                                                 ('release-check-disposable',)):
                            if ref:
                                delete_api_key(ref)
                print(f'BACKEND_EXIT={process.returncode}', flush=True)


if __name__ == '__main__':
    main()
