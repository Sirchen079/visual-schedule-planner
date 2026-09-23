"""AI run 终态通知 + 会话自动命名：SSE 全链路 + 后台命名任务。

FunctionModel 按消息内容分流：含「会话命名助手」指令的请求是自动命名的
一次性调用，返回固定标题；其余按对话脚本（文本 / 审批 / 提问 / 抛错）分流。
"""
import json
import time

from fastapi.testclient import TestClient
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from tests.server.test_ai_routes import parse_sse
from zhishi.server.app import create_app

TITLE_REPLY = '「行程规划讨论」'   # 故意带引号返回，锁定 _clean_title 清洗
NAMED_TITLE = '行程规划讨论'


def _joined_text(messages) -> str:
    return ''.join(str(getattr(p, 'content', '')) for m in messages for p in m.parts)


def install_stream_model(monkeypatch, *, delete_call=False, ask_question=False,
                         boom=False, naming_reply=TITLE_REPLY, naming_boom=False):
    """build_model → FunctionModel：对话主体按 delete_call/ask_question/boom 分流；
    命名请求返回 naming_reply（naming_boom=True 时抛异常模拟模型故障）。"""
    import zhishi.server.routes.ai as ai_route
    state = {'step': 0}

    async def stream(messages, info):
        # Agent instructions 不进 FunctionModel 消息（provider 层注入），
        # 用命名专属的用户提示语识别一次性命名调用。
        if '请输出会话标题' in _joined_text(messages):
            if naming_boom:
                raise RuntimeError('命名模型不可用')
            yield naming_reply
            return
        if boom:
            raise RuntimeError('模型连接失败')
        results = [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
        if delete_call and not any(p.tool_name == 'delete_task' for p in results):
            state['step'] += 1
            yield {0: DeltaToolCall(name='delete_task', json_args='{"task_id": 42}',
                                    tool_call_id=f'tc{state["step"]}')}
        elif ask_question and not any(p.tool_name == 'ask_user' for p in results):
            yield {0: DeltaToolCall(name='ask_user', json_args=json.dumps(
                {'questions': [{'id': 'scope', 'question': '整理哪段时间？',
                                'options': [{'label': '今天'}]}]}),
                tool_call_id='question-1')}
        else:
            yield '已收到，回复完成。'

    monkeypatch.setattr(ai_route, 'build_model', lambda *a, **k: FunctionModel(stream_function=stream))


def _seed_config(c):
    from zhishi.domain.models import AIConfig
    with c.app.state.session_factory() as db:
        db.add(AIConfig(name='t', provider_kind='openai_compat', model='t',
                        base_url='http://x', enabled=True))
        db.commit()


def _wait_until(predicate, timeout=5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_completed_run_writes_one_notification(tmp_path, monkeypatch):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        _seed_config(c)
        install_stream_model(monkeypatch)
        events = parse_sse(c.post('/ai/chat/stream', json={'message': '帮我整理下周行程'}).text)
        run_id, cid = events[0]['run_id'], events[0]['conversation_id']
        from zhishi.domain.models import NotificationLog
        with c.app.state.session_factory() as db:
            rows = db.query(NotificationLog).filter_by(kind='ai_run').all()
            assert len(rows) == 1
            row = rows[0]
            assert row.dedupe_key == f'ai-run-{run_id}-completed'
            assert row.title == '知时已完成回复'
            assert row.target_path == f'/chat?conversation={cid}'
            assert '帮我整理下周行程' in row.body and '回复已生成' in row.body
            assert row.read_at is None and row.task_id is None


def test_notification_dedupe_is_idempotent(tmp_path, monkeypatch):
    """同一 run 同一状态重复写（轮询/重放）不产生重复行。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        _seed_config(c)
        install_stream_model(monkeypatch)
        events = parse_sse(c.post('/ai/chat/stream', json={'message': '随便聊聊'}).text)
        run_id = events[0]['run_id']
        from zhishi.domain.models import AIRun, NotificationLog
        from zhishi.server.routes.ai import _record_run_notification
        with c.app.state.session_factory() as db:
            row = db.get(AIRun, run_id)
            _record_run_notification(db, row, events[0]['conversation_id'])
            _record_run_notification(db, row, events[0]['conversation_id'])
            assert db.query(NotificationLog).filter_by(kind='ai_run').count() == 1


def test_awaiting_approval_then_resume_writes_both_notifications(tmp_path, monkeypatch):
    """awaiting 与 completed 先后发生：各写各的 dedupe_key，共两行。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        _seed_config(c)
        install_stream_model(monkeypatch, delete_call=True)
        events = parse_sse(c.post('/ai/chat/stream', json={'message': '删掉任务42'}).text)
        first_run, cid = events[0]['run_id'], events[0]['conversation_id']
        approval = next(e for e in events if e['type'] == 'tool_approval_requested')
        assert c.post(f"/ai/actions/{approval['action_id']}/approve").status_code == 200
        resume_events = parse_sse(c.post(f'/ai/conversations/{cid}/resume/stream').text)
        assert any(e['type'] == 'run_completed' for e in resume_events)
        from zhishi.domain.models import NotificationLog
        with c.app.state.session_factory() as db:
            rows = db.query(NotificationLog).filter_by(kind='ai_run').order_by(NotificationLog.id).all()
            assert [r.dedupe_key for r in rows] == [
                f'ai-run-{first_run}-awaiting_approval',
                f'ai-run-{resume_events[0]["run_id"]}-completed']
            assert rows[0].title == '知时需要你的处理' and '待你审批' in rows[0].body
            assert rows[1].title == '知时已完成回复'


def test_awaiting_input_writes_notification(tmp_path, monkeypatch):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        _seed_config(c)
        install_stream_model(monkeypatch, ask_question=True)
        events = parse_sse(c.post('/ai/chat/stream', json={'message': '帮我安排'}).text)
        run_id = events[0]['run_id']
        assert any(e['type'] == 'user_input_requested' for e in events)
        from zhishi.domain.models import NotificationLog
        with c.app.state.session_factory() as db:
            row = db.query(NotificationLog).filter_by(kind='ai_run').one()
            assert row.dedupe_key == f'ai-run-{run_id}-awaiting_input'
            assert '等你回答' in row.body


def test_failed_run_writes_no_notification(tmp_path, monkeypatch):
    """非终态（failed/interrupted）不写通知。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        _seed_config(c)
        install_stream_model(monkeypatch, boom=True)
        events = parse_sse(c.post('/ai/chat/stream', json={'message': '随便说点'}).text)
        assert any(e['type'] == 'run_error' for e in events)
        from zhishi.domain.models import NotificationLog
        with c.app.state.session_factory() as db:
            assert db.query(NotificationLog).filter_by(kind='ai_run').count() == 0


def test_first_completed_run_auto_names_conversation(tmp_path, monkeypatch):
    """自动建会话打 title_auto 标记；首轮完成后后台命名写回并清除标记；
    后续 run 不再改名。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        _seed_config(c)
        install_stream_model(monkeypatch)
        events = parse_sse(c.post('/ai/chat/stream', json={'message': '帮我规划马拉松训练'}).text)
        cid = events[0]['conversation_id']
        from zhishi.domain.models import AIConversation, NotificationLog

        def named():
            with c.app.state.session_factory() as db:
                conv = db.get(AIConversation, cid)
                return conv is not None and conv.title == NAMED_TITLE \
                    and json.loads(conv.meta_json or '{}').get('title_auto') is False

        assert _wait_until(named), '自动命名未在超时内完成'

        # 标记已清除：再跑一轮，标题保持不变
        parse_sse(c.post('/ai/chat/stream', json={'message': '继续', 'conversation_id': cid}).text)
        time.sleep(0.3)
        with c.app.state.session_factory() as db:
            assert db.get(AIConversation, cid).title == NAMED_TITLE
            # 两次完成各写一行通知（不同 run_id 的 dedupe_key）
            keys = {r.dedupe_key for r in db.query(NotificationLog).filter_by(kind='ai_run').all()}
            assert len(keys) == 2 and all(k.endswith('-completed') for k in keys)


def test_naming_failure_keeps_original_title(tmp_path, monkeypatch):
    """模型异常：静默保留原标题（标记保留，后续完成可重试）。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        _seed_config(c)
        install_stream_model(monkeypatch, naming_boom=True)
        events = parse_sse(c.post('/ai/chat/stream', json={'message': '随便聊聊周末去哪'}).text)
        cid = events[0]['conversation_id']
        time.sleep(0.4)   # 给后台命名任务失败收敛留时间
        from zhishi.domain.models import AIConversation
        with c.app.state.session_factory() as db:
            conv = db.get(AIConversation, cid)
            assert conv.title == '随便聊聊周末去哪'
            assert json.loads(conv.meta_json or '{}').get('title_auto') is True


def test_rename_clears_title_auto_and_keeps_other_meta(tmp_path):
    """用户手动改名：标题更新、title_auto 清除、其余 meta 键原样保留。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        from zhishi.domain.models import AIConversation
        with c.app.state.session_factory() as db:
            conv = AIConversation(title='新会话',
                                  meta_json=json.dumps({'title_auto': True, 'plans': [{'id': 1}]}))
            db.add(conv); db.commit(); db.refresh(conv)
            cid = conv.id
        r = c.patch(f'/ai/conversations/{cid}/title', json={'title': ' 我的手动标题 '})
        assert r.status_code == 200
        assert r.json() == {'id': cid, 'title': '我的手动标题'}
        with c.app.state.session_factory() as db:
            conv = db.get(AIConversation, cid)
            assert conv.title == '我的手动标题'
            assert json.loads(conv.meta_json) == {'plans': [{'id': 1}]}
        assert c.patch(f'/ai/conversations/{cid}/title', json={'title': 'x'}).status_code == 200
        assert c.patch('/ai/conversations/9999/title', json={'title': 'x'}).status_code == 404


def test_auto_naming_skips_renamed_conversation(tmp_path):
    """标记已被清除（用户已改名）时直接跳过，绝不覆盖手动标题。"""
    from pydantic_ai.models.function import FunctionModel
    from zhishi.infra.database import create_all, make_engine, make_session_factory
    from zhishi.domain.models import AIConversation, AIMessage
    from zhishi.server.routes.ai import _auto_name_conversation

    engine = make_engine(tmp_path / 'naming.db')
    create_all(engine)
    factory = make_session_factory(engine)
    with factory() as db:
        conv = AIConversation(title='我的手动标题', meta_json=json.dumps({'plans': []}))
        db.add(conv); db.commit(); db.refresh(conv)
        db.add(AIMessage(conversation_id=conv.id, role='user',
                         display_json=json.dumps({'text': '帮我规划训练'})))
        db.add(AIMessage(conversation_id=conv.id, role='assistant',
                         display_json=json.dumps({'text': '好的，这是计划。'})))
        db.commit()
        cid = conv.id

    called = {'n': 0}

    async def stream(messages, info):
        called['n'] += 1
        yield '不应出现的标题'

    import asyncio
    asyncio.run(_auto_name_conversation(factory, cid, FunctionModel(stream_function=stream)))
    with factory() as db:
        assert db.get(AIConversation, cid).title == '我的手动标题'
    assert called['n'] == 0, '已改名的会话不应再调用命名模型'
    engine.dispose()


def test_auto_name_conversation_success_and_cleaning(tmp_path):
    """直接驱动命名协程：标题写回、标记清除、引号/换行被清洗。"""
    from pydantic_ai.models.function import FunctionModel
    from zhishi.infra.database import create_all, make_engine, make_session_factory
    from zhishi.domain.models import AIConversation, AIMessage
    from zhishi.server.routes.ai import _auto_name_conversation

    engine = make_engine(tmp_path / 'naming2.db')
    create_all(engine)
    factory = make_session_factory(engine)
    with factory() as db:
        conv = AIConversation(title='随便聊聊马拉松', meta_json=json.dumps({'title_auto': True}))
        db.add(conv); db.commit(); db.refresh(conv)
        db.add(AIMessage(conversation_id=conv.id, role='user',
                         display_json=json.dumps({'text': '帮我规划马拉松训练安排'})))
        db.add(AIMessage(conversation_id=conv.id, role='assistant',
                         display_json=json.dumps({'text': '好的，这是一份周计划……'})))
        db.commit()
        cid = conv.id

    async def stream(messages, info):
        yield '「马拉松 训练计划」\n多余的第二行'

    import asyncio
    asyncio.run(_auto_name_conversation(factory, cid, FunctionModel(stream_function=stream)))
    with factory() as db:
        conv = db.get(AIConversation, cid)
        assert conv.title == '马拉松 训练计划'
        assert json.loads(conv.meta_json)['title_auto'] is False
    engine.dispose()


def test_clean_title_edge_cases():
    from zhishi.server.routes.ai import _clean_title
    assert _clean_title(None) == ''
    assert _clean_title('   ') == ''
    assert _clean_title('「旅途规划」\n第二行不算') == '旅途规划'
    assert _clean_title('"单行标题"') == '单行标题'
    assert len(_clean_title('很' * 40)) == 15
