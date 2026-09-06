"""Mount only the owned router so tests need no application registration changes."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from zhishi.adapters import web_services as ws
from zhishi.domain.models import AppSetting
from zhishi.server.deps import get_db
from zhishi.server.routes.web_services import router


@pytest.fixture
def client(db, monkeypatch):
    vault = {}
    monkeypatch.setattr(ws.secrets, "store_api_key", lambda name, value: vault.update({name: value}))
    monkeypatch.setattr(ws.secrets, "load_api_key", vault.get)
    monkeypatch.setattr(ws.secrets, "delete_api_key", lambda name: vault.pop(name, None))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        yield client


def test_config_and_secret_lifecycle(client, db):
    root = "/ai/web-services"
    data = client.get(root).json()
    assert data["config"]["search_provider"] == data["config"]["fetch_provider"] == "builtin"
    assert data["tavily_has_api_key"] is False
    response = client.put(root + "/credentials/tavily", json={"api_key": "tvly-hidden"})
    assert response.status_code == 200
    assert response.json() == {"tavily_has_api_key": True}
    response = client.put(root, json={"search_provider": "tavily", "fetch_provider": "builtin"})
    assert response.status_code == 200
    assert response.json()["tavily_has_api_key"] is True
    assert response.json()["config"]["search_provider"] == "tavily"
    assert "tvly-hidden" not in response.text + client.get(root).text
    assert "tvly-hidden" not in json.dumps([row.value for row in db.query(AppSetting)])
    assert client.delete(root + "/credentials/tavily").json() == {"tavily_has_api_key": False}
    assert client.get(root).json()["tavily_has_api_key"] is False


def test_invalid_config_does_not_change_saved_state(client):
    root = "/ai/web-services"
    assert client.put(root, json={"search_provider": "tavily"}).status_code == 200
    for body in ({"api_key": "x"}, {"search_provider": "unknown"}, {"search_provider": "mcp"}):
        assert client.put(root, json=body).status_code == 422
    assert client.put(root, json={"search_provider": "mcp", "mcp_search": {
        "server_id": 999, "tool_name": "search"}}).status_code == 400
    assert client.get(root).json()["config"]["search_provider"] == "tavily"


def test_explicit_requests_forward_provider_without_changing_defaults(client, db, monkeypatch):
    calls = []

    def search(db_arg, query, limit, provider):
        calls.append((db_arg, query, limit, provider))
        return [{"title": "Guide", "url": "https://example.com", "description": "Summary"}]

    monkeypatch.setattr(ws, "search", search)
    response = client.post("/ai/web-services/search", json={"query": "q", "provider": "tavily"})
    assert response.status_code == 200
    assert calls == [(db, "q", 5, "tavily")]
    assert client.get("/ai/web-services").json()["config"]["search_provider"] == "builtin"
    assert client.post("/ai/web-services/search", json={"query": "q", "max_results": 100}).status_code == 422
    assert client.post("/ai/web-services/search", json={"query": "q", "server_id": 1}).status_code == 422
    assert client.post("/ai/web-services/fetch", json={"url": "http://127.0.0.1"}).json()["ok"] is False


def test_keyring_failure_does_not_echo_credential(client, monkeypatch):
    def fail(*args):
        raise RuntimeError("private-key")

    monkeypatch.setattr(ws.secrets, "store_api_key", fail)
    response = client.put("/ai/web-services/credentials/tavily", json={"api_key": "private-key"})
    assert response.status_code == 400
    assert "private-key" not in response.text
