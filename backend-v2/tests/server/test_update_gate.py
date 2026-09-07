from fastapi.testclient import TestClient
from pydantic_ai.models.function import FunctionModel
from tests.server.test_attachments import _parse_sse, _seed_enabled_config
from zhishi.server.app import create_app
from zhishi.server.routes import ai


def test_update_gate_blocks_new_runs_but_allows_draft_flush_and_cancellation(tmp_path, monkeypatch):
    async def stream(messages, info): yield 'ok'
    monkeypatch.setattr(ai, 'build_model', lambda *a, **k: FunctionModel(stream_function=stream))
    with TestClient(create_app(data_dir=tmp_path)) as c:
        _seed_enabled_config(c)
        c.app.state.active_runs[99] = 'busy'
        assert c.post('/ai/runtime/update-prepare').status_code == 409
        c.app.state.active_runs.clear()
        assert c.post('/ai/runtime/update-prepare').status_code == 200
        assert c.post('/ai/chat/stream', json={'message': '不应开始'}).status_code == 409
        assert c.post('/ai/conversations/1/resume/stream').status_code == 409
        assert c.put('/ai/workspaces/main', json={'revision': 0, 'state': {'drafts': {'new': {'text': '保存原草稿', 'attachments': []}}}}).status_code == 200
        assert c.post('/ai/runtime/update-cancel').status_code == 200
        events = _parse_sse(c.post('/ai/chat/stream', json={'message': '可以开始'}).text)
        assert events[0]['type'] == 'run_started' and not any(e['type'] == 'run_error' for e in events)
