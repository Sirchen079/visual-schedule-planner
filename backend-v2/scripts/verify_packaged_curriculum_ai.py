"""Frozen Agent clock, content revision, recovery and history through a loopback model."""
import argparse
import json
import sqlite3
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from verify_learning import seed
from verify_ledger import request, start, stop
from verify_packaged_inbox_ai import stream


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.server.steps += 1
            step = self.server.steps
            returns = [m for m in body['messages'] if m.get('role') == 'tool']
            latest = json.loads(returns[-1]['content']) if returns else None
            name, args = None, None
            assert any('【实时本机时钟】' in str(m.get('content','')) for m in body['messages'])
            if step == 1:
                name, args = 'get_current_time', {}
            elif step == 2:
                from datetime import datetime
                assert datetime.fromisoformat(latest['now']).tzinfo is not None
                self.server.base_date = latest['date']
                name, args = 'resolve_local_date', {'expression':'后天','reference_date':latest['date']}
            elif step in (3, 5):
                if step == 3:
                    from datetime import date, timedelta
                    assert latest['date'] == str(date.fromisoformat(self.server.base_date)+timedelta(days=2))
                name, args = 'preview_research_revision', {'project_id':self.server.pid, 'plan':{
                    'version':2,'mode':'replace','target_link_id':999999 if step == 3 else self.server.target['id'],
                    'movable_task_link_ids':[self.server.target['id']],
                    'rationale':'Replace the untouched task with a small example, with permission to move its manual slot.',
                    'steps':[{'title':'Explain a small example','outcome':'Record each variable and result','minutes':45}]}}
            elif step == 4:
                assert latest['code'] == 'research_conflict'
                name, args = latest['next_call']['tool'], latest['next_call']['args']
            elif step == 6:
                self.server.plan_id = latest['plan']['id']
                assert latest['plan']['revision']['before_task'] == self.server.target
                name, args = latest['next_call']['tool'], latest['next_call']['args']
            elif step == 7:
                assert latest['state'] == 'applied' and latest['result']['replaced_tasks'] == 1
                name, args = 'list_research_plans', {'project_id':self.server.pid}
            elif step == 8:
                assert latest['items'][0]['id'] == self.server.plan_id
                name, args = latest['items'][0]['read_call']['tool'], latest['items'][0]['read_call']['args']
            else:
                assert step == 9 and latest['revision']['before_task'] == self.server.target
            delta = {'content':'The task content was revised; original notes are available in history.'} if name is None else {
                'role':'assistant', 'tool_calls':[{'index':0, 'id':f'learning-{step}', 'type':'function',
                    'function':{'name':name, 'arguments':json.dumps(args)}}]}
            def chunk(part, reason=None):
                return {'id':'chatcmpl-learning', 'object':'chat.completion.chunk', 'created':0, 'model':'curriculum-check',
                        'choices':[{'index':0, 'delta':part, 'finish_reason':reason}]}
            payload = ''.join('data: '+json.dumps(c)+'\n\n' for c in [chunk(delta), chunk({}, 'tool_calls' if name else 'stop')])+'data: [DONE]\n\n'
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Content-Length', str(len(payload.encode())))
            self.end_headers()
            self.wfile.write(payload.encode())
        except Exception as exc:  # noqa: BLE001 -- expose assertions from the provider thread.
            self.server.errors.append(repr(exc))
            self.send_error(500)


def verify(exe):
    root = Path(tempfile.mkdtemp(prefix='zhishi-curriculum-ai-frozen-'))
    print(f'CURRICULUM_AI_CHECK_ROOT={root}', flush=True)
    provider = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    provider.steps, provider.errors = 0, []
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    proc, log, port = start(exe, root, 'backend')
    try:
        base, _, detail = seed(port)
        provider.pid = detail['project']['id']
        provider.target = detail['tasks'][1]
        cfg = request(port, '/ai/configs', 'POST', {'name':'curriculum-check-disposable', 'model':'curriculum-check',
            'base_url':f'http://127.0.0.1:{provider.server_port}/v1', 'api_key':'learning-placeholder-not-a-real-key'}, 201)
        request(port, f'/ai/configs/{cfg["id"]}/enable', 'POST')
        events = stream(port, '/ai/chat/stream', {'message':'Replace the untouched experiment with a small example. You may move its manual time.', 'research_project_id':provider.pid})
        assert len(request(port, '/api/tasks')) == 2
        assert any(e['type'] == 'tool_call_result' and not e['ok'] for e in events)
        approval = next(e for e in events if e['type'] == 'tool_approval_requested')
        assert 'Explain a small example' in approval['preview']
        request(port, f'/ai/actions/{approval["action_id"]}/approve', 'POST')
        stream(port, f'/ai/conversations/{events[0]["conversation_id"]}/resume/stream')
        after = request(port, base)
        assert after['project']['total_tasks'] == 2 and after['project']['completed_tasks'] == 1
        assert after['tasks'][0] == detail['tasks'][0]
        assert after['tasks'][1]['task_id'] == provider.target['task_id']
        assert after['tasks'][1]['title'] == 'Explain a small example'
        assert provider.steps == 9 and not provider.errors, provider.errors
        print('CURRICULUM_AI_FROZEN_PASS: 9 model rounds, live clock, relative date, bad target, exact recovery, revision preview, concrete approval, resume, history, same task identity', flush=True)
    finally:
        try:
            stop(proc, log, port)
        finally:
            provider.shutdown()
            provider.server_close()
            from zhishi.infra.secrets import delete_api_key
            with sqlite3.connect(root/'v2'/'backend.db') as db:
                for (ref,) in db.execute('SELECT api_key_ref FROM ai_configs WHERE name = ?', ('curriculum-check-disposable',)):
                    if ref:
                        delete_api_key(ref)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('exe', type=Path)
    verify(parser.parse_args().exe.resolve())
