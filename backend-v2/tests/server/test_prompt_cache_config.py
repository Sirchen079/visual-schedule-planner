import sqlite3

from fastapi.testclient import TestClient
from zhishi.server.app import create_app


def test_cache_options_roundtrip_validate_and_migrate_legacy_config(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        body = {'name': 'Example gateway', 'model': 'example', 'provider_kind': 'openai_compat',
                'prompt_cache_mode': 'anthropic_compat', 'prompt_cache_ttl': '1h', 'prompt_cache_key': True}
        result = client.post('/ai/configs', json=body)
        assert result.status_code == 201
        config_id = result.json()['id']
        row = client.get('/ai/configs').json()[0]
        assert all(row[key] == value for key, value in body.items())
        changed = {**body, 'prompt_cache_mode': 'disabled', 'prompt_cache_key': False}
        assert client.put(f'/ai/configs/{config_id}', json=changed).json()['prompt_cache_key'] is False
        for invalid in ({**body, 'provider_kind': 'anthropic'}, {**body, 'provider_kind': 'openai_responses'},
                        {**body, 'prompt_cache_ttl': '24h'}, {**body, 'prompt_cache_mode': 'invented'}):
            assert client.post('/ai/configs', json=invalid).status_code == 422
    # Simulate the previous schema without touching any real application data.
    with sqlite3.connect(tmp_path / 'v2' / 'backend.db') as db:
        for column in ('prompt_cache_mode', 'prompt_cache_ttl', 'prompt_cache_key'):
            db.execute(f'ALTER TABLE ai_configs DROP COLUMN {column}')
    for _ in range(2):
        with TestClient(create_app(data_dir=tmp_path)) as client:
            row = client.get('/ai/configs').json()[0]
            assert row['id'] == config_id and row['name'] == body['name']
            assert row['prompt_cache_mode'] == 'auto' and row['prompt_cache_ttl'] == '5m'
            assert row['prompt_cache_key'] is None
