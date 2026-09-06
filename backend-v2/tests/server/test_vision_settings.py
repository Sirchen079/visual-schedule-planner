import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from zhishi.agent.attachments import VISION_SETTING_KEY
from zhishi.domain.models import AppSetting, MCPServer
from zhishi.server.deps import get_db
from zhishi.server.routes.vision import router


@pytest.fixture
def client(db, monkeypatch):
    from zhishi.adapters import mcp_client

    def never_connect(*args, **kwargs):
        pytest.fail('Settings must not make MCP calls')

    monkeypatch.setattr(mcp_client, 'build_toolset', never_connect)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        yield client


@pytest.fixture
def server(db):
    row = MCPServer(name='vision', transport='http', url='http://unused.invalid/mcp',
                    enabled=True, auto_approve_readonly=True,
                    headers_json='{"Authorization":"private-token"}')
    db.add(row)
    db.commit()
    return row


def body(server, **kwargs):
    return {'enabled': True, 'server_id': server.id, 'tool_name': 'describe', **kwargs}


def test_save_read_delete_nonsecret_binding(client, db, server):
    assert client.get('/ai/vision').json()['enabled'] is False
    response = client.put('/ai/vision', json=body(server))
    assert response.status_code == 200
    assert response.json()['arguments']['image'] == '{{image_data_url}}'
    assert client.get('/ai/vision').json() == response.json()
    stored = db.get(AppSetting, VISION_SETTING_KEY).value
    assert json.loads(stored)['server_fingerprint']
    assert 'private-token' not in stored
    assert 'server_fingerprint' not in response.json()
    assert client.delete('/ai/vision').json()['enabled'] is False
    assert client.get('/ai/vision').json()['enabled'] is False


@pytest.mark.parametrize('arguments', [
    {'image': '{{unknown}}'}, {'image': '{{image_data_url}'}, {'image': '{{prompt}}'},
    {'image': '{{image_data_url}}', 'api_key': 'private'},
    {'image': '{{image_data_url}}', 'nested': {'Authorization': 'private'}},
    {'image': '{{image_data_url}}', 'x': 'x' * 17000},
])
def test_invalid_template_rejected_without_write(client, db, server, arguments):
    assert client.put('/ai/vision', json=body(server, arguments=arguments)).status_code == 422
    assert db.get(AppSetting, VISION_SETTING_KEY) is None


def test_schema_rejects_extra_credentials_and_missing_selection(client, server):
    assert client.put('/ai/vision', json=body(server, api_key='private')).status_code == 422
    assert client.put('/ai/vision', json={'enabled': True}).status_code == 422
    assert client.put('/ai/vision', json=body(server, enabled='true')).status_code == 422
    assert client.put('/ai/vision', json=body(server, server_id=9999)).status_code == 404


def test_path_http_disallowed_and_stdio_requires_trust(client, db, server):
    payload = body(server, arguments={'path': '{{image_path}}'})
    assert client.put('/ai/vision', json=payload).status_code == 422
    server.transport, server.command = 'stdio', 'unused-command'
    db.commit()
    assert client.put('/ai/vision', json=payload).status_code == 422
    server.trusted = True
    db.commit()
    assert client.put('/ai/vision', json=payload).status_code == 200


@pytest.mark.parametrize('attribute', ['enabled', 'auto_approve_readonly'])
def test_enable_respects_server_flags(client, db, server, attribute):
    setattr(server, attribute, False)
    db.commit()
    assert client.put('/ai/vision', json=body(server)).status_code == 409
    assert client.put('/ai/vision', json=body(server, enabled=False)).status_code == 200


def test_corrupt_setting_can_be_replaced_or_cleared(client, db, server):
    db.add(AppSetting(key=VISION_SETTING_KEY, value='not-json'))
    db.commit()
    assert client.get('/ai/vision').status_code == 409
    assert client.put('/ai/vision', json=body(server)).status_code == 200
    assert client.delete('/ai/vision').status_code == 200
