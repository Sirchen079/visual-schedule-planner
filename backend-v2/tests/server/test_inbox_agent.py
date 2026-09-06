import json

from fastapi.testclient import TestClient
from pydantic_ai.messages import RetryPromptPart, ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from tests.server.test_attachments import _parse_sse, _seed_enabled_config
from zhishi.server.app import create_app
from zhishi.server.routes import ai


ITEM = {"item_key": "receipt-total", "source_excerpt": "2026-09-05 实付28.50元",
        "proposal": {"kind": "ledger", "data": {"day": "2026-09-05", "direction": "expense", "amount": "28.50"}}}


def call(name, args, n):
    return {0: DeltaToolCall(name=name, json_args=json.dumps(args), tool_call_id=f"call-{n}")}


def returned(messages):
    return [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]


def test_missing_field_then_repeat_then_approval_resume_keeps_text_identity(tmp_path, monkeypatch):
    """A deliberately imperfect model uses validation feedback and repeats across deferred execution."""
    calls = 0
    async def stream(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            yield call("propose_inbox_items", {"items": [{k: v for k, v in ITEM.items() if k != "source_excerpt"}]}, calls)
        elif calls == 2:
            retry = [p for m in messages for p in m.parts if isinstance(p, RetryPromptPart)]
            assert retry and "source_excerpt" in str(retry[-1].content)
            yield call("propose_inbox_items", {"items": [ITEM]}, calls)
        elif calls == 3:
            result = json.loads(returned(messages)[-1].content)
            assert result["ok"] and "还没有创建" in result["next_step"]
            yield call("propose_inbox_items", {"items": [ITEM]}, calls)
        elif calls == 4:
            rows = [json.loads(p.content)["items"][0] for p in returned(messages)
                    if p.tool_name == "propose_inbox_items"]
            assert rows[0]["id"] == rows[1]["id"]
            yield call("apply_inbox_item", {"item_id": rows[-1]["id"], "version": rows[-1]["version"]}, calls)
        elif calls == 5:
            # New runtime after approval: repeated extraction must find the applied item.
            yield call("propose_inbox_items", {"items": [ITEM]}, calls)
        else:
            row = json.loads(returned(messages)[-1].content)["items"][0]
            assert row["status"] == "applied" and row["target_id"]
            yield "确认完成，账本中已有这一笔。"
    monkeypatch.setattr(ai, "build_model", lambda *a, **k: FunctionModel(stream_function=stream))
    with TestClient(create_app(data_dir=tmp_path)) as c:
        _seed_enabled_config(c)
        events = _parse_sse(c.post("/ai/chat/stream", json={"message": "整理并确认这笔收支：2026-09-05 实付28.50元"}).text)
        assert not [e for e in events if e["type"] == "run_error"]
        assert any(e["type"] == "tool_call_result" and not e["ok"] for e in events)
        assert c.get("/api/inbox").json()["total"] == 1
        assert c.get("/api/ledger").json()["total"] == 0
        from zhishi.domain.models import AIPendingAction
        with c.app.state.session_factory() as db:
            pending = db.query(AIPendingAction).one()
            action_id, cid = pending.id, pending.conversation_id
        assert c.post(f"/ai/actions/{action_id}/approve").status_code == 200
        resumed = _parse_sse(c.post(f"/ai/conversations/{cid}/resume/stream").text)
        assert not [e for e in resumed if e["type"] == "run_error"]
        assert c.get("/api/ledger").json()["total"] == 1
        assert c.get("/api/inbox").json()["total"] == 0
        assert c.get("/api/inbox?status=applied").json()["total"] == 1
        assert calls == 6


def test_attachment_has_explicit_id_and_reupload_processed_records(tmp_path, monkeypatch):
    expected_id = None
    processed = False
    calls = 0
    async def stream(messages, info):
        nonlocal calls
        calls += 1
        if calls in (1, 3):
            text = str(messages)
            assert f"source_file_id={expected_id}" in text
            assert "propose_inbox_items" in text and "receipt-total" in text
            if processed:
                assert '"status": "applied"' in text
            yield call("propose_inbox_items", {"items": [{**ITEM, "source_file_id": expected_id}]}, calls)
        else:
            row = json.loads(returned(messages)[-1].content)["items"][0]
            assert row["status"] == ("applied" if processed else "pending")
            yield "已处理过。" if processed else "已放入收件箱。"
    monkeypatch.setattr(ai, "build_model", lambda *a, **k: FunctionModel(stream_function=stream))
    with TestClient(create_app(data_dir=tmp_path)) as c:
        _seed_enabled_config(c)
        for filename in ("receipt.txt", "renamed.txt"):
            expected_id = c.post("/ai/attachments", files={"file": (filename, ITEM["source_excerpt"].encode(), "text/plain")}).json()["file_id"]
            events = _parse_sse(c.post("/ai/chat/stream", json={"message": "帮我整理", "attachment_ids": [expected_id]}).text)
            assert not [e for e in events if e["type"] == "run_error"]
            if not processed:
                row = c.get("/api/inbox").json()["items"][0]
                assert c.post(f"/api/inbox/{row['id']}/apply", json={"version": row["version"]}).status_code == 200
                processed = True
        assert c.get("/api/ledger").json()["total"] == 1
        assert c.get("/api/inbox?status=applied").json()["total"] == 1


def test_conflicting_extraction_returns_exact_recovery_tool(tmp_path, monkeypatch):
    calls = 0
    async def stream(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            yield call('propose_inbox_items', {'items': [ITEM]}, calls)
        elif calls == 2:
            altered = {**ITEM, 'uncertainty': '付款方式待确认'}
            yield call('propose_inbox_items', {'items': [altered]}, calls)
        elif calls == 3:
            failed = json.loads(returned(messages)[-1].content)
            assert failed['ok'] is False and failed['code'] == 'inbox_conflict'
            # No exploration: execute the exact next tool/arguments supplied by the program.
            yield call(failed['next_call']['tool'], failed['next_call']['args'], calls)
        else:
            row = json.loads(returned(messages)[-1].content)
            assert row['status'] == 'pending' and row['version'] == 1
            yield '已有候选，请先核对这条。'
    monkeypatch.setattr(ai, 'build_model', lambda *a, **k: FunctionModel(stream_function=stream))
    with TestClient(create_app(data_dir=tmp_path)) as c:
        _seed_enabled_config(c)
        events = _parse_sse(c.post('/ai/chat/stream', json={'message': '整理这笔收支：2026-09-05 实付28.50元'}).text)
        assert not [e for e in events if e['type'] == 'run_error']
        assert any(e['type'] == 'tool_call_result' and not e['ok'] for e in events)
        assert c.get('/api/inbox').json()['total'] == 1
        assert c.get('/api/ledger').json()['total'] == 0
