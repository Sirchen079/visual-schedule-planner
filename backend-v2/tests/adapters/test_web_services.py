"""Provider dispatch, credential boundaries and MCP authorization use mocked I/O."""
import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from zhishi.adapters import web_services as ws
from zhishi.domain import settingsvc
from zhishi.domain.models import AppSetting, MCPServer


@pytest.fixture
def vault(monkeypatch):
    values = {}
    monkeypatch.setattr(ws.secrets, "store_api_key", lambda name, value: values.update({name: value}))
    monkeypatch.setattr(ws.secrets, "load_api_key", values.get)
    monkeypatch.setattr(ws.secrets, "delete_api_key", lambda name: values.pop(name, None))
    return values


@pytest.fixture
def public_dns(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("8.8.8.8", 0))])


@pytest.fixture
def mcp(db, monkeypatch):
    row = MCPServer(name="web", url="https://mcp.example/mcp", transport="http", enabled=True,
                    auto_approve_readonly=True, headers_json='{"Authorization":"Bearer secret99"}')
    db.add(row)
    db.commit()
    state = SimpleNamespace(row=row, calls=[], connections=[], read_only=True,
        name="search", schema={"type": "object", "properties": {
            "q": {"type": "string"}, "count": {"type": "integer"}}, "required": ["q"]},
        result={"data": {"hits": [{"heading": "Guide", "link": "https://example.com/a",
                                  "summary": "Useful guide"}]}})

    class Toolset:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def list_tools(self):
            return [SimpleNamespace(name=state.name, description="", input_schema=state.schema,
                                    annotations=SimpleNamespace(read_only_hint=state.read_only))]

        async def direct_call_tool(self, name, args):
            state.calls.append((name, args))
            return state.result

    def build(row, timeout):
        state.connections.append((row.url, row.headers_json))
        return Toolset()

    monkeypatch.setattr(ws.mcp_client, "build_toolset", build)
    state.binding = ws.MCPSearchBinding(server_id=row.id, tool_name="search", query_argument="q",
        limit_argument="count", results_path="data.hits", title_field="heading",
        url_field="link", description_field="summary")
    return state


def test_defaults_and_bounded_builtin(db, monkeypatch):
    calls = []

    def search(query, limit):
        calls.append((query, limit))
        return [{"title": "t" * 400, "url": f"https://example.com/{i}",
                 "description": "d" * 3000} for i in range(20)]

    monkeypatch.setattr(ws.web, "search", search)
    assert ws.get_config(db) == ws.WebServicesConfig()
    hits = ws.search(db, " topic ", 999)
    assert calls == [("topic", 10)]
    assert len(hits) == 10
    assert len(hits[0]["title"]) == 300
    assert len(hits[0]["description"]) == 1000
    assert "error" in ws.search(db, " ")[0]
    assert "error" in ws.search(db, "q" * 501)[0]
    assert "error" in ws.search(db, "q", True)[0]
    assert len(calls) == 1


def test_credentials_rotate_without_plaintext_settings(db, vault):
    ws.save_tavily_key(db, "tvly-first-secret")
    first_ref = settingsvc.get_setting(db, ws.KEY_REF_SETTING)
    ws.save_config(db, ws.WebServicesConfig(search_provider="tavily"))
    assert ws.has_tavily_key(db)
    ws.save_tavily_key(db, "tvly-second-secret")
    assert first_ref not in vault
    assert list(vault.values()) == ["tvly-second-secret"]
    assert "tvly-" not in " ".join(row.value for row in db.query(AppSetting).all())
    ws.delete_tavily_key(db)
    assert not ws.has_tavily_key(db)
    assert not vault


def test_keyring_write_failure_preserves_old_reference(db, vault, monkeypatch):
    ws.save_tavily_key(db, "old-key")
    old_ref = settingsvc.get_setting(db, ws.KEY_REF_SETTING)

    def fail(*args):
        raise RuntimeError("new-private-key leaked by backend")

    monkeypatch.setattr(ws.secrets, "store_api_key", fail)
    with pytest.raises(ws.WebServiceError) as exc:
        ws.save_tavily_key(db, "new-private-key")
    assert "private" not in str(exc.value)
    assert settingsvc.get_setting(db, ws.KEY_REF_SETTING) == old_ref
    assert vault == {old_ref: "old-key"}


