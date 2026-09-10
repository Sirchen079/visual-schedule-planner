import io
import json
import logging
import zipfile
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from zhishi.infra import diagnostics
from zhishi.server.app import create_app


def test_export_includes_general_failures_but_excludes_private_data(tmp_path):
    secret = 'sk-private-TEST-SECRET'
    with TestClient(create_app(data_dir=tmp_path)) as client:
        log = logging.getLogger('zhishi.test')
        try:
            raise RuntimeError(f'{secret} C:\\Users\\PrivateName\\secret.txt person@example.com 聊天正文')
        except RuntimeError:
            log.exception('Provider returned %s', secret)
        assert client.get('/tasks/not-a-number', params={'secret': secret}).status_code in (404, 422)
        payload = {'event': 'vue_error', 'error_type': 'TypeError', 'asset': 'index-abc.js', 'line': 3, 'column': 42}
        assert client.post('/api/diagnostics/frontend', json=payload).status_code == 204
        assert client.post('/api/diagnostics/frontend', json={**payload, 'message': secret}).status_code == 422
        assert client.post('/api/diagnostics/frontend', json={**payload, 'asset': 'C:\\Users\\PrivateName.js'}).status_code == 422
        response = client.get('/api/diagnostics/export')
        assert response.status_code == 200
        assert response.headers['content-type'] == 'application/zip'
        assert 'attachment;' in response.headers['content-disposition']
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        assert set(archive.namelist()) == {'manifest.json', 'diagnostics.jsonl', 'README.txt'}
        text = '\n'.join(archive.read(name).decode() for name in archive.namelist())
        for excluded in (secret, 'PrivateName', 'person@example.com', 'secret.txt', '聊天正文'):
            assert excluded not in archive.read('diagnostics.jsonl').decode()
        assert secret not in text
        rows = [json.loads(line) for line in archive.read('diagnostics.jsonl').splitlines()]
        assert any(row.get('error_type') == 'RuntimeError' and row.get('frames') for row in rows)
        assert any(row['kind'] == 'frontend' and row['column'] == 42 for row in rows)
        assert any(row['kind'] == 'http' and row['status_code'] in (404, 422) for row in rows)
        assert any(row['kind'] == 'startup' for row in rows)
        # Cross-origin reads must not disclose even this reduced bundle.
        assert client.get('/api/diagnostics/export', headers={'Origin': 'https://evil.example'}).status_code == 403


def test_snapshot_bounds_records_skips_partial_writes_and_unrecognized_fields(tmp_path):
    diagnostics.setup(tmp_path)
    path = tmp_path / 'diagnostics.jsonl'
    rows = [{'kind': 'http', 'time': '2026-09-10T00:00:00+00:00', 'status_code': 500,
             'message': 'NEVER-EXPORT', 'headers': {'Authorization': 'NEVER-EXPORT'}}] * 5010
    path.write_text('\n'.join(json.dumps(row) for row in rows) + '\n{"kind":', encoding='utf-8')
    result, skipped = diagnostics.snapshot(tmp_path)
    assert len(result) == 5000 and skipped == 1
    assert 'NEVER-EXPORT' not in json.dumps(result)
    assert diagnostics.export_record({'kind': []}) is None
    assert diagnostics.export_record({'kind': 'http', 'time': 'SECRET', 'model': 'SECRET'}) == {'kind': 'http'}


