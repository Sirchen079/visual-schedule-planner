# ruff: noqa: DTZ001 -- v2 persists local wall times; these fixtures exercise that contract.
import json
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from zhishi.domain.models import InboxItem
from zhishi.domain.notifications import record_due_reminders
from zhishi.server.app import create_app


def test_candidate_with_reminder_applies_once_and_produces_calendar_notification(tmp_path):
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as client:
        body = {'capture_key': 'meeting-text', 'items': [{'item_key': 'meeting-1',
            'source_excerpt': '9月6日15点在三楼开会，提前半小时提醒我。',
            'proposal': {'kind': 'event', 'data': {'title': '会议', 'date': '2026-09-06',
                'start_time': '15:00', 'end_time': '16:00', 'location': '三楼', 'remind_offsets': [30]}}}]}
        captured = client.post('/api/inbox', json=body)
        assert captured.status_code == 201, captured.text
        item = captured.json()[0]
        applied = client.post(f"/api/inbox/{item['id']}/apply", json={'version': item['version']})
        assert applied.status_code == 200, applied.text
        assert client.post(f"/api/inbox/{item['id']}/apply", json={'version': item['version']}).json() == applied.json()
        eid = applied.json()['target_id']
        assert client.get(f'/api/schedule/events/{eid}').json()['remind_offsets'] == [30]
        with app.state.session_factory() as db:
            record_due_reminders(db, datetime(2026, 9, 6, 14, 30))
        notifications = client.get('/api/notifications').json()
        assert len(notifications) == 1
        assert notifications[0]['target_path'] == f'/calendar?date=2026-09-06&event={eid}'
        assert client.get('/api/tasks').json() == []


def test_reminder_patch_validation_clear_and_restart(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        created = client.post('/api/schedule/events', json={'title': '全天活动', 'date': '2026-09-06'})
        eid = created.json()['id']
        assert client.patch(f'/api/schedule/events/{eid}', json={'remind_offsets': [0]}).status_code == 422
        saved = client.patch(f'/api/schedule/events/{eid}', json={'remind_offsets': [0], 'reminder_time': '09:00'})
        assert saved.status_code == 200
        assert client.patch(f'/api/schedule/events/{eid}', json={'reminder_time': None}).status_code == 422
        assert client.get(f'/api/schedule/events/{eid}').json()['reminder_time'] == '09:00'
        cleared = client.patch(f'/api/schedule/events/{eid}', json={'remind_offsets': [], 'reminder_time': None})
        assert cleared.status_code == 200 and cleared.json()['reminder_time'] is None
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.get(f'/api/schedule/events/{eid}').json()['remind_offsets'] == []


def test_legacy_candidate_defaults_do_not_create_false_conflicts(tmp_path):
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as client:
        body = {'capture_key': 'legacy', 'items': [{'item_key': 'one', 'source_excerpt': '9月6日会议',
            'proposal': {'kind': 'event', 'data': {'title': '会议', 'date': '2026-09-06'}}}]}
        first = client.post('/api/inbox', json=body).json()[0]
        with app.state.session_factory() as db:
            row = db.scalar(select(InboxItem).where(InboxItem.id == first['id']))
            old = json.loads(row.payload_json)
            old['data'].pop('remind_offsets'); old['data'].pop('reminder_time')
            row.payload_json = json.dumps(old)
            db.commit()
        second = client.post('/api/inbox', json=body)
        assert second.status_code == 201 and second.json()[0]['id'] == first['id']
