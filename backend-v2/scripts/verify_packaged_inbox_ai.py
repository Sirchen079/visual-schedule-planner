"""Exercise the shipped Agent against a fallible loopback-only OpenAI-compatible provider."""
import argparse
import http.client
import json
import sqlite3
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from verify_ledger import request, start, stop

ITEM = {'item_key':'receipt-total', 'source_excerpt':'2026-09-05 paid CNY 28.50',
        'proposal': {'kind':'ledger', 'data':{'day':'2026-09-05','direction':'expense','amount':'28.50'}}}


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.server.steps += 1
            step = self.server.steps
            returns = [m for m in body['messages'] if m.get('role') == 'tool']
            name, args = 'propose_inbox_items', {'items':[ITEM]}
            if step == 1:
                assert any(t['function']['name'] == name for t in body['tools'])
                args = {'items': [{k:v for k,v in ITEM.items() if k != 'source_excerpt'}]}
            elif step == 2:
                assert 'source_excerpt' in returns[-1]['content']
            elif step == 4:
                row = json.loads(returns[-1]['content'])['items'][0]
                assert row['status'] == 'pending'
                name, args = 'apply_inbox_item', {'item_id':row['id'],'version':row['version']}
            elif step == 6:
                assert json.loads(returns[-1]['content'])['items'][0]['status'] == 'applied'
            assert step <= 6
            delta = {'content':'Confirmed once; the ledger contains this receipt.'} if step == 6 else {
                'role':'assistant', 'tool_calls':[{'index':0,'id':f'inbox-call-{step}','type':'function',
                    'function':{'name':name,'arguments':json.dumps(args)}}]}
            def chunk(part, reason=None):
                return {'id':'chatcmpl-inbox','object':'chat.completion.chunk','created':0,'model':'inbox-check',
                        'choices':[{'index':0,'delta':part,'finish_reason':reason}]}
            payload = ''.join('data: '+json.dumps(c)+'\n\n' for c in [chunk(delta),chunk({},'stop' if step == 6 else 'tool_calls')])+'data: [DONE]\n\n'
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream')
            self.send_header('Content-Length',str(len(payload.encode())))
            self.end_headers()
            self.wfile.write(payload.encode())
        except Exception as exc:  # noqa: BLE001 — report failures from the test server thread to the verifier
            self.server.errors.append(repr(exc))
            self.send_error(500)


def stream(port, path, body=None):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=45)
    try:
        conn.request('POST',path,json.dumps(body) if body is not None else None,{'Content-Type':'application/json'})
        res = conn.getresponse()
        raw = res.read().decode()
        assert res.status == 200, raw
        events = [json.loads(line[6:]) for line in raw.splitlines() if line.startswith('data: ')]
        assert events and events[-1]['type'] == 'done'
        assert not [e for e in events if e['type'] == 'run_error'], events
        return events
    finally:
        conn.close()


def verify(exe):
    root = Path(tempfile.mkdtemp(prefix='zhishi-inbox-ai-frozen-'))
    print(f'INBOX_AI_CHECK_ROOT={root}',flush=True)
    provider = ThreadingHTTPServer(('127.0.0.1',0),Provider)
    provider.steps, provider.errors = 0, []
    threading.Thread(target=provider.serve_forever,daemon=True).start()
    proc, log, port = start(exe,root,'backend')
    try:
        config = request(port,'/ai/configs','POST',{'name':'inbox-check-disposable','model':'inbox-check',
            'base_url':f'http://127.0.0.1:{provider.server_port}/v1',
            'api_key':'inbox-check-placeholder-not-a-real-key'},201)
        request(port,f"/ai/configs/{config['id']}/enable",'POST')
        events = stream(port,'/ai/chat/stream',{'message':'Organize and confirm: 2026-09-05 paid CNY 28.50'})
        assert request(port,'/api/inbox')['total'] == 1
        assert request(port,'/api/ledger')['total'] == 0
        assert any(e['type'] == 'tool_call_result' and not e['ok'] for e in events)
        approval = next(e for e in events if e['type'] == 'tool_approval_requested')
        request(port,f"/ai/actions/{approval['action_id']}/approve",'POST')
        resumed = stream(port,f"/ai/conversations/{events[0]['conversation_id']}/resume/stream")
        assert resumed[-1]['type'] == 'done'
        assert request(port,'/api/inbox')['total'] == 0
        assert request(port,'/api/inbox?status=applied')['total'] == 1
        assert request(port,'/api/ledger')['total'] == 1
        assert provider.steps == 6 and not provider.errors, provider.errors
        print('INBOX_AI_FROZEN_PASS: missing field, correction, repeated extraction, approval, resume, one real ledger entry',flush=True)
    finally:
        try:
            stop(proc,log,port)
        finally:
            provider.shutdown()
            provider.server_close()
            # Only remove throwaway secret references created in this isolated database.
            from zhishi.infra.secrets import delete_api_key
            with sqlite3.connect(root/'v2'/'backend.db') as db:
                for (ref,) in db.execute('SELECT api_key_ref FROM ai_configs WHERE name = ?',('inbox-check-disposable',)):
                    if ref:
                        delete_api_key(ref)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('exe',type=Path)
    verify(parser.parse_args().exe.resolve())