def test_tavily_official_payloads_and_independent_override(db, vault, public_dns, monkeypatch):
    ws.save_tavily_key(db, "tvly-SECRET")
    ws.save_config(db, ws.WebServicesConfig(search_provider="tavily", tavily_search_depth="advanced"))
    requests = []

    def handler(req):
        body = json.loads(req.content)
        requests.append((str(req.url), body))
        assert req.headers["authorization"] == "Bearer tvly-SECRET"
        assert "api_key" not in body
        if req.url.path == "/search":
            return httpx.Response(200, json={"results": [
                {"title": "Guide", "url": "https://example.com", "content": "tvly-SECRET details"}]})
        return httpx.Response(200, json={"results": [
            {"url": body["urls"][0], "raw_content": "tvly-SECRET " + "x" * 9000}]})

    monkeypatch.setattr(ws.web, "fetch", lambda url: "builtin content")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        hits = ws.search(db, "query", client=client)
        assert hits[0]["description"] == "*** details"
        assert ws.fetch(db, "https://example.com") == "builtin content"
        content = ws.fetch(db, "https://example.com", provider="tavily", client=client)
    assert len(content) == 8000 and "SECRET" not in content
    assert requests == [
        ("https://api.tavily.com/search", {"query": "query", "max_results": 5,
         "search_depth": "advanced", "topic": "general", "auto_parameters": False,
         "include_answer": False, "include_raw_content": False, "include_images": False}),
        ("https://api.tavily.com/extract", {"urls": ["https://example.com"],
         "extract_depth": "basic", "format": "text", "include_images": False})]
    assert ws.get_config(db).fetch_provider == "builtin"


@pytest.mark.parametrize("response", [
    httpx.Response(401, text="tvly-SECRET"),
    httpx.Response(302, headers={"Location": "https://evil.example/"}),
    httpx.Response(200, text="tvly-SECRET invalid json"),
    httpx.Response(200, content=b"x" * (ws.MAX_RESPONSE_BYTES + 1)),
])
def test_tavily_failures_redacted_no_redirect_or_fallback(db, vault, monkeypatch, response):
    ws.save_tavily_key(db, "tvly-SECRET")
    calls = []
    monkeypatch.setattr(ws.web, "search", lambda *a, **k: pytest.fail("unexpected fallback"))

    def handler(req):
        calls.append(str(req.url))
        return response

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = ws.search(db, "q", provider="tavily", client=client)
    assert len(calls) == 1
    assert "error" in result[0] and "SECRET" not in json.dumps(result)


def test_missing_key_and_corrupt_settings_fail_closed(db, vault, monkeypatch):
    monkeypatch.setattr(ws.web, "search", lambda *a, **k: pytest.fail("unexpected fallback"))
    assert "API key" in ws.search(db, "q", provider="tavily")[0]["error"]
    settingsvc.set_setting(db, ws.CONFIG_KEY, '{"search_provider":"other"}')
    assert "配置无效" in ws.search(db, "q")[0]["error"]


@pytest.mark.parametrize("provider", ["builtin", "tavily", "mcp"])
@pytest.mark.parametrize("url", ["http://127.0.0.1/x", "http://[::1]/", "file:///secret",
                                  "https://user:password@example.com", "http://10.0.0.1"])
def test_all_readers_reject_private_or_credential_urls_before_io(db, monkeypatch, provider, url):
    monkeypatch.setattr(ws, "_tavily", lambda *a, **k: pytest.fail("unexpected request"))
    monkeypatch.setattr(ws, "_mcp", lambda *a, **k: pytest.fail("unexpected MCP call"))
    monkeypatch.setattr(ws.web, "fetch", lambda *a, **k: pytest.fail("unexpected request"))
    with pytest.raises(ws.WebServiceError):
        ws.fetch(db, url, provider=provider)


def test_mcp_saved_mapping_and_full_json_before_bounding(db, mcp):
    ws.save_config(db, ws.WebServicesConfig(search_provider="mcp", mcp_search=mcp.binding))
    assert not mcp.calls  # readiness lists tools; never executes one on save
    mcp.result["data"]["hits"][0]["summary"] = "x" * 12000
    result = ws.search(db, "topic", 2)
    assert mcp.calls == [("search", {"q": "topic", "count": 2})]
    assert result == [{"title": "Guide", "url": "https://example.com/a", "description": "x" * 1000}]


