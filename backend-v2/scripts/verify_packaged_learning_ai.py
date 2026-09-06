"""Frozen Agent feedback, recovery and approved continuation using a loopback fake model."""
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

REPORT = {'note':'The example ran, but I need a concrete explanation.', 'difficulty':'too_hard', 'actual_minutes':75}


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
            if step in (1, 2, 8):
                if step == 2:
                    self.server.fid = latest['feedback']['id']
                    assert latest['context']['project']['version'] == 3
                name, args = 'record_research_feedback', {'project_id':self.server.pid, 'version':2, 'report':REPORT}
            elif step in (3, 5):
                if step == 3:
                    assert latest['feedback']['id'] == self.server.fid
                name, args = 'preview_research_extension', {'project_id':self.server.pid, 'plan':{'version':3,
                    'rationale':'Provide a concrete example in response to the reported difficulty.',
                    'feedback_ids':[999999 if step == 3 else self.server.fid],
                    'steps':[{'title':'Explain a new example', 'outcome':'Explain every step', 'minutes':45}]}}
            elif step == 4:
                assert latest['code'] == 'research_conflict'
                name, args = latest['next_call']['tool'], latest['next_call']['args']
            elif step == 6:
                self.server.plan_id = latest['plan']['id']
                name, args = latest['next_call']['tool'], latest['next_call']['args']
            elif step == 7:
                assert latest['state'] == 'applied'
                name, args = 'apply_research_plan', {'plan_id':self.server.plan_id}
            else:
                assert step == 9 and latest['feedback']['id'] == self.server.fid
                assert latest['context']['project']['total_tasks'] == 3
            delta = {'content':'Feedback saved; a follow-on exercise is scheduled.'} if name is None else {
                'role':'assistant', 'tool_calls':[{'index':0, 'id':f'learning-{step}', 'type':'function',
                    'function':{'name':name, 'arguments':json.dumps(args)}}]}
            def chunk(part, reason=None):
                return {'id':'chatcmpl-learning', 'object':'chat.completion.chunk', 'created':0, 'model':'learning-check',
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
    root = Path(tempfile.mkdtemp(prefix='zhishi-learning-ai-frozen-'))
    print(f'LEARNING_AI_CHECK_ROOT={root}', flush=True)
    provider = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    provider.steps, provider.errors = 0, []
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    proc, log, port = start(exe, root, 'backend')
    try:
        base, _, detail = seed(port)
        provider.pid = detail['project']['id']
        cfg = request(port, '/ai/configs', 'POST', {'name':'learning-check-disposable', 'model':'learning-check',
            'base_url':f'http://127.0.0.1:{provider.server_port}/v1', 'api_key':'learning-placeholder-not-a-real-key'}, 201)
        request(port, f'/ai/configs/{cfg["id"]}/enable', 'POST')
        events = stream(port, '/ai/chat/stream', {'message':REPORT['note'], 'research_project_id':provider.pid})
        assert len(request(port, '/api/tasks')) == 2
        assert any(e['type'] == 'tool_call_result' and not e['ok'] for e in events)
        approval = next(e for e in events if e['type'] == 'tool_approval_requested')
        request(port, f'/ai/actions/{approval["action_id"]}/approve', 'POST')
        stream(port, f'/ai/conversations/{events[0]["conversation_id"]}/resume/stream')
        after = request(port, base)
        assert after['project']['total_tasks'] == 3 and after['project']['completed_tasks'] == 1
        assert after['tasks'][:2] == detail['tasks']
        assert after['feedback']['total'] == 1 and after['feedback']['items'][0]['applied_plan_ids'] == [provider.plan_id]
        assert provider.steps == 9 and not provider.errors, provider.errors
        print('LEARNING_AI_FROZEN_PASS: 9 model rounds, self-report, duplicate, bad feedback id, exact recovery, preview, approval, resume, replay, one additional task', flush=True)
    finally:
        try:
            stop(proc, log, port)
        finally:
            provider.shutdown()
            provider.server_close()
            from zhishi.infra.secrets import delete_api_key
            with sqlite3.connect(root/'v2'/'backend.db') as db:
                for (ref,) in db.execute('SELECT api_key_ref FROM ai_configs WHERE name = ?', ('learning-check-disposable',)):
                    if ref:
                        delete_api_key(ref)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('exe', type=Path)
    verify(parser.parse_args().exe.resolve())
