"""Frozen Agent: long-file retrieval, bad-part recovery and a verified learning-plan citation."""
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
from verify_materials import upload
from verify_packaged_inbox_ai import stream

QUOTE = 'reproduce the baseline before comparing methods'


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        try:
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.server.steps+=1
            step=self.server.steps
            returns=[m for m in body['messages'] if m.get('role')=='tool']
            latest=json.loads(returns[-1]['content']) if returns else None
            name,args=None,None
            if step in (1,4):
                name,args='search_materials',{'file_id':self.server.fid,'query':'Final requirement'}
            elif step==2:
                name,args='read_material',{'file_id':self.server.fid,'part':999999}
            elif step==3:
                assert latest['code']=='material_conflict'
                name,args=latest['next_call']['tool'],latest['next_call']['args']
            elif step==5:
                name,args=latest['hits'][0]['next_call']['tool'],latest['hits'][0]['next_call']['args']
            elif step==6:
                self.server.part=next(p['part'] for p in latest['parts'] if QUOTE in p['text'])
                self.server.revision=latest['document']['revision']
                assert self.server.part>15
                name,args='create_research_project',{'spec':{'title':'Long-material AI project',
                    'objective':'Reproduce the baseline','start_date':str(date.today()+timedelta(days=2))}}
            elif step==7:
                self.server.pid=latest['project']['id']
                name,args='attach_research_material',{'project_id':self.server.pid,'file_id':self.server.fid}
            elif step==8:
                name,args='preview_research_plan',{'project_id':self.server.pid,'plan':{'version':1,
                    'rationale':'Follow the actual late-file requirement','steps':[{'title':'Reproduce',
                    'outcome':'Save repeatable results','minutes':45,'source_refs':[{'source_id':latest['id'],
                    'part':self.server.part,'revision':self.server.revision,'quote':QUOTE}]}]}}
            elif step==9:
                self.server.plan_id=latest['plan']['id']
                name,args=latest['next_call']['tool'],latest['next_call']['args']
            elif step==10:
                assert latest['state']=='applied'
                name,args='apply_research_plan',{'plan_id':self.server.plan_id}
            elif step==11:
                name,args='get_research_project',{'project_id':self.server.pid}
            else:
                assert step==12 and latest['project']['total_tasks']==1
                assert latest['tasks'][0]['source_refs'][0]['quote']==QUOTE
            delta={'content':'The late-file requirement is cited in the learning task.'} if name is None else {
                'role':'assistant','tool_calls':[{'index':0,'id':f'material-{step}','type':'function',
                    'function':{'name':name,'arguments':json.dumps(args)}}]}
            def chunk(part,reason=None):
                return {'id':'chatcmpl-material','object':'chat.completion.chunk','created':0,'model':'material-check',
                    'choices':[{'index':0,'delta':part,'finish_reason':reason}]}
            payload=''.join('data: '+json.dumps(c)+'\n\n' for c in [chunk(delta),chunk({},'tool_calls' if name else 'stop')])+'data: [DONE]\n\n'
            self.send_response(200);self.send_header('Content-Type','text/event-stream')
            self.send_header('Content-Length',str(len(payload.encode())));self.end_headers();self.wfile.write(payload.encode())
        except Exception as exc:  # noqa: BLE001 -- expose failures from the provider thread.
            self.server.errors.append(repr(exc));self.send_error(500)


def verify(exe):
    root=Path(tempfile.mkdtemp(prefix='zhishi-material-ai-frozen-'))
    print(f'MATERIAL_AI_CHECK_ROOT={root}',flush=True)
    provider=ThreadingHTTPServer(('127.0.0.1',0),Provider)
    provider.steps,provider.errors=0,[]
    threading.Thread(target=provider.serve_forever,daemon=True).start()
    proc,log,port=start(exe,root,'backend')
    try:
        provider.fid=upload(port,'long.txt',('Background notes. '*3000+'Final requirement: '+QUOTE+'.').encode())
        cfg=request(port,'/ai/configs','POST',{'name':'material-check-disposable','model':'material-check',
            'base_url':f'http://127.0.0.1:{provider.server_port}/v1','api_key':'material-placeholder-not-a-real-key'},201)
        request(port,f"/ai/configs/{cfg['id']}/enable",'POST')
        events=stream(port,'/ai/chat/stream',{'message':'Read the final requirement and arrange learning with the original evidence.',
            'attachment_ids':[provider.fid]})
        assert request(port,'/api/tasks')==[]
        assert any(e['type']=='tool_call_result' and not e['ok'] for e in events)
        approval=next(e for e in events if e['type']=='tool_approval_requested')
        request(port,f"/ai/actions/{approval['action_id']}/approve",'POST')
        resumed=stream(port,f"/ai/conversations/{events[0]['conversation_id']}/resume/stream")
        assert not any(e['type'] in ('run_error','tool_approval_requested') for e in resumed),resumed
        assert provider.steps==12 and not provider.errors,provider.errors
        task=request(port,'/api/tasks')[0]
        assert QUOTE in task['notes'] and len(request(port,'/api/tasks'))==1
        (root/'result.json').write_text(json.dumps({'ok':True,'steps':12,'part':provider.part,
            'revision':provider.revision,'task_id':task['id']}),encoding='utf8')
        print('MATERIAL_AI_FROZEN_PASS: retrieve tail, bad-part recovery, exact read, create project, attach, verified quote, approval/resume, terminal retry, progress',flush=True)
    finally:
        try:
            stop(proc,log,port)
        finally:
            provider.shutdown();provider.server_close()
            from zhishi.infra.secrets import delete_api_key
            with sqlite3.connect(root/'v2/backend.db') as db:
                for (ref,) in db.execute('SELECT api_key_ref FROM ai_configs WHERE name=?',('material-check-disposable',)):
                    if ref: delete_api_key(ref)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('exe',type=Path)
    verify(parser.parse_args().exe.resolve())
