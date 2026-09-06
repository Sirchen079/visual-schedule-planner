"""Frozen 2.12 upgrade, native bill management, real scheduler and replay/restart verification."""
import argparse
import json
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from verify_ledger import request, start, stop


def verify(exe, old_exe, electron, qa):
    qa.mkdir(parents=True,exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='zhishi-bills-'))
    report = {'root':str(root),'passed':False,'checks':[]}
    proc = log = port = None
    try:
        proc,log,port = start(old_exe,root,'old-2.12')
        original = request(port,'/api/ledger','POST',{'day':'2026-01-31','direction':'expense',
            'amount':'12.50','category':'订阅','notes':'升级前已记账','idempotency_key':'legacy-cloud'},201)
        stop(proc,log,port); proc=log=port=None
        with sqlite3.connect(root/'v2/backend.db') as db:
            assert not db.execute("SELECT name FROM sqlite_master WHERE name='bills'").fetchall()
        proc,log,port = start(exe,root,'upgrade')
        assert request(port,'/api/bills')['total'] == 0
        assert request(port,f"/api/ledger/{original['id']}") == original
        fixture = request(port,'/api/bills','POST',{'title':'到期提醒验收','first_due':'2026-01-01',
            'cycle':'once','amount':None,'request_key':'reminder-fixture'},201)
        report['checks'].append('2.12 upgrade creates empty bill tables and preserves original ledger exactly')
        (qa/'bill-ui-state.json').write_text(json.dumps({'port':port,'entry_id':original['id'],
            'reminder_bill_id':fixture['id']}),encoding='utf-8')
        env = dict(os.environ); env.pop('ELECTRON_RUN_AS_NODE',None)
        done = subprocess.run([str(electron),str(Path(__file__).with_name('verify_bill_ui.cjs')),str(qa)],
            env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180,
            creationflags=subprocess.CREATE_NO_WINDOW,check=False)
        (qa/'bill-ui.log').write_text(done.stdout+'\n'+done.stderr,encoding='utf-8')
        assert done.returncode == 0, done.stdout[-1000:]+done.stderr[-1500:]
        ui = json.loads((qa/'bill-ui-result.json').read_text(encoding='utf-8'))
        rent = request(port,f"/api/bills/{ui['rent_id']}")
        assert rent['pending']['due'] == '2026-03-31' and not rent['details']['enabled']
        assert rent['pending']['details']['amount'] == '2100'
        periods = request(port,f"/api/bills/{rent['id']}/history")['items']
        assert [p['status'] for p in periods] == ['pending','skipped','paid']
        assert periods[-1]['details']['amount'] == '2000'
        assert periods[-1]['ledger_entry']['amount'] == '1999.95'
        assert request(port,'/api/ledger')['total'] == 2
        assert request(port,f"/api/ledger/{original['id']}") == original
        replay = {'version':1,'day':'2026-01-31','amount':'1999.950','account':'默认账户',
            'existing_entry_id':None,'source_file_id':None,'source_excerpt':''}
        assert request(port,f"/api/bills/occurrences/{periods[-1]['id']}/pay",'POST',replay)['ledger_entry']['id'] == periods[-1]['ledger_entry']['id']
        report['checks'].append('native add/month-end/payment/skip/pause/edit/history; existing ledger link creates no duplicate')
        logs = request(port,'/api/notifications')
        notifications = [n for n in logs if n['target_path'] == f"/ledger?bill={fixture['id']}"]
        assert len(notifications) == 1 and notifications[0]['read_at'] is not None
        report['checks'].append('actual frozen scheduler sends one overdue catchup; native bell opens exact bill')
        # Pause the fixture via its real API; recurring rent is already paused in native UI.
        fixture = request(port,f"/api/bills/{fixture['id']}")
        request(port,f"/api/bills/{fixture['id']}",'PUT',
            {**fixture['details'],'enabled':False,'version':fixture['version']})
        stop(proc,log,port); proc=log=port=None
        proc,log,port = start(exe,root,'restart')
        assert request(port,f"/api/bills/{rent['id']}") == rent
        assert request(port,f"/api/bills/{rent['id']}/history")['items'] == periods
        assert request(port,'/api/ledger')['total'] == 2
        assert request(port,f"/api/ledger/{original['id']}") == original
        assert len([n for n in request(port,'/api/notifications')
            if n['target_path'] == f"/ledger?bill={fixture['id']}"]) == 1
        report['checks'].append('restart retains payment, month-end anchor, original ledger and pause without repeated notifications')
        report['bills'] = request(port,'/api/bills')
        report['rent_history'] = periods
        report['notifications'] = notifications
        report['passed'] = True
    finally:
        if proc is not None:
            stop(proc,log,port)
        report['owned_processes_stopped'] = True
        (qa/'bills.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('BILLS_FROZEN_UPGRADE_NATIVE_SCHEDULER_RESTART_PASS',flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('exe',type=Path)
    parser.add_argument('--old-exe',type=Path,required=True)
    parser.add_argument('--electron',type=Path,required=True)
    parser.add_argument('--qa',type=Path,required=True)
    args = parser.parse_args()
    verify(args.exe.resolve(),args.old_exe.resolve(),args.electron.resolve(),args.qa.resolve())
