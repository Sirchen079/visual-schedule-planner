"""Native settings UI + restart acceptance with a disposable loopback model catalog."""
import argparse
import json
import os
import sqlite3
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def verify(exe: Path, qa: Path, app_dir: Path | None = None):
    qa.mkdir(parents=True,exist_ok=True)
    root=Path(tempfile.mkdtemp(prefix='zhishi-settings-check-'))
    calls=[]
    class Catalog(BaseHTTPRequestHandler):
        def do_GET(self):
            allowed=self.headers.get('Authorization')=='Bearer disposable-catalog-check'
            calls.append({'path':self.path,'authenticated':allowed})
            if self.path!='/v1/models':
                code,payload=404,{'error':'unknown path'}
            elif allowed:
                code,payload=200,{'data':[{'id':'catalog-alpha'},{'id':'catalog-beta','name':'Beta'}]}
            else:
                code,payload=401,{'error':'invalid credential'}
            raw=json.dumps(payload).encode()
            self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def log_message(self,*args):
            pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Catalog)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        for mode in ('seed','check'):
            env={**os.environ,'ZHISHI_SHELL_USER_DATA_DIR':str(root/'profile'),'ZHISHI_SHELL_DATA_DIR':str(root/'data'),
                'ZHISHI_SETTINGS_SMOKE':mode,'ZHISHI_SETTINGS_QA':str(qa),'ZHISHI_MODELS_TEST_URL':f'http://127.0.0.1:{server.server_port}/v1'}
            env.pop('ELECTRON_RUN_AS_NODE',None)
            done=subprocess.run([str(exe),*([str(app_dir)] if app_dir else []),'--smoke-quit','--settings-selftest'],env=env,capture_output=True,
                text=True,encoding='utf-8',errors='replace',timeout=180,check=False,creationflags=subprocess.CREATE_NO_WINDOW)
            (qa/f'settings-{mode}.log').write_text(done.stdout+'\n'+done.stderr,encoding='utf-8')
            assert done.returncode==0,(mode,done.stdout[-1800:],done.stderr[-500:])
        assert len(calls)>=3 and any(not c['authenticated'] for c in calls)
        result={'passed':True,'dataRoot':str(root),'catalogCalls':calls,
                'ui':json.loads((qa/'settings-ui.json').read_text()),'restart':json.loads((qa/'settings-restart.json').read_text())}
        (qa/'settings-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print('SETTINGS_NATIVE_AND_RESTART_PASS',flush=True)
    finally:
        server.shutdown();server.server_close();worker.join(timeout=5)
        # Only disposable keys created by this isolated settings acceptance run.
        database=root/'data'/'v2'/'backend.db'
        if database.is_file():
            from zhishi.infra.secrets import delete_api_key
            with sqlite3.connect(database) as db:
                for (ref,) in db.execute('SELECT api_key_ref FROM ai_configs WHERE name = ?', ('模型列表验收',)):
                    if ref:
                        delete_api_key(ref)
                for (ref,) in db.execute('SELECT value FROM app_settings WHERE key = ?', ('web_services_tavily_key_ref',)):
                    if ref:
                        delete_api_key(ref)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('exe',type=Path)
    parser.add_argument('--qa',type=Path,required=True)
    parser.add_argument('--app-dir',type=Path,help='Optional Electron source app directory for prepackaging UI acceptance')
    args=parser.parse_args()
    verify(args.exe.resolve(),args.qa.resolve(),args.app_dir.resolve() if args.app_dir else None)
