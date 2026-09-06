"""Native main/widget + actual process restart; only temporary data and loopback fixtures."""
import argparse
import http.client
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from verify_ledger import start, stop
from verify_web_snapshots import request

REPO=Path(__file__).resolve().parents[1]
MARKERS=['A_SEED','W_SEED','A_SLOW','A_AFTER_CANCEL','APPROVAL_A','A_HARD_CRASH','A_AFTER_RESTART']


def verify(exe,electron,qa):
    qa.mkdir(parents=True,exist_ok=True)
    root=Path(tempfile.mkdtemp(prefix='zhishi-session-check-'))
    captured=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass

        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            messages=body['messages']
            last=next((m for m in reversed(messages) if m['role']=='user'),{})
            marker=next((m for m in MARKERS if m in str(last.get('content',''))),'summary')
            captured.append({'marker':marker,'messages':messages,'stream':body.get('stream',False)})
            if not body.get('stream'):
                raw=json.dumps({'id':'summary','object':'chat.completion','created':0,'model':body['model'],
                    'choices':[{'index':0,'message':{'role':'assistant','content':'【用户目标】继续处理当前会话\n【已办事项】保留当前会话记录\n【关键偏好】无\n【未完成事项】按用户后续要求处理'},'finish_reason':'stop'}],
                    'usage':{'prompt_tokens':10,'completion_tokens':10,'total_tokens':20}}).encode()
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Connection','close');self.end_headers()
            def frame(delta,reason=None):
                chunk={'id':'session-fixture','object':'chat.completion.chunk','created':0,'model':body['model'],
                    'choices':[{'index':0,'delta':delta,'finish_reason':reason}]}
                self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode());self.wfile.flush()
            try:
                if marker in ('A_SLOW','A_HARD_CRASH'):
                    for index in range(35):
                        frame({'content':f'PARTIAL_{marker}_{index} '});time.sleep(.25)
                elif messages[-1]['role']=='tool':
                    frame({'content':'APPROVAL_RESOLVED'})
                elif marker=='APPROVAL_A':
                    frame({'tool_calls':[{'index':0,'id':'approval-call','type':'function','function':{'name':'delete_task','arguments':'{"task_id":999999}'}}]})
                    frame({},'tool_calls');self.wfile.write(b'data: [DONE]\n\n');return
                else: frame({'content':'REPLY '+marker})
                frame({},'stop');self.wfile.write(b'data: [DONE]\n\n')
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError): pass
            finally:self.close_connection=True

    provider=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    provider.daemon_threads=True
    threading.Thread(target=provider.serve_forever,daemon=True).start()
    proc=log=port=None
    report={'root':str(root),'passed':False,'mode':'frozen' if exe else 'source'}
    def chat(cid,message):
        conn=http.client.HTTPConnection('127.0.0.1',port,timeout=30)
        try:
            conn.request('POST','/ai/chat/stream',json.dumps({'message':message,'conversation_id':cid}),{'Content-Type':'application/json'})
            response=conn.getresponse();raw=response.read().decode()
            assert response.status==200,(response.status,raw)
            return raw
        finally:conn.close()
    def launch(label):
        if exe:return start(exe,root,label)
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));chosen=sock.getsockname()[1]
        output=(root/(label+'.log')).open('wb')
        process=subprocess.Popen([sys.executable,'-m','zhishi.server.app','--port',str(chosen)],cwd=REPO,
            env={**os.environ,'ZHISHI_DATA_DIR':str(root)},stdout=output,stderr=output,creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(200):
            if process.poll() is not None:raise RuntimeError('source backend exited')
            try:request(chosen,'/health');return process,output,chosen
            except (OSError,AssertionError):time.sleep(.1)
        raise TimeoutError('source startup')
    def ui(phase):
        (qa/'session-state.json').write_text(json.dumps({'port':port}),encoding='utf-8')
        env=dict(os.environ);env.pop('ELECTRON_RUN_AS_NODE',None)
        result=subprocess.run([str(electron),str(Path(__file__).with_suffix('.cjs')),str(qa),phase],
            env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
        (qa/f'session-ui-{phase}.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
        assert result.returncode==0,result.stdout[-1000:]+result.stderr[-2000:]
    try:
        proc,log,port=launch('first')
        config=request(port,'/ai/configs','POST',{'name':'session-fixture','model':'session-fixture',
            'provider_kind':'openai_compat','base_url':f'http://127.0.0.1:{provider.server_port}/v1',
            'api_key':'session-disposable-placeholder','context_window':128000,'max_output_tokens':1024},201)
        request(port,f"/ai/configs/{config['id']}/enable",'POST',{})
        ui('seed')
        old_port=port;stop(proc,log,port);proc=log=None
        proc,log,port=launch('restart');assert port!=old_port
        ui('restore')
        selections=json.loads((qa/'session-selections.json').read_text(encoding='utf-8'))
        cid=selections['main']
        def crash_request():
            try:chat(cid,'A_HARD_CRASH')
            except (OSError,AssertionError,http.client.HTTPException):pass
        with ThreadPoolExecutor() as pool:
            future=pool.submit(crash_request)
            for _ in range(100):
                time.sleep(.1)
                rows=request(port,f'/ai/conversations/{cid}')
                if 'PARTIAL_A_HARD_CRASH_4' in str(rows):break
            else:raise AssertionError('no durable stream checkpoint before crash')
            proc.kill();proc.wait(timeout=10);log.close();proc=log=None
            future.result(timeout=10)
        proc,log,port=launch('after-hard-crash')
        recovered=request(port,f'/ai/conversations/{cid}/state')
        assert recovered['status']=='interrupted' and recovered['active_run_id'] is None,recovered
        rows=request(port,f'/ai/conversations/{cid}')
        assert 'PARTIAL_A_HARD_CRASH_4' in str(rows)
        assert 'run_error' not in chat(cid,'A_AFTER_RESTART')
        continued=next(c for c in reversed(captured) if c['marker']=='A_AFTER_RESTART')
        assert 'PARTIAL_A_HARD_CRASH_4' in str(continued['messages'])
        for item in captured:
            transcript=json.dumps(item['messages'])
            if item['marker']=='W_SEED':assert all(m not in transcript for m in MARKERS if m!='W_SEED')
            elif item['marker']!='summary':assert 'W_SEED' not in transcript
        report.update(passed=True,checks=['main/widget scope and live synchronization','cancel checkpoint preservation',
            'approval and per-window drafts across distinct backend ports','hard process termination checkpoint recovery',
            'next provider request includes pre-crash partial response','provider transcripts exclude other conversation markers'],
            provider_requests=[{'marker':c['marker'],'message_count':len(c['messages'])} for c in captured],selections=selections)
    finally:
        if proc is not None:stop(proc,log,port)
        provider.shutdown();provider.server_close()
        from zhishi.infra.secrets import delete_api_key,load_api_key
        database=root/'v2/backend.db'
        refs=[]
        if database.exists():
            with sqlite3.connect(database) as db:refs=[r[0] for r in db.execute('SELECT api_key_ref FROM ai_configs WHERE name=?',('session-fixture',)) if r[0]]
            for ref in refs:delete_api_key(ref);assert load_api_key(ref) is None
        report['test_credentials_removed']=len(refs)
        report['owned_processes_stopped']=True
        (qa/'sessions.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('SESSION_NATIVE_RESTART_PASS',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--backendexe',type=Path);parser.add_argument('--electron',type=Path,required=True);parser.add_argument('--qa',type=Path,required=True)
    args=parser.parse_args();verify(args.backendexe.resolve() if args.backendexe else None,args.electron.resolve(),args.qa.resolve())
