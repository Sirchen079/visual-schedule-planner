import json

import pytest
from fastapi.testclient import TestClient

from zhishi.adapters import model_catalog
from zhishi.infra import secrets
from zhishi.server.app import _ensure_schema, create_app


def test_edit_capabilities_retains_key_and_enabled_state(tmp_path, monkeypatch):
    vault = {}
    monkeypatch.setattr(secrets, 'store_api_key', lambda ref, value: vault.__setitem__(ref, value))
    monkeypatch.setattr(secrets, 'load_api_key', vault.get)
    monkeypatch.setattr(secrets, 'delete_api_key', lambda ref: vault.pop(ref, None))
    with TestClient(create_app(data_dir=tmp_path)) as client:
        body = {'name': '可配置模型', 'model': 'test', 'base_url': 'https://model.example/v1',
                'api_key': 'test-secret'}
        cid = client.post('/ai/configs', json=body).json()['id']
        client.post(f'/ai/configs/{cid}/enable')
        body.update(api_key='', context_window=128000, max_output_tokens=8192,
                    input_modalities=['text', 'image', 'audio'], reasoning_effort='high')
        saved = client.put(f'/ai/configs/{cid}', json=body)
        assert saved.status_code == 200, saved.text
        assert saved.json()['enabled'] and saved.json()['has_api_key']
        assert saved.json()['context_window'] == 128000
        assert saved.json()['reasoning_effort'] == 'high'
        assert saved.json()['input_modalities'] == ['text', 'image', 'audio']
        assert list(vault.values()) == ['test-secret']
        assert 'test-secret' not in saved.text
        received = []
        def discover(request):
            received.append(request.api_key.get_secret_value())
            return {'models': [{'id': 'test', 'name': 'test'}]}
        monkeypatch.setattr(model_catalog, 'discover_models', discover)
        catalog = {'config_id': cid, 'base_url': body['base_url']}
        assert client.post('/ai/configs/models', json=catalog).status_code == 200
        assert received == ['test-secret']
        catalog['base_url'] = 'https://different.example/v1'
        assert client.post('/ai/configs/models', json=catalog).status_code == 400
        assert len(received) == 1
        body['api_key'] = 'replacement-secret'
        assert client.put(f'/ai/configs/{cid}', json=body).status_code == 200
        assert list(vault.values()) == ['replacement-secret']
    with TestClient(create_app(data_dir=tmp_path)) as client:
        config = client.get('/ai/configs').json()[0]
        assert config['max_output_tokens'] == 8192
        assert config['reasoning_effort'] == 'high'
        cleared = client.put(f'/ai/configs/{cid}', json={**body, 'api_key': '', 'reasoning_effort': None})
        assert cleared.status_code == 200 and cleared.json()['reasoning_effort'] is None
        assert config['input_modalities'] == ['text', 'image', 'audio']


@pytest.mark.parametrize('patch', [
    {'context_window': True}, {'context_window': 100}, {'max_output_tokens': 0},
    {'context_window': 4096, 'max_output_tokens': 4096},
    {'input_modalities': ['image']}, {'input_modalities': ['imaginary']},
    {'reasoning_effort': 'ultra'}, {'reasoning_effort': True},
    {'provider_kind': 'anthropic', 'reasoning_effort': 'minimal'},
])
def test_invalid_capabilities_rejected_without_writes(tmp_path, patch):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        result = client.post('/ai/configs', json={'name': 'test', 'model': 'test', **patch})
        assert result.status_code == 422
        assert client.get('/ai/configs').json() == []


def test_migration_adds_conservative_capabilities_without_changing_config(db):
    engine = db.get_bind()
    with engine.begin() as conn:
        conn.exec_driver_sql('DROP TABLE ai_configs')
        conn.exec_driver_sql('CREATE TABLE ai_configs (id INTEGER PRIMARY KEY, name TEXT)')
        conn.exec_driver_sql("INSERT INTO ai_configs (id,name) VALUES (1,'existing')")
    _ensure_schema(engine)
    _ensure_schema(engine)
    with engine.connect() as conn:
        row = conn.exec_driver_sql('SELECT * FROM ai_configs').mappings().one()
        assert row['name'] == 'existing'
        assert row['context_window'] is None and row['max_output_tokens'] is None
        assert row['reasoning_effort'] is None
        assert json.loads(row['input_modalities_json']) == ['text']
