"""Test the shipped Agent with an intentionally fallible loopback model."""
# ruff: noqa: DTZ011 -- v2 uses local calendar dates.
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
from verify_research import upload


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
                name, args = 'create_research_project', {'spec':{'title':'Frozen AI learning project',
                    'objective':'Run an example and write three findings', 'start_date':str(date.today()+timedelta(days=2)),
                    'window_start':'18:30', 'window_end':'21:00'}}
            elif step == 2:
                self.server.pid = latest['project']['id']
                name, args = 'attach_research_material', {'project_id':self.server.pid, 'file_id':self.server.file_id}
            elif step in (3, 5):
                sid = 999999 if step == 3 else latest['sources'][0]['id']
                version = 1 if step == 3 else latest['project']['version']
                name, args = 'preview_research_plan', {'project_id':self.server.pid, 'plan':{'version':version,
                    'rationale':'Read, practice, then reflect.', 'steps':[{'title':'Read and practice',
                        'outcome':'Run one example and record findings', 'minutes':90, 'source_ids':[sid]}]}}
            elif step == 4:
                assert latest['ok'] is False and latest['code'] == 'research_conflict'
                name, args = latest['next_call']['tool'], latest['next_call']['args']
            elif step == 6:
                self.server.plan_id = latest['plan']['id']
                name, args = latest['next_call']['tool'], latest['next_call']['args']
            elif step == 7:
                assert latest['state'] == 'applied'
                name, args = 'apply_research_plan', {'plan_id':self.server.plan_id}
            elif step == 8:
                name, args = 'get_research_project', {'project_id':self.server.pid}
            elif step == 9:
                assert latest['project']['total_tasks'] == 2
            elif step == 10:
                prompt = json.dumps(body['messages'], ensure_ascii=False)
                assert '【当前打开的学习/研究项目】' in prompt and 'Run an example and write three findings' in prompt
            assert step <= 10
            delta = {'content':'The project has two real tasks and its reference material.'} if name is None else {
                'role':'assistant', 'tool_calls':[{'index':0, 'id':f'research-{step}', 'type':'function',
                    'function':{'name':name, 'arguments':json.dumps(args)}}]}
            def chunk(part, reason=None):
                return {'id':'chatcmpl-research', 'object':'chat.completion.chunk', 'created':0, 'model':'research-check',
                        'choices':[{'index':0, 'delta':part, 'finish_reason':reason}]}
            payload = ''.join('data: '+json.dumps(c)+'\n\n' for c in [chunk(delta), chunk({}, 'tool_calls' if name else 'stop')])+'data: [DONE]\n\n'
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream')
            self.send_header('Content-Length',str(len(payload.encode())))
            self.end_headers()
            self.wfile.write(payload.encode())
        except Exception as exc:  # noqa: BLE001 -- report failures from the provider thread.
            self.server.errors.append(repr(exc))
            self.send_error(500)


def verify(exe):
    root = Path(tempfile.mkdtemp(prefix='zhishi-research-ai-frozen-'))
    print(f'RESEARCH_AI_CHECK_ROOT={root}', flush=True)
    provider = ThreadingHTTPServer(('127.0.0.1',0),Provider)
    provider.steps, provider.errors = 0, []
    threading.Thread(target=provider.serve_forever,daemon=True).start()
    proc, log, port = start(exe,root,'backend')
    try:
        provider.file_id = upload(port)
        cfg = request(port,'/ai/configs','POST',{'name':'research-check-disposable', 'model':'research-check',
            'base_url':f'http://127.0.0.1:{provider.server_port}/v1', 'api_key':'research-placeholder-not-a-real-key'},201)
        request(port,f"/ai/configs/{cfg['id']}/enable",'POST')
        events = stream(port,'/ai/chat/stream',{'message':'Create a learning project using this material and arrange time.', 'attachment_ids':[provider.file_id]})
        assert request(port,'/api/tasks') == []
        assert any(e['type'] == 'tool_call_result' and not e['ok'] for e in events)
        approval = next(e for e in events if e['type'] == 'tool_approval_requested')
        request(port,f"/ai/actions/{approval['action_id']}/approve",'POST')
        stream(port,f"/ai/conversations/{events[0]['conversation_id']}/resume/stream")
        assert len(request(port,'/api/tasks')) == 2 and provider.steps == 9
        stream(port,'/ai/chat/stream',{'message':'Read this project.', 'research_project_id':provider.pid})
        assert provider.steps == 10 and not provider.errors, provider.errors
        assert len(request(port,'/api/tasks')) == 2
        print('RESEARCH_AI_FROZEN_PASS: create, attach, wrong source recovery, preview, approval, resume, repeated apply, progress, selected project context', flush=True)
    finally:
        try:
            stop(proc,log,port)
        finally:
            provider.shutdown()
            provider.server_close()
            from zhishi.infra.secrets import delete_api_key
            with sqlite3.connect(root/'v2'/'backend.db') as db:
                for (ref,) in db.execute('SELECT api_key_ref FROM ai_configs WHERE name = ?',('research-check-disposable',)):
                    if ref:
                        delete_api_key(ref)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('exe',type=Path)
    verify(parser.parse_args().exe.resolve())
