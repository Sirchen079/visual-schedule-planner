"""Inspect actual provider requests from native main/widget new-conversation UI flows."""
import argparse
import json
import os
import sqlite3
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from verify_ledger import start, stop
from verify_web_snapshots import request

MARKERS = ['CHAT_OLD_ONLY_A', 'CHAT_NEW_ONLY_B', 'CHAT_CONTINUE_B', 'CHAT_NEW_ONLY_C',
           'WIDGET_OLD_ONLY_D', 'WIDGET_NEW_ONLY_E']
KEY = 'chat-isolation-disposable-test-key'


def verify(exe, electron, qa):
    qa.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='zhishi-chat-isolation-'))
    captured = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert self.path == '/v1/chat/completions'
            assert self.headers.get('Authorization') == f'Bearer {KEY}'
            messages = body['messages']
            last = next(m for m in reversed(messages) if m['role'] == 'user')
            text = json.dumps(last['content'], ensure_ascii=False)
            marker = next(m for m in MARKERS if m in text)
            captured.append({'marker':marker, 'messages':messages})
            answer = f'已收到 {marker}'
            def frame(delta, reason=None):
                return {'id':'chat-isolation','object':'chat.completion.chunk','created':0,'model':body['model'],
                    'choices':[{'index':0,'delta':delta,'finish_reason':reason}]}
            raw = (''.join('data: '+json.dumps(x)+'\n\n' for x in [
                frame({'role':'assistant','content':answer}),frame({},'stop')]) + 'data: [DONE]\n\n').encode()
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream')
            self.send_header('Content-Length',str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    provider = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread = threading.Thread(target=provider.serve_forever,daemon=True)
    thread.start()
    proc = log = port = None
    report = {'root':str(root),'passed':False,'provider_requests':[]}
    try:
        proc,log,port = start(exe,root,'backend')
        config = request(port,'/ai/configs','POST',{'name':'新对话隔离验收','provider_kind':'openai_compat',
            'model':'chat-isolation-fixture','base_url':f'http://127.0.0.1:{provider.server_port}/v1',
            'api_key':KEY,'context_window':128000,'max_output_tokens':1024},201)
        request(port,f"/ai/configs/{config['id']}/enable",'POST',{})
        (qa/'chat-isolation-state.json').write_text(json.dumps({'port':port}),encoding='utf-8')
        env = dict(os.environ)
        env.pop('ELECTRON_RUN_AS_NODE',None)
        done = subprocess.run([str(electron),str(Path(__file__).with_suffix('.cjs')),str(qa)],env=env,
            capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180,check=False,
            creationflags=subprocess.CREATE_NO_WINDOW)
        (qa/'chat-isolation-ui.log').write_text(done.stdout+'\n'+done.stderr,encoding='utf-8')
        assert done.returncode == 0, done.stdout[-1200:]+done.stderr[-1200:]
        report['received_order'] = [c['marker'] for c in captured]
        assert report['received_order'] == MARKERS
        for index,item in enumerate(captured):
            text = json.dumps(item['messages'],ensure_ascii=False)
            expected = {item['marker']} | ({MARKERS[1]} if index == 2 else set())
            seen = {marker for marker in MARKERS if marker in text}
            report['provider_requests'].append({'message':item['marker'],'seen_markers':sorted(seen),
                'user_messages':sum(m['role']=='user' for m in item['messages'])})
            assert seen == expected, (index,seen,expected)
            assert 'OLD_DRAFT_ATTACHMENT' not in text
        conversations = request(port,'/ai/conversations')
        assert len(conversations) == 5
        history = {c['title']:request(port,f"/ai/conversations/{c['id']}") for c in conversations}
        assert sorted(len(v) for v in history.values()) == [2,2,2,2,4]
        assert sum('CHAT_OLD_ONLY_A' in json.dumps(v) for v in history.values()) == 1
        report['conversation_count'] = len(conversations)
        report['history_message_counts'] = sorted(len(v) for v in history.values())
        report['passed'] = True
    finally:
        if proc is not None:
            stop(proc,log,port)
        provider.shutdown();provider.server_close();thread.join(timeout=5)
        from zhishi.infra.secrets import delete_api_key, load_api_key
        database = root/'v2/backend.db'
        if database.is_file():
            with sqlite3.connect(database) as db:
                refs = [row[0] for row in db.execute('SELECT api_key_ref FROM ai_configs WHERE name = ?',('新对话隔离验收',))]
            for ref in refs:
                if ref:
                    delete_api_key(ref)
                    assert load_api_key(ref) is None
            report['test_credentials_removed'] = len(refs)
        report['owned_processes_stopped'] = True
        (qa/'chat-isolation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('CHAT_MAIN_WIDGET_CONTEXT_ISOLATION_PASS',flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('exe',type=Path)
    parser.add_argument('--electron',type=Path,required=True)
    parser.add_argument('--qa',type=Path,required=True)
    args=parser.parse_args()
    verify(args.exe.resolve(),args.electron.resolve(),args.qa.resolve())