def test_export_merges_desktop_events_in_time_order_and_drops_unknown_content(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        logs = client.app.state.logs_dir
        desktop = {'kind': 'desktop', 'time': '2026-01-01T00:00:00.123Z',
                   'version': '2.20.0', 'event': 'renderer_gone', 'status_code': -1,
                   'private_details': 'PRIVATE-DESKTOP-DATA'}
        (logs / 'desktop-diagnostics.jsonl').write_text(json.dumps(desktop) + '\n', encoding='utf-8')
        result = client.get('/api/diagnostics/export')
        archive = zipfile.ZipFile(io.BytesIO(result.content))
        content = archive.read('diagnostics.jsonl').decode()
        rows = [json.loads(line) for line in content.splitlines()]
        assert rows[0]['kind'] == 'desktop' and rows[0]['event'] == 'renderer_gone'
        assert rows[0]['status_code'] == -1 and rows[0]['time'] == '2026-01-01T00:00:00.123000+00:00'
        assert 'PRIVATE-DESKTOP-DATA' not in content


async def test_request_diagnostics_report_prefix_changes_and_actual_usage_without_content(tmp_path):
    from zhishi.agent.diagnostics import request_diagnostic_hooks
    diagnostics.setup(tmp_path)
    cfg = SimpleNamespace(provider_kind='openai_compat', model='PRIVATE-MODEL')
    def model(messages, info):
        return ModelResponse(parts=[TextPart('PRIVATE-ANSWER')],
            usage=RequestUsage(input_tokens=1500, output_tokens=10, cache_read_tokens=1024, cache_write_tokens=128))
    first = await Agent(FunctionModel(model), instructions='PRIVATE-INSTRUCTIONS',
        capabilities=[request_diagnostic_hooks(cfg, 42, str(tmp_path))]).run('PRIVATE-QUESTION')
    agent = Agent(FunctionModel(model), instructions='PRIVATE-INSTRUCTIONS',
        capabilities=[request_diagnostic_hooks(cfg, 42, str(tmp_path))])
    await agent.run('PRIVATE-FOLLOWUP', message_history=first.all_messages())
    await agent.run('Different history')
    rows, _ = diagnostics.snapshot(tmp_path)
    requests = [row for row in rows if row['kind'] == 'ai_request']
    assert len(requests) == 3
    assert requests[1]['has_previous'] and not requests[1]['history_changed']
    assert not requests[1]['tools_changed'] and not requests[1]['instructions_changed']
    assert requests[2]['history_changed']
    responses = [row for row in rows if row['kind'] == 'ai_response']
    assert responses[-1]['cache_read_tokens'] == 1024 and responses[-1]['cache_write_tokens'] == 128
    assert 'PRIVATE-' not in json.dumps(rows)


@pytest.mark.parametrize('approved', [True, False])
def test_dispatched_tool_approval_preview_resume_and_single_execution(tmp_path, monkeypatch, approved):
    from pydantic_ai.models.function import DeltaToolCall

    from tests.server.test_ai_routes import parse_sse
    from zhishi.domain import settingsvc
    from zhishi.domain.models import AIConfig, AIToolExecution, Task
    async def stream(messages, info):
        if any(getattr(p, 'tool_call_id', None) == 'write' and p.part_kind == 'tool-return'
               for m in messages for p in m.parts):
            yield 'Finished'
        else:
            yield {0: DeltaToolCall(name='execute_tool', tool_call_id='write',
                json_args=json.dumps({'name': 'create_task', 'arguments': {'title': 'One task'}}))}
    import zhishi.server.routes.ai as ai_route
    monkeypatch.setattr(ai_route, 'build_model', lambda *a, **k: FunctionModel(stream_function=stream))
    with TestClient(create_app(data_dir=tmp_path)) as client:
        with client.app.state.session_factory() as db:
            db.add(AIConfig(name='test', model='test', provider_kind='openai_compat', enabled=True))
            settingsvc.set_setting(db, 'agent_autonomy', 'careful'); db.commit()
        events = parse_sse(client.post('/ai/chat/stream', json={'message': 'Create'}).text)
        approval = next(row for row in events if row['type'] == 'tool_approval_requested')
        assert approval['tool'] == 'create_task' and approval['args'] == {'title': 'One task'}
        started = next(row for row in events if row['type'] == 'run_started')
        assert next(row for row in events if row['type'] == 'tool_call_started')['tool'] == 'create_task'
        decision = 'approve' if approved else 'reject'
        assert client.post(f"/ai/actions/{approval['action_id']}/{decision}").status_code == 200
        result = client.post(f"/ai/conversations/{started['conversation_id']}/resume/stream",
                             json={'run_id': started['run_id']})
        assert result.status_code == 200, result.text
        assert not [row for row in parse_sse(result.text) if row['type'] == 'run_error']
        with client.app.state.session_factory() as db:
            assert db.query(Task).count() == int(approved)
            assert db.query(AIToolExecution).count() == int(approved)
