import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from zhishi.agent.attachments import VISION_SETTING_KEY, server_fingerprint
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
                    enabled=True, auto_approve_readonly=False,
                    headers_json='{"Authorization":"private-token"}')
    db.add(row)
    db.commit()
    return row


def body(server, **kwargs):
    return {'enabled': True, 'server_id': server.id, **kwargs}


def test_save_read_delete_nonsecret_binding(client, db, server):
    assert client.get('/ai/vision').json()['enabled'] is False
    response = client.put('/ai/vision', json=body(server))
    assert response.status_code == 200
    assert response.json() == {'enabled': True, 'server_id': server.id}
    assert client.get('/ai/vision').json() == response.json()
    stored = db.get(AppSetting, VISION_SETTING_KEY).value
    assert json.loads(stored)['server_fingerprint']
    assert 'private-token' not in stored
    assert 'server_fingerprint' not in response.json()
    assert client.delete('/ai/vision').json()['enabled'] is False
    assert client.get('/ai/vision').json()['enabled'] is False


def test_legacy_tool_binding_fields_are_rejected(client, db, server):
    """固定工具绑定已移除（模型运行时自选工具）；旧字段按未知字段拒绝。"""
    legacy = body(server, tool_name='describe',
                  arguments={'image': '{{image_data_url}}'})
    assert client.put('/ai/vision', json=legacy).status_code == 422
    assert db.get(AppSetting, VISION_SETTING_KEY) is None


def test_legacy_stored_setting_loads_after_key_strip(client, db, server):
    """存量设置带旧 tool_name/arguments 键：读取时剥离，不报「配置无效」。"""
    fingerprint = server_fingerprint(server)
    db.merge(AppSetting(key=VISION_SETTING_KEY, value=json.dumps({
        'enabled': True, 'server_id': server.id, 'tool_name': 'describe',
        'arguments': {'image': '{{image_data_url}}'},
        'server_fingerprint': fingerprint})))
    db.commit()
    assert client.get('/ai/vision').json() == {'enabled': True, 'server_id': server.id}


def test_schema_rejects_extra_credentials_and_missing_selection(client, server):
    assert client.put('/ai/vision', json=body(server, api_key='private')).status_code == 422
    assert client.put('/ai/vision', json={'enabled': True}).status_code == 422
    assert client.put('/ai/vision', json=body(server, enabled='true')).status_code == 422
    assert client.put('/ai/vision', json=body(server, server_id=9999)).status_code == 404


def test_stdio_requires_trust_to_enable(client, db, server):
    server.transport, server.command = 'stdio', 'unused-command'
    db.commit()
    assert client.put('/ai/vision', json=body(server)).status_code == 409
    server.trusted = True
    db.commit()
    assert client.put('/ai/vision', json=body(server)).status_code == 200


def test_enable_respects_server_enabled_flag(client, db, server):
    server.enabled = False
    db.commit()
    assert client.put('/ai/vision', json=body(server)).status_code == 409
    assert client.put('/ai/vision', json=body(server, enabled=False)).status_code == 200


def test_enable_works_without_readonly_auto_approval(client, db, server):
    assert server.auto_approve_readonly is False
    assert client.put('/ai/vision', json=body(server)).status_code == 200


def test_corrupt_setting_can_be_replaced_or_cleared(client, db, server):
    db.add(AppSetting(key=VISION_SETTING_KEY, value='not-json'))
    db.commit()
    assert client.get('/ai/vision').status_code == 409
    assert client.put('/ai/vision', json=body(server)).status_code == 200
    assert client.delete('/ai/vision').status_code == 200
