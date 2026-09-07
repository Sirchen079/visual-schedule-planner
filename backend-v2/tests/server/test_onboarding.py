from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from zhishi.domain.models import AppSetting, Task
from zhishi.domain.onboarding import STATE_KEY
from zhishi.infra.database import create_all, make_engine
from zhishi.server.app import create_app


def test_new_install_shows_once_and_completion_survives_restart(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.get('/api/settings/onboarding').json() == {
            'status': 'pending', 'has_history': False, 'show_automatically': True}
        assert client.post('/api/settings/onboarding', json={'outcome': 'completed'}).json()['status'] == 'completed'
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert not client.get('/api/settings/onboarding').json()['show_automatically']
        # Closing a manual replay must not erase a previous completion.
        assert client.post('/api/settings/onboarding', json={'outcome': 'skipped'}).json()['status'] == 'completed'


def test_skip_persists_without_creating_example_data(tmp_path):
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as client:
        response = client.post('/api/settings/onboarding', json={'outcome': 'skipped'})
        assert response.json() == {'status': 'skipped', 'has_history': False, 'show_automatically': False}
        with app.state.session_factory() as db:
            assert db.scalar(select(Task.id).limit(1)) is None
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.get('/api/settings/onboarding').json()['status'] == 'skipped'


def test_existing_empty_database_is_an_upgrade_not_a_new_install(tmp_path):
    engine = make_engine(tmp_path / 'v2/backend.db')
    create_all(engine)
    engine.dispose()
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.get('/api/settings/onboarding').json()['status'] == 'existing'


def test_history_including_trash_suppresses_automatic_guide(tmp_path):
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as client:
        with app.state.session_factory() as db:
            db.add(Task(title='Previous record', deleted_at=datetime(2026, 1, 1, tzinfo=UTC)))
            db.commit()
        result = client.get('/api/settings/onboarding').json()
        assert result['has_history'] and not result['show_automatically']
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.get('/api/settings/onboarding').json()['status'] == 'existing'


def test_invalid_outcomes_cannot_reset_first_run_state(tmp_path):
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as client:
        assert client.post('/api/settings/onboarding', json={'outcome': 'pending'}).status_code == 422
        with app.state.session_factory() as db:
            assert db.get(AppSetting, STATE_KEY).value == 'pending'
