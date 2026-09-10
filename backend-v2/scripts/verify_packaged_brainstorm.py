"""Verify the frozen interview/answer flow against a synthetic local provider."""
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
    captured = []
    mode = 'normal'

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.captured.append(body)
        assert body['stream'] is True
        tool_results = [m for m in body['messages'] if m['role'] == 'tool']
        call = None
        if self.mode == 'brainstorm' and not tool_results:
            call = {'name': 'ask_user', 'arguments': json.dumps({'questions': [
                {'id': 'goal', 'question': '这次最想解决什么问题？'}]}, ensure_ascii=False)}
        elif self.mode == 'plan' and not tool_results:
            call = {'name': 'propose_plan', 'arguments': json.dumps({'title': '测试计划', 'steps': [
                {'action': '查看待办', 'tool': 'list_tasks'}]}, ensure_ascii=False)}
        delta = {'tool_calls': [{'index': 0, 'id': 'mock-call', 'type': 'function', 'function': call}]} if call else {'content': '已收到，请继续补充想法。'}
        chunks = [{'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]},
                  {'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'tool_calls' if call else 'stop'}]},
                  {'choices': [], 'usage': {'prompt_tokens': 1000, 'completion_tokens': 10,
                    'total_tokens': 1010, 'prompt_tokens_details': {'cached_tokens': 900}}}]
        payload = (''.join('data: ' + json.dumps({'id': 'mock', 'object': 'chat.completion.chunk',
            'created': 1, 'model': 'mock-brainstorm', **chunk}) + '\n\n' for chunk in chunks) + 'data: [DONE]\n\n').encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def verify(exe: Path, report: Path):
    provider = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]

    def request(path, body=None, text=False):
        req = Request(f'http://127.0.0.1:{port}{path}', data=None if body is None else json.dumps(body).encode(),
                      headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=60) as response:
            value = response.read().decode()
        return value if text else json.loads(value)

    def events(path, body):
        result = [json.loads(line[6:]) for line in request(path, body, True).splitlines() if line.startswith('data: ')]
        assert not any(e['type'] == 'run_error' for e in result), result
        return result

    with tempfile.TemporaryDirectory(prefix='zhishi-brainstorm-acceptance-') as root:
        env = {**os.environ, 'ZHISHI_DATA_DIR': root}
        env.pop('ZHISHI_FRONTEND_DIR', None)
        with (Path(root) / 'backend.log').open('wb') as log:
            proc = subprocess.Popen([str(exe.resolve()), '--port', str(port)], cwd=root, env=env,
                stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            try:
                deadline = time.monotonic() + 60
                while True:
                    try:
                        health = request('/health')
                        break
                    except OSError:
                        if time.monotonic() > deadline or proc.poll() is not None:
                            raise RuntimeError('Frozen backend failed to start') from None
                        time.sleep(.2)
                assert health['version'] == '2.21.0'
                cfg = request('/ai/configs', {'name': 'Isolated acceptance', 'provider_kind': 'openai_compat',
                    'model': 'mock-brainstorm', 'base_url': f'http://127.0.0.1:{provider.server_port}/v1',
                    'api_key': 'synthetic-not-a-real-credential'})
                request(f"/ai/configs/{cfg['id']}/enable", {})
                normal = events('/ai/chat/stream', {'message': '帮我理清思路'})
                assert '内置·梳理想法' in json.dumps(Provider.captured[-1], ensure_ascii=False)
                Provider.mode = 'brainstorm'
                interview = events('/ai/chat/stream', {'message': '帮我问清所有决策', 'brainstorm_mode': True})
                cid = interview[0]['conversation_id']
                question = next(e['request'] for e in interview if e['type'] == 'user_input_requested')
                request(f"/ai/conversations/{cid}/questions/{question['id']}/answer", {
                    'version': 0, 'answers': {'goal': {'text': '确认每周可以投入的时间'}}})
                resumed = events(f'/ai/conversations/{cid}/resume/stream', {})
                payload = Provider.captured[-1]
                assert '内置·完整决策访谈' in json.dumps(payload, ensure_ascii=False)
                names = [t['function']['name'] for t in payload['tools']]
                assert 'ask_user' in names and 'propose_plan' not in names and 'create_task' not in names
                assert not any(e['type'] == 'plan_card' for e in resumed)
                assert request('/api/tasks') == []
                Provider.mode = 'plan'
                plan = events('/ai/chat/stream', {'message': '请拟定计划', 'plan_mode': True})
                assert any(e['type'] == 'plan_card' for e in plan)
                assert '【计划模式】' in json.dumps(Provider.captured[-1], ensure_ascii=False)
                totals = request('/ai/cache/stats')['totals']
                assert totals['cache_hit_rate'] == .9
                report.write_text(json.dumps({'health': health, 'normal_skill': True, 'brainstorm_ask_answer_resume': True,
                    'brainstorm_readonly': True, 'plan_card': True, 'cache_hit_rate': totals['cache_hit_rate'],
                    'personal_data_used': False}, ensure_ascii=False, indent=2), encoding='utf-8')
                print('PACKAGED_BRAINSTORM_PASS')
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
