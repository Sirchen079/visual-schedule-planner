"""摘要初始化阶段的路由生命周期：隔离数据库、可控挂起、不访问模型服务。"""
import asyncio
import json
import threading
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse, ToolCallPart

from tests.agent.test_compaction import _history
from zhishi.agent import compaction
from zhishi.domain.models import AIConfig, AIConversation, AIMessage, AIPendingAction, AIRun
from zhishi.domain.settingsvc import set_setting
from zhishi.infra.database import make_session_factory
from zhishi.server.routes import ai


@pytest.fixture
def initialized(db, tmp_path, monkeypatch, request):
    conv = AIConversation(title="摘要生命周期")
    db.add(conv)
    db.add(AIConfig(name="test", provider_kind="openai_compat", model="test", enabled=True))
    db.commit()
    history = _history(14)
    resume = getattr(request.node, 'callspec', None) is None or request.node.callspec.params.get('kind') != 'chat'
    if resume:
        history.append(ModelResponse(parts=[ToolCallPart(
            tool_name="create_task", args={"title": "test"}, tool_call_id="pending-call")]))
    db.add(AIMessage(conversation_id=conv.id, role="assistant", display_json="{}",
                     history_json=ModelMessagesTypeAdapter.dump_json(history).decode()))
    db.add(AIRun(run_id="old-run", conversation_id=conv.id, status="awaiting_approval" if resume else 'completed'))
    db.add(AIPendingAction(conversation_id=conv.id, run_id="old-run",
                          tool_call_id="pending-call", tool_name="create_task",
                          args_json='{"title":"test"}', status="confirmed"))
    db.commit()
    app = SimpleNamespace(state=SimpleNamespace(
        session_factory=make_session_factory(db.get_bind()), active_runs={}, cancel_tokens={},
        storage_root=tmp_path))

    class Runtime:
        def __init__(self, **kwargs):
            pass

        async def run_stream(self, **kwargs):
            yield {"type": "run_started", "run_id": kwargs["run_id"]}
            yield {"type": "done", "run_id": kwargs["run_id"]}

    monkeypatch.setattr(ai, "build_model", lambda cfg: object())
    monkeypatch.setattr(ai, "AgentRuntime", Runtime)
    monkeypatch.setattr(compaction, "build_model", lambda cfg: object())
    return app, conv.id


async def _request(app, cid, kind):
    if kind == "resume":
        return await ai.resume_stream(cid, SimpleNamespace(app=app))
    return await ai._start_run(app, message="继续", conversation_id=cid)


async def _consume(response):
    return [part async for part in response.body_iterator]


@pytest.mark.parametrize("kind", ["chat", "resume"])
async def test_cancel_during_compaction_releases_slot_without_late_write(
        db, initialized, monkeypatch, kind):
    app, cid = initialized
    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def slow(model, system, user):
        started.set()
        release.wait(5)
        finished.set()
        return "不应补写的迟到摘要"

    monkeypatch.setattr(compaction, "oneshot_text", slow)
    task = asyncio.create_task(_request(app, cid, kind))
    try:
        assert await asyncio.to_thread(started.wait, 3)
        assert cid in app.state.active_runs
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert app.state.active_runs == {}
        assert app.state.cancel_tokens == {}
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.to_thread(finished.wait, 3)
    # 让 worker 从 oneshot 返回、路由清理完成；不能在取消后补写旧摘要。
    await asyncio.sleep(0.05)
    db.expire_all()
    assert "summary" not in json.loads(db.get(AIConversation, cid).meta_json)
    assert db.query(AIPendingAction).one().status == "confirmed"
    monkeypatch.setattr(compaction, "oneshot_text", lambda *args: "正常摘要")
    response = await _request(app, cid, kind)
    assert await _consume(response)
    assert app.state.active_runs == {}


@pytest.mark.parametrize("kind", ["chat", "resume"])
async def test_compaction_timeout_allows_next_request(db, initialized, monkeypatch, kind):
    app, cid = initialized
    set_setting(db, "compaction_timeout", "0.05")
    db.commit()
    release = threading.Event()

    def slow(*args):
        release.wait(3)
        return "超时结果"

    monkeypatch.setattr(compaction, "oneshot_text", slow)
    try:
        response = await asyncio.wait_for(_request(app, cid, kind), timeout=1)
        assert await _consume(response)
        assert app.state.active_runs == {}
        assert app.state.cancel_tokens == {}
        db.expire_all()
        assert "summary" not in json.loads(db.get(AIConversation, cid).meta_json)
        monkeypatch.setattr(compaction, "oneshot_text", lambda *args: "正常摘要")
        response = await ai._start_run(app, message="下一轮", conversation_id=cid)
        assert await _consume(response)
        assert app.state.active_runs == {}
    finally:
        release.set()


async def test_resume_checks_active_slot_before_compaction(initialized, monkeypatch):
    app, cid = initialized
    app.state.active_runs[cid] = "existing-run"
    calls = []
    monkeypatch.setattr(compaction, "oneshot_text", lambda *args: calls.append(1) or "摘要")
    with pytest.raises(HTTPException) as error:
        await _request(app, cid, "resume")
    assert error.value.status_code == 409
    assert not calls
    assert app.state.active_runs[cid] == "existing-run"


def test_release_slot_does_not_remove_another_run(initialized):
    app, cid = initialized
    app.state.active_runs[cid] = "new-owner"
    ai._release_run_slot(app, "old-owner", cid)
    assert app.state.active_runs[cid] == "new-owner"