@pytest.mark.parametrize("change", ["untrusted_stdio", "disabled", "no_auto_approval", "deleted"])
def test_mcp_revocation_blocks_before_connection(db, mcp, change):
    ws.save_config(db, ws.WebServicesConfig(search_provider="mcp", mcp_search=mcp.binding))
    mcp.connections.clear()
    if change == "untrusted_stdio":
        mcp.row.transport, mcp.row.command, mcp.row.trusted = "stdio", "do-not-launch", False
    elif change == "disabled":
        mcp.row.enabled = False
    elif change == "no_auto_approval":
        mcp.row.auto_approve_readonly = False
    else:
        db.delete(mcp.row)
    db.commit()
    assert "error" in ws.search(db, "q")[0]
    assert not mcp.connections and not mcp.calls


@pytest.mark.parametrize("change", ["not_readonly", "missing", "required", "wrong_type"])
def test_mcp_readiness_rejects_tools_without_overwriting_settings(db, mcp, change):
    ws.save_config(db, ws.WebServicesConfig(search_provider="tavily"))
    if change == "not_readonly":
        mcp.read_only = False
    elif change == "missing":
        mcp.name = "different-tool"
    elif change == "required":
        mcp.schema["required"].append("command")
    else:
        mcp.schema["properties"]["q"] = {"type": "object"}
    with pytest.raises(ws.WebServiceError):
        ws.save_config(db, ws.WebServicesConfig(search_provider="mcp", mcp_search=mcp.binding))
    assert not mcp.calls
    assert ws.get_config(db).search_provider == "tavily"


def test_mcp_live_readonly_and_reconnection_are_rechecked(db, mcp):
    ws.save_config(db, ws.WebServicesConfig(search_provider="mcp", mcp_search=mcp.binding))
    assert "error" not in ws.search(db, "q")[0]
    mcp.calls.clear()
    mcp.read_only = False
    assert "error" in ws.search(db, "q")[0]
    assert not mcp.calls
    connections = len(mcp.connections)
    mcp.row.url = "https://changed.example/mcp"
    mcp.row.headers_json = '{"X-Key":"new-credential"}'
    db.commit()
    assert "重新保存" in ws.search(db, "q")[0]["error"]
    assert not mcp.calls
    assert len(mcp.connections) == connections
    mcp.read_only = True
    ws.save_config(db, ws.get_config(db))
    assert "error" not in ws.search(db, "q")[0]
    assert mcp.connections[-1] == (mcp.row.url, mcp.row.headers_json)


def test_switch_to_builtin_retains_broken_inactive_mcp_binding(db, mcp):
    config = ws.WebServicesConfig(search_provider="mcp", mcp_search=mcp.binding)
    ws.save_config(db, config)
    mcp.row.enabled = False
    db.commit()
    mcp.connections.clear()
    config.search_provider = "builtin"
    ws.save_config(db, config)
    assert ws.get_config(db).mcp_search == mcp.binding
    assert ws.get_config(db).search_provider == "builtin"
    assert not mcp.connections


@pytest.mark.parametrize("field,value", [
    ("headers_json", '{"X-Key":"changed"}'), ("env_json", '{"TOKEN":"changed"}'),
    ("command", "new-program"), ("args_json", '["new-argument"]'),
])
def test_mcp_identity_changes_require_resave_before_io(db, mcp, field, value):
    ws.save_config(db, ws.WebServicesConfig(search_provider="mcp", mcp_search=mcp.binding))
    setattr(mcp.row, field, value)
    db.commit()
    mcp.connections.clear()
    assert "重新保存" in ws.search(db, "q")[0]["error"]
    assert not mcp.connections and not mcp.calls


def test_mcp_fetch_list_mapping_and_output_redaction(db, mcp, public_dns):
    mcp.name = "extract"
    mcp.schema = {"type": "object", "properties": {
        "urls": {"type": "array", "items": {"type": "string"}}}, "required": ["urls"]}
    mcp.result = json.dumps({"results": [{"raw_content": "Bearer secret99 body secret99"}]})
    binding = ws.MCPFetchBinding(server_id=mcp.row.id, tool_name="extract", url_argument="urls",
                                 url_as_list=True, content_path="results.0.raw_content")
    ws.save_config(db, ws.WebServicesConfig(fetch_provider="mcp", mcp_fetch=binding))
    assert ws.fetch(db, "https://example.com/a") == "*** body ***"
    assert mcp.calls == [("extract", {"urls": ["https://example.com/a"]})]


