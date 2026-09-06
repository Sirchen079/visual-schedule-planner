"""Frozen Agent followup protocol with stale-version recovery and approval resumption."""
# ruff: noqa: DTZ011 -- local calendar dates are the application contract.
import argparse
import json
import sqlite3
import tempfile
import threading
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

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
            if step == 1:
                name, args = 'check_research_progress', {'project_id':self.server.pid}
            elif step == 2:
                self.server.followup_id = latest['id']
                assert latest['plan_summary']['state'] == 'draft'
                name, args = 'apply_secretary_followup', {'followup_id':latest['id'], 'version':1}
            elif step == 3:
                assert latest['ok'] is False and latest['code'] == 'followup_conflict'
                name, args = latest['next_call']['tool'], latest['next_call']['args']
                assert name == 'get_secretary_followup'
            elif step == 4:
                name, args = latest['next_call']['tool'], latest['next_call']['args']
                assert name == 'apply_secretary_followup' and args['version'] > 1
            elif step == 5:
                assert latest['status'] == 'applied'
                name, args = 'apply_secretary_followup', {'followup_id':self.server.followup_id, 'version':1}
            elif step == 6:
                assert latest['status'] == 'applied'
                name, args = latest['next_call']['tool'], latest['next_call']['args']
            else:
                assert step == 7 and latest['project']['total_tasks'] == 1
            delta = {'content':'The existing learning task has been rescheduled.'} if name is None else {
                'role':'assistant', 'tool_calls':[{'index':0, 'id':f'followup-{step}', 'type':'function',
                    'function':{'name':name, 'arguments':json.dumps(args)}}]}
            def chunk(part, reason=None):
                return {'id':'chatcmpl-followup', 'object':'chat.completion.chunk', 'created':0,
                    'model':'followup-check', 'choices':[{'index':0, 'delta':part, 'finish_reason':reason}]}
            payload = ''.join('data: '+json.dumps(c)+'\n\n' for c in [chunk(delta),
                chunk({}, 'tool_calls' if name else 'stop')])+'data: [DONE]\n\n'
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Content-Length', str(len(payload.encode())))
            self.end_headers()
            self.wfile.write(payload.encode())
        except Exception as exc:  # noqa: BLE001 -- record provider-thread failures.
            self.server.errors.append(repr(exc))
            self.send_error(500)


def verify(exe):
    root = Path(tempfile.mkdtemp(prefix='zhishi-followup-ai-frozen-'))
    print(f'FOLLOWUP_AI_CHECK_ROOT={root}', flush=True)
    provider = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    provider.steps, provider.errors = 0, []
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    proc, log, port = start(exe, root, 'backend')
    try:
        p = request(port, '/api/research/projects', 'POST', {'title':'AI followup project',
            'objective':'Practice and report findings', 'start_date':str(date.today()+timedelta(days=2))}, 201)
        provider.pid = p['id']
        plan = request(port, f"/api/research/projects/{p['id']}/plans", 'POST', {'version':1,
            'rationale':'Read then practice', 'steps':[{'title':'Read', 'outcome':'Explain findings', 'minutes':45}]}, 201)
        request(port, f"/api/research/plans/{plan['id']}/apply", 'POST')
        member = request(port, f"/api/research/projects/{p['id']}")['tasks'][0]
        request(port, f"/api/schedule/entries/{member['slots'][0]['id']}", 'PATCH', {'date':str(date.today()-timedelta(days=1))})
        cfg = request(port, '/ai/configs', 'POST', {'name':'followup-check-disposable', 'model':'followup-check',
            'base_url':f'http://127.0.0.1:{provider.server_port}/v1', 'api_key':'followup-placeholder-not-a-real-key'}, 201)
        request(port, f"/ai/configs/{cfg['id']}/enable", 'POST')
        events = stream(port, '/ai/chat/stream', {'message':'Follow up my learning project and adjust the missed time.',
            'research_project_id':p['id']})
        cid = events[0]['conversation_id']
        approvals, failures = 0, 0
        while True:
            assert not any(e['type'] == 'run_error' for e in events), events
            failures += sum(e['type'] == 'tool_call_result' and not e['ok'] for e in events)
            approval = next((e for e in events if e['type'] == 'tool_approval_requested'), None)
            if approval is None:
                break
            approvals += 1
            assert approvals <= 2
            assert request(port, f"/api/followups/{provider.followup_id}")['plan']['state'] == 'draft'
            request(port, f"/ai/actions/{approval['action_id']}/approve", 'POST')
            events = stream(port, f'/ai/conversations/{cid}/resume/stream')
        assert approvals == 2 and failures == 1 and provider.steps == 7 and not provider.errors, provider.errors
        assert request(port, f"/api/followups/{provider.followup_id}")['status'] == 'applied'
        assert [t['id'] for t in request(port, '/api/tasks')] == [member['task_id']]
        (root/'result.json').write_text(json.dumps({'ok':True, 'steps':provider.steps, 'approvals':approvals,
            'recovered_errors':failures, 'task_id':member['task_id']}), encoding='utf8')
        print('FOLLOWUP_AI_FROZEN_PASS: guided check, stale version, exact recovery, approval, resume, existing task adjustment, terminal retry, progress', flush=True)
    finally:
        try:
            stop(proc, log, port)
        finally:
            provider.shutdown()
            provider.server_close()
            from zhishi.infra.secrets import delete_api_key
            with sqlite3.connect(root/'v2/backend.db') as db:
                for (ref,) in db.execute('SELECT api_key_ref FROM ai_configs WHERE name = ?', ('followup-check-disposable',)):
                    if ref:
                        delete_api_key(ref)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('exe', type=Path)
    verify(parser.parse_args().exe.resolve())
