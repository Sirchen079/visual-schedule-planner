"""Real frozen 2.10 -> current upgrade, immutable citations, full-page MCP and optional public web/UI.

Only isolated temporary data and local fixture services are used. --live reads a
public Python documentation page through the actual configured builtin reader.
No model credentials or production databases are used.
"""
# ruff: noqa: DTZ011 -- v2 schedules follow local calendar dates.
import argparse
import http.client
import json
import os
import sqlite3
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

import verify_capabilities as fixtures
from verify_ledger import start, stop

BODY = '原版引用：先解释概念，再独立实践。\n' + '学习记录：用例子检验理解，写下推导过程与适用条件。\n' * 2300 + '最后练习：整理对照表并解释选择依据。'


def request(port, path, method='GET', body=None, expected=200):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=60)
    try:
        conn.request(method, path, json.dumps(body) if body is not None else None,
                     {'Content-Type':'application/json'} if body is not None else {})
        response = conn.getresponse()
        raw = response.read()
        assert response.status == expected, (path, response.status, raw[:500])
        return json.loads(raw) if raw else None
    finally:
        conn.close()


def verify(exe, old_exe, qa, electron=None, live=False):
    qa.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='zhishi-web-snapshots-'))
    report = {'root':str(root), 'checks':[], 'passed':False}
    fixture = fixtures.MCPFixture()
    fixtures.WEB_REPORT = BODY
    proc = log = port = None
    try:
        fixture.start()
        proc, log, port = start(old_exe, root, 'old-2.10.0')
        server = request(port, '/ai/mcp/servers', 'POST', {'name':'网页长文验收', 'transport':'http',
            'url':f'http://127.0.0.1:{fixture.port}/mcp','enabled':True,'auto_approve_readonly':True}, 201)
        request(port, '/ai/web-services', 'PUT', {'fetch_provider':'mcp', 'mcp_fetch':{
            'server_id':server['id'],'tool_name':'mapped_read','url_argument':'targets',
            'url_as_list':True,'content_path':'pages.0.body'}})
        day = date.today() + timedelta(days=2)
        project = request(port, '/api/research/projects', 'POST', {'title':'网页教程学习',
            'objective':'阅读完整教程并完成最后练习','start_date':str(day),
            'end_date':str(day + timedelta(days=13))}, 201)
        base = f"/api/research/projects/{project['id']}"
        original = request(port, base+'/sources','POST',{'url':fixtures.PUBLIC_URL,'title':'长篇学习教程'},201)
        assert original['status'] == 'verified', original['error']
        assert 0 < len(original['content']) <= 8000 and len(original['content']) < len(BODY)
        old_read = request(port, f"/api/materials/{original['library_file_id']}?part=1&count=1")
        assert old_read['document']['partial'] and old_read['document']['indexed_chars'] == len(original['content'])
        reference = {'source_id':original['id'],'part':1,'revision':old_read['document']['revision'],
            'quote':'先解释概念，再独立实践'}
        plan = request(port,base+'/plans','POST',{'version':project['version'],'rationale':'先理解基础再开展练习',
            'steps':[{'title':'完成基础阅读','outcome':'解释概念并举例','minutes':30,'source_refs':[reference]}]},201)
        request(port,f"/api/research/plans/{plan['id']}/apply",'POST',{})
        old_tasks = request(port, '/api/tasks')
        stop(proc, log, port); proc = log = port = None
        with sqlite3.connect(root/'v2/backend.db') as db:
            assert 'superseded_by' not in [r[1] for r in db.execute('PRAGMA table_info(research_sources)')]
        proc, log, port = start(exe, root, 'upgraded')
        actual = request(port, base)['sources'][0]
        assert all(actual[key] == value for key,value in original.items() if key != 'document')
        assert actual['superseded_by'] is None
        report['checks'].append('2.10 source, task and citation preserved on schema upgrade')
        if electron:
            state = {'port':port,'project_id':project['id'],'source_id':original['id'],
                'original_file_id':original['library_file_id'],'original_revision':old_read['document']['revision'],
                'body_chars':len(BODY)}
            (qa/'web-ui-state.json').write_text(json.dumps(state), encoding='utf-8')
            env = dict(os.environ)
            env.pop('ELECTRON_RUN_AS_NODE',None)
            done = subprocess.run([str(electron),str(Path(__file__).with_name('verify_web_ui.cjs')),str(qa)],
                env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=150,check=False,
                creationflags=subprocess.CREATE_NO_WINDOW)
            (qa/'web-ui.log').write_text(done.stdout+'\n'+done.stderr,encoding='utf-8')
            assert done.returncode == 0, done.stdout[-1200:] + done.stderr[-1200:]
            report['checks'].append('native Vue refresh, late-text search, reader navigation, historical task citation and themes')
        else:
            request(port,base+f"/sources/{original['id']}/fetch?refresh=true",'POST',{})
        detail = request(port, base)
        current = next(s for s in detail['sources'] if not s['superseded_by'])
        assert current['id'] != original['id'] and current['document']['indexed_chars'] == len(BODY)
        assert current['document']['partial'] and 'mcp' in ' '.join(current['document']['warnings'])
        hit = request(port, '/api/materials/search?'+urlencode({'file_id':current['library_file_id'],'query':'最后练习'}))['hits'][0]
        tail_path = f"/api/materials/{current['library_file_id']}?"+urlencode({'part':hit['part'],'revision':hit['revision']})
        tail = request(port, tail_path)
        assert '整理对照表' in tail['parts'][0]['text']
        assert request(port, f"/api/materials/{original['library_file_id']}?part=1&count=1") == old_read
        assert request(port, '/api/tasks') == old_tasks
        repeat = request(port, base+'/sources','POST',{'url':fixtures.PUBLIC_URL,'refresh':True},201)
        assert repeat['id'] == current['id'] and len(request(port,base)['sources']) == 2
        fixtures.WEB_REPORT = ''
        failed = request(port,base+f"/sources/{current['id']}/fetch?refresh=true",'POST',{})
        assert failed['status'] == 'verified' and '已保留原版本' in failed['error']
        fixtures.WEB_REPORT = BODY
        recovered = request(port,base+f"/sources/{current['id']}/fetch?refresh=true",'POST',{})
        assert recovered['id'] == current['id'] and not recovered['error']
        report['checks'].append('full MCP body, late citation, immutable old plan, replay, failure and recovery')
        report['document'] = current['document']
        if live:
            request(port, '/ai/web-services','PUT',{'fetch_provider':'builtin'})
            public = request(port,base+'/sources','POST',{'url':'https://docs.python.org/3/tutorial/datastructures.html',
                'title':'Python 官方教程：数据结构'},201)
            assert public['status'] == 'verified', public['error']
            assert public['document']['indexed_chars'] > 8000
            public_hit = request(port,'/api/materials/search?'+urlencode({'file_id':public['library_file_id'],
                'query':'Comparing Sequences'}))['hits']
            assert public_hit
            last = request(port,f"/api/materials/{public['library_file_id']}?part={public['document']['total_parts']}")
            assert last['parts'] and last['next_call'] is None
            report['public_page'] = {'url':public['url'],'document':public['document'],'matching_parts':len(public_hit)}
            report['checks'].append('live Python documentation archived beyond preview and last segment readable')
        stop(proc,log,port); proc = log = port = None
        proc,log,port = start(exe,root,'restart')
        assert request(port,tail_path) == tail
        assert request(port,f"/api/materials/{original['library_file_id']}?part=1&count=1") == old_read
        assert request(port,'/api/tasks') == old_tasks
        report['checks'].append('new and old snapshots readable after process restart')
        report['passed'] = True
    finally:
        if proc is not None:
            stop(proc,log,port)
        fixture.close()
        report['owned_processes_stopped'] = True
        (qa/'web-snapshots.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('WEB_SNAPSHOTS_UPGRADE_RESTART_PASS',flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('exe',type=Path)
    parser.add_argument('--old-exe',type=Path,required=True)
    parser.add_argument('--qa',type=Path,required=True)
    parser.add_argument('--electron',type=Path)
    parser.add_argument('--live',action='store_true')
    args=parser.parse_args()
    verify(args.exe.resolve(),args.old_exe.resolve(),args.qa.resolve(),args.electron.resolve() if args.electron else None,args.live)