@pytest.mark.parametrize("payload", [
    {"search_provider": "mcp"}, {"api_key": "secret"},
    {"mcp_search": {"server_id": 1, "tool_name": "search", "args": {"command": "exec"}}},
    {"mcp_search": {"server_id": 1, "tool_name": "search", "query_argument": "query",
                    "limit_argument": "query"}},
    {"mcp_fetch": {"server_id": 1, "tool_name": "read", "content_path": "${eval(code)}"}},
])
def test_config_rejects_secrets_arbitrary_args_and_templates(payload):
    with pytest.raises(ValidationError):
        ws.WebServicesConfig.model_validate(payload)


def test_mcp_reused_id_requires_resave(db, mcp):
    from datetime import timedelta

    ws.save_config(db, ws.WebServicesConfig(search_provider="mcp", mcp_search=mcp.binding))
    original_id, original_created = mcp.row.id, mcp.row.created_at
    db.delete(mcp.row)
    db.commit()
    replacement = MCPServer(id=original_id, name="web", url="https://mcp.example/mcp",
        transport="http", enabled=True, auto_approve_readonly=True,
        headers_json='{"Authorization":"Bearer secret99"}',
        created_at=original_created + timedelta(seconds=1))
    db.add(replacement)
    db.commit()
    mcp.connections.clear()
    assert "重新保存" in ws.search(db, "q")[0]["error"]
    assert not mcp.connections and not mcp.calls


def test_mcp_general_grant_does_not_authorize_nonreadonly_tool(db, mcp):
    from zhishi.domain.models import AIToolGrant

    ws.save_config(db, ws.WebServicesConfig(search_provider="mcp", mcp_search=mcp.binding))
    db.add(AIToolGrant(tool_name=f"mcp__{mcp.row.id}__search", arg_pattern=""))
    db.commit()
    mcp.read_only = False
    assert "只读" in ws.search(db, "q")[0]["error"]
    assert not mcp.calls


def test_mcp_remote_exception_and_oversized_result_are_safe(db, mcp, monkeypatch):
    ws.save_config(db, ws.WebServicesConfig(search_provider="mcp", mcp_search=mcp.binding))
    mcp.result = "secret99" * ws.MAX_RESPONSE_BYTES
    assert "超过2MB" in ws.search(db, "q")[0]["error"]

    def fail(*args):
        raise RuntimeError("secret99")

    monkeypatch.setattr(ws.mcp_client, "build_toolset", fail)
    result = ws.search(db, "q")
    assert "error" in result[0] and "secret99" not in json.dumps(result)


def test_tavily_partial_and_malformed_extract_are_failures(db, vault, public_dns):
    ws.save_tavily_key(db, "hidden")
    for response in ({"results": [], "failed_results": [{"error": "hidden"}]},
                     {"results": [{"url": "https://different.example", "raw_content": "body"}]},
                     {"results": [{"url": "https://example.com", "raw_content": {"bad": "hidden"}}]}):
        transport = httpx.MockTransport(lambda req, body=response: httpx.Response(200, json=body))
        with httpx.Client(transport=transport) as c, pytest.raises(ws.WebServiceError) as exc:
            ws.fetch(db, "https://example.com", provider="tavily", client=c)
        assert "hidden" not in str(exc.value)


def test_public_tools_use_db_and_readonly_research_contract(db, monkeypatch, public_dns):
    from zhishi.agent.permissions import classify
    from zhishi.agent.tools import web_tools
    from zhishi.agent.tools.macro import subagent_specs
    from zhishi.agent.tools.registry import readonly_names

    observed = []

    def search(db_arg, query, limit, provider):
        observed.append((db_arg, query, limit, provider))
        return [{"title": "t", "url": "https://example.com", "description": "d"}]

    monkeypatch.setattr(ws, "search", search)
    monkeypatch.setattr(ws.web, "fetch", lambda url: "body")
    assert json.loads(web_tools.web_search(db, "topic", provider="tavily"))[0]["title"] == "t"
    assert observed == [(db, "topic", 5, "tavily")]
    assert json.loads(web_tools.web_fetch(db, "https://example.com"))["content"] == "body"
    assert json.loads(web_tools.web_fetch(db, "http://127.0.0.1"))["ok"] is False
    assert {"web_search", "web_fetch"} <= readonly_names()
    assert {"web_search", "web_fetch"} <= {spec.name for spec in subagent_specs(db)}
    settingsvc.set_setting(db, "agent_autonomy", "careful")
    assert classify(db, "web_search", {"query": "topic"}) == "allow"
