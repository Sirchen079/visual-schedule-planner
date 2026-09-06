"""Authorized real-provider acceptance against a newly created, empty frozen-app database.

Only a keyring reference is accepted on the command line. This script never writes the key
to its report and deletes the temporary application's copied credential on completion.
"""
# ruff: noqa: DTZ011 -- acceptance follows the host's local calendar.
import argparse
import json
import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path

import httpx
from verify_ledger import request, start, stop
from verify_packaged_inbox_ai import stream

from zhishi.infra.secrets import delete_api_key, load_api_key


def verify(exe, key_ref, base_url, model, report_file):
    root = Path(tempfile.mkdtemp(prefix='zhishi-responses-packaged-'))
    print('PACKAGED_RESPONSES_ROOT='+str(root),flush=True)
    proc, log, port = start(exe,root,'backend')
    key = ''
    try:
        with sqlite3.connect(root/'v2/backend.db') as db:
            tables = ['tasks','events','library_files','ai_conversations','ai_configs','mcp_servers',
                      'research_projects','journal_entries','ledger_entries']
            counts = {table:db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in tables}
            assert not any(counts.values()), 'Unexpected pre-existing data in disposable database'
            assert db.execute('SELECT count(*) FROM ai_skills WHERE is_builtin = 0').fetchone()[0] == 0
            db.execute("INSERT OR REPLACE INTO app_settings(key,value,updated_at) VALUES ('agent_autonomy','careful',datetime('now'))")
            db.commit()
        print('ISOLATION_PASS: supplied data root is new Temp folder; all personal-data tables, configurations, MCP and custom prompts are empty.',flush=True)
        key = load_api_key(key_ref)
        assert key, 'Test credential unavailable'
        with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=60) as c:
            cfg = c.post('/ai/configs',json={'name':'Disposable frozen Responses acceptance',
                'provider_kind':'openai_responses','model':model,'base_url':base_url,'api_key':key})
            assert cfg.status_code == 201
            assert c.post(f"/ai/configs/{cfg.json()['id']}/enable").status_code == 200
        day = str(date.today()+timedelta(days=2))
        events = stream(port,'/ai/chat/stream',{'message':'请把后天上午9:00到9:20安排为一个叫“响应格式验收”的独立日程，地点书房。请核对本机当前日期和已有安排，换算出明确日期。'})
        all_events = list(events)
        assert any(e['type']=='tool_approval_requested' for e in events), 'Expected confirmation in careful mode'
        assert request(port,'/api/schedule/day?date='+day)['items'] == []
        for _ in range(4):
            approvals = [e for e in events if e['type']=='tool_approval_requested']
            if not approvals:
                break
            for approval in approvals:
                request(port,f"/ai/actions/{approval['action_id']}/approve",'POST')
            events = stream(port,f"/ai/conversations/{all_events[0]['conversation_id']}/resume/stream")
            all_events.extend(events)
        errors = [e for e in all_events if e['type']=='run_error']
        actual = request(port,'/api/schedule/day?date='+day)
        assert not errors, json.dumps(errors,ensure_ascii=False).replace(key,'[redacted]')
        assert len(actual['items']) == 1 and actual['items'][0]['title'] == '响应格式验收'
        assert actual['items'][0]['start_time'] == '09:00' and actual['items'][0]['end_time'] == '09:20'
        report = {'ok':True,'model':model,'protocol':'openai_responses','base_url':base_url,
                  'isolation_counts':counts,'expected_date':day,'actual':actual,'events':all_events}
        report_file.write_text(json.dumps(report,ensure_ascii=False,indent=2).replace(key,'[redacted]'),encoding='utf8')
        print('PACKAGED_RESPONSES_PASS: real model, machine date, relative date, calendar read, confirmation, resume, exactly one event.',flush=True)
    finally:
        try:
            stop(proc,log,port)
        finally:
            with sqlite3.connect(root/'v2/backend.db') as db:
                for (ref,) in db.execute('SELECT api_key_ref FROM ai_configs'):
                    if ref:
                        delete_api_key(ref)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('exe',type=Path)
    parser.add_argument('--key-ref',required=True)
    parser.add_argument('--base-url',required=True)
    parser.add_argument('--model',required=True)
    parser.add_argument('--report',type=Path,required=True)
    args = parser.parse_args()
    verify(args.exe.resolve(),args.key_ref,args.base_url,args.model,args.report)
