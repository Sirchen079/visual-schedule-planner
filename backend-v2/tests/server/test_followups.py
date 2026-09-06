# ruff: noqa: DTZ005 -- API stores local wall time.
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from tests.server.test_research import SPEC
from zhishi.domain.models import NotificationLog, TaskScheduleEntry
from zhishi.server.app import create_app


def make_missed(c):
    p = c.post('/api/research/projects',json=SPEC).json()
    draft = c.post(f"/api/research/projects/{p['id']}/plans",json={'version':1,'rationale':'Read first',
        'steps':[{'title':'Read','outcome':'Write three findings','minutes':45}]}).json()
    assert c.post(f"/api/research/plans/{draft['id']}/apply").status_code == 200
    # Simulate time passing by relocating only this isolated test task's owned slot into yesterday.
    with c.app.state.session_factory() as db:
        slot = db.query(TaskScheduleEntry).one()
        slot.date = (datetime.now()-timedelta(days=1)).date()
        db.commit()
    return p


def test_followup_api_notification_target_snooze_and_refresh(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        assert 'secretary-followups' in c.app.state.scheduler._jobs
        p = make_missed(c)
        first = c.post('/api/followups/check',json={'project_id':p['id']})
        assert first.status_code == 200, first.text
        row = first.json()
        assert row['plan']['state'] == 'draft'
        notification = next(n for n in c.get('/api/notifications').json() if n['kind'] == 'followup')
        assert notification['target_path'] == row['target_path']
        snooze = c.post(f"/api/followups/{row['id']}/respond",json={'version':row['version'],
            'snooze_until':(datetime.now()+timedelta(hours=2)).isoformat()})
        assert snooze.status_code == 200
        assert c.post(f"/api/followups/{row['id']}/apply",json={'version':row['version']}).status_code == 409
        assert c.get('/api/followups?project_id='+str(p['id'])).json()[0]['status'] == 'snoozed'
        assert c.put('/api/followups/preferences',json={'enabled':False}).json()['enabled'] is False
    with TestClient(create_app(data_dir=tmp_path)) as c:
        assert c.get('/api/followups/status').json()['enabled'] is False
        assert c.get(f"/api/followups/{row['id']}").json()['status'] == 'snoozed'
        assert len(c.get('/api/tasks').json()) == 1
        assert c.get('/api/followups/99999').status_code == 404


def test_old_notification_table_migrates_without_losing_reminders(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        with c.app.state.session_factory() as db:
            db.add(NotificationLog(kind='reminder',title='Existing reminder',body='Keep this',remind_at=datetime.now()))
            db.commit()
        with c.app.state.engine.begin() as conn:
            conn.exec_driver_sql('ALTER TABLE notification_logs DROP COLUMN target_path')
    with TestClient(create_app(data_dir=tmp_path)) as c:
        notes = c.get('/api/notifications').json()
        original = next(n for n in notes if n['title'] == 'Existing reminder')
        assert original['body'] == 'Keep this' and original['target_path'] is None


def test_startup_worker_follows_persisted_projects_without_manual_check(tmp_path):
    import time
    with TestClient(create_app(data_dir=tmp_path)) as c:
        p = make_missed(c)
    with TestClient(create_app(data_dir=tmp_path)) as c:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            rows = c.get('/api/followups', params={'project_id':p['id']}).json()
            if rows and rows[0]['plan_id'] and c.get('/api/followups/status').json()['last_scan']:
                break
            time.sleep(0.02)
        assert rows[0]['status'] == 'pending' and rows[0]['plan_id']
        assert len(c.get('/api/tasks').json()) == 1
