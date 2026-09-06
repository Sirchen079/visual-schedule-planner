"""Frozen upgrade, native settings and actual scheduled material collection, using isolated data."""
# ruff: noqa: DTZ005 -- v2 uses local wall time.
import argparse
import json
import os
import sqlite3
import subprocess
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import verify_capabilities as fixtures
from verify_ledger import start, stop
from verify_web_snapshots import request


def verify(exe, old_exe, electron, qa):
    qa.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='zhishi-research-watches-'))
    report = {'root':str(root),'checks':[],'passed':False}
    fixture = fixtures.MCPFixture()
    fixtures.WEB_REPORT = '原始教程：先解释基础概念。'
    proc = log = port = None
    try:
        fixture.start()
        proc,log,port = start(old_exe,root,'old-2.11.0')
        server = request(port,'/ai/mcp/servers','POST',{'name':'资料跟进验收','transport':'http',
            'url':f'http://127.0.0.1:{fixture.port}/mcp','enabled':True,'auto_approve_readonly':True},201)
        request(port,'/ai/web-services','PUT',{'search_provider':'mcp','fetch_provider':'mcp',
            'mcp_search':{'server_id':server['id'],'tool_name':'mapped_search','query_argument':'needle',
                'limit_argument':'count','results_path':'payload.hits','title_field':'heading','url_field':'link','description_field':'summary'},
            'mcp_fetch':{'server_id':server['id'],'tool_name':'mapped_read','url_argument':'targets',
                'url_as_list':True,'content_path':'pages.0.body'}})
        project = request(port,'/api/research/projects','POST',{'title':'教程资料跟进',
            'objective':'PRIVATE_OBJECTIVE_DO_NOT_SEARCH','background':'PRIVATE_BACKGROUND_DO_NOT_SEARCH'},201)
        base = f"/api/research/projects/{project['id']}"
        original = request(port,base+'/sources','POST',{'url':fixtures.PUBLIC_URL,'title':'原始教程'},201)
        original_read = request(port,f"/api/materials/{original['library_file_id']}")
        plan = request(port,base+'/plans','POST',{'version':project['version'],'rationale':'保留旧资料引用',
            'steps':[{'title':'读基础概念','outcome':'举例解释概念','minutes':30,'source_refs':[{
                'source_id':original['id'],'part':1,'revision':original_read['document']['revision'],'quote':'先解释基础概念'}]}]},201)
        request(port,f"/api/research/plans/{plan['id']}/apply",'POST',{})
        tasks = request(port,'/api/tasks')
        stop(proc,log,port); proc=log=port=None
        with sqlite3.connect(root/'v2/backend.db') as db:
            assert not db.execute("SELECT name FROM sqlite_master WHERE name='research_watches'").fetchall()
        proc,log,port = start(exe,root,'upgrade')
        assert request(port,base+'/watch')['version'] == 0
        assert request(port,'/api/tasks') == tasks
        assert request(port,f"/api/materials/{original['library_file_id']}") == original_read
        report['checks'].append('2.11 upgrade preserves project, plan, tasks and old source; no subscription enabled')
        fixtures.WEB_REPORT = '更新教程：继续学习后续概念。\n' + '学习正文与可核对的练习。\n'*1000
        (qa/'watch-ui-state.json').write_text(json.dumps({'port':port,'project_id':project['id']}),encoding='utf-8')
        env=dict(os.environ); env.pop('ELECTRON_RUN_AS_NODE',None)
        done = subprocess.run([str(electron),str(Path(__file__).with_name('verify_watch_ui.cjs')),str(qa)],
            env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180,
            creationflags=subprocess.CREATE_NO_WINDOW,check=False)
        (qa/'watch-ui.log').write_text(done.stdout+'\n'+done.stderr,encoding='utf-8')
        assert done.returncode == 0, done.stdout[-1000:]+done.stderr[-1200:]
        state = request(port,base+'/watch')
        assert state['config']['enabled'] and state['config']['frequency'] == 'daily'
        assert len(state['runs']) == 2
        assert request(port,f"/api/materials/{original['library_file_id']}") == original_read
        assert request(port,'/api/tasks') == tasks
        notifications = request(port,'/api/notifications')
        report['native_notifications'] = notifications
        report['checks'].append('native configuration, collection, unchanged run, pause, reader and notification')
        stop(proc,log,port); proc=log=port=None
        fixtures.WEB_REPORT += '\n新增结尾练习：写出一个独立例子。'
        # Set only the known isolated test watch due; the real frozen scheduler must pick it up.
        with sqlite3.connect(root/'v2/backend.db') as db:
            db.execute('UPDATE research_watches SET next_run_at=? WHERE project_id=?',
                ((datetime.now()-timedelta(days=7)).isoformat(' '),project['id']))
        proc,log,port = start(exe,root,'due-restart')
        for _ in range(100):
            state = request(port,base+'/watch')
            if len(state['runs']) == 3 and state['runs'][0]['status'] != 'running':
                break
            time.sleep(1)
        assert len(state['runs']) == 3 and state['runs'][0]['status'] == 'updated', state
        assert len([s for s in state['runs'][0]['sources'] if s['changed']]) == 2
        assert datetime.fromisoformat(state['next_run_at']) > datetime.now()
        assert all(c['needle']=='公开教程 更新' for c in fixture.calls if c['tool']=='mapped_search')
        assert request(port,f"/api/materials/{original['library_file_id']}") == original_read
        assert request(port,'/api/tasks') == tasks
        report['checks'].append('actual frozen scheduler catches up once after seven missed days, changes saved as new snapshots')
        stop(proc,log,port); proc=log=port=None
        proc,log,port = start(exe,root,'final-restart')
        assert request(port,base+'/watch')['runs'] == state['runs']
        paused = request(port,base+'/watch','PUT',{**state['config'],'enabled':False,'version':state['version']})
        assert not paused['config']['enabled']
        request(port,base+'/watch/run','POST',{},422)
        assert request(port,'/api/tasks') == tasks
        report['checks'].append('restart keeps history and next due; pause prevents additional collection; no schedule mutation')
        report['state'] = state
        report['search_queries'] = [c['needle'] for c in fixture.calls if c['tool']=='mapped_search']
        report['passed']=True
    finally:
        if proc is not None:
            stop(proc,log,port)
        fixture.close()
        report['owned_processes_stopped']=True
        (qa/'research-watches.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('WATCH_FROZEN_UPGRADE_SCHEDULER_RESTART_PASS',flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('exe',type=Path)
    parser.add_argument('--old-exe',type=Path,required=True)
    parser.add_argument('--electron',type=Path,required=True)
    parser.add_argument('--qa',type=Path,required=True)
    args=parser.parse_args()
    verify(args.exe.resolve(),args.old_exe.resolve(),args.electron.resolve(),args.qa.resolve())
