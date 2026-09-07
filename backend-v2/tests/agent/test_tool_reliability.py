import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from zhishi.agent.mutations import MutationConflict
from zhishi.agent.tool_feedback import FailureTracker, failure_result
from zhishi.agent.tools import atomic_write as aw
from zhishi.agent.tools import macro
from zhishi.domain.models import (
    AIConversation,
    AIRun,
    AIToolExecution,
    AIWriteReceipt,
    Event,
    Habit,
    LibraryFile,
    Subtask,
    Task,
    TaskScheduleEntry,
)


def context(db, *, capture='request-one', cid=None):
    if cid is None:
        row = AIConversation(title='Tool reliability')
        db.add(row)
        db.commit()
        cid = row.id
    return SimpleNamespace(deps=SimpleNamespace(conversation_id=cid, capture_key=capture))


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_mutations_replay_same_request_but_allow_explicit_distinct_operations(db):
    ctx = context(db)
    first = json.loads(aw.create_task(db, title='A task', ctx=ctx))
    second = json.loads(aw.create_task(db, title='A task', ctx=ctx))
    assert first['id'] == second['id'] and second['replayed']
    other = context(db, capture='request-two', cid=ctx.deps.conversation_id)
    assert json.loads(aw.create_task(db, title='A task', ctx=other))['id'] != first['id']
    a = json.loads(aw.create_task(db, title='Explicit', request_key='operation-a', ctx=ctx))
    assert json.loads(aw.create_task(db, title='Explicit', request_key='operation-a', ctx=other))['id'] == a['id']
    assert json.loads(aw.create_task(db, title='Explicit', request_key='operation-b', ctx=ctx))['id'] != a['id']
    with pytest.raises(MutationConflict):
        aw.create_task(db, title='Changed', request_key='operation-a', ctx=ctx)
    assert count(db, Task) == 4
    event = json.loads(aw.create_event(db, title='Meeting', day='2026-09-08', ctx=ctx))
    assert json.loads(aw.create_event(db, title='Meeting', day='2026-09-08', ctx=ctx))['event_id'] == event['event_id']
    habit = Habit(name='Read', target_count=1)
    db.add(habit)
    db.commit()
    assert json.loads(aw.check_in_habit(db, habit.id, day='2026-09-08', ctx=ctx))['count'] == 1
    assert json.loads(aw.check_in_habit(db, habit.id, day='2026-09-08', ctx=ctx))['count'] == 1
    assert json.loads(aw.check_in_habit(db, habit.id, day='2026-09-08', ctx=other))['count'] == 2


def test_concurrent_mutation_and_restart_replay_one_commit(tmp_path):
    from zhishi.infra.database import create_all, make_engine, make_session_factory
    engine = make_engine(tmp_path / 'concurrent.db')
    create_all(engine)
    factory = make_session_factory(engine)
    with factory() as db:
        cid = context(db).deps.conversation_id
    def create(_):
        with factory() as db:
            ctx = context(db, cid=cid)
            return json.loads(aw.create_task(db, title='One write', ctx=ctx))['id']
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(create, range(8)))
    assert len(set(ids)) == 1
    engine.dispose()
    engine = make_engine(tmp_path / 'concurrent.db')
    factory = make_session_factory(engine)
    with factory() as db:
        assert json.loads(aw.create_task(db, title='One write', ctx=context(db, cid=cid)))['replayed']
        assert count(db, Task) == count(db, AIWriteReceipt) == 1
    engine.dispose()


def test_subtask_batch_rolls_back_and_can_retry_same_key(db, monkeypatch):
    from zhishi.domain import subtasks
    ctx = context(db)
    parent = json.loads(aw.create_task(db, title='Parent'))['id']
    original, calls = subtasks.create_subtask, []
    def failing(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(result.id)
        if len(calls) == 2:
            raise RuntimeError('simulated failure after second flush')
        return result
    monkeypatch.setattr(subtasks, 'create_subtask', failing)
    payload = [{'title':'First'}, {'title':'Second'}]
    with pytest.raises(RuntimeError):
        aw.create_subtasks(db, parent, payload, request_key='batch', ctx=ctx)
    assert count(db, Subtask) == count(db, AIWriteReceipt) == 0
    assert db.get(Task, parent).status == 'todo'
    monkeypatch.setattr(subtasks, 'create_subtask', original)
    saved = json.loads(aw.create_subtasks(db, parent, payload, request_key='batch', ctx=ctx))
    assert len(saved['created']) == 2
    assert json.loads(aw.create_subtasks(db, parent, payload, request_key='batch', ctx=ctx))['replayed']
    assert count(db, Subtask) == 2


def test_invalid_web_batch_and_failed_commit_leave_no_links_or_receipts(db, monkeypatch):
    ctx = context(db)
    with pytest.raises(ValidationError):
        aw.import_web_resources(db, [{'title':'Good','url':'https://example.org'},
                                     {'title':'Bad','url':'file:///private'}], ctx=ctx)
    assert count(db, LibraryFile) == 0
    original = db.commit
    def unavailable():
        raise RuntimeError('simulated commit failure')
    monkeypatch.setattr(db, 'commit', unavailable)
    with pytest.raises(RuntimeError):
        aw.create_event(db, title='Uncommitted', day='2026-09-08', request_key='event', ctx=ctx)
    monkeypatch.setattr(db, 'commit', original)
    assert count(db, Event) == count(db, AIWriteReceipt) == 0
    assert json.loads(aw.create_event(db, title='Uncommitted', day='2026-09-08', request_key='event', ctx=ctx))['ok']


def test_day_plan_has_ready_arguments_and_stale_batch_rolls_back(db):
    ctx = context(db)
    aw.create_task(db, title='First', estimated_minutes=45)
    aw.create_task(db, title='Second', estimated_minutes=45)
    plan = json.loads(macro.plan_day(db, '2026-09-08'))
    assert plan['next_call']['args']['assignments'] == plan['assignments']
    bad = [plan['assignments'][0], {**plan['assignments'][1], 'task_id':99999}]
    with pytest.raises(macro.StaleDayPlan) as caught:
        macro.apply_day_plan(db, '2026-09-08', bad, ctx=ctx)
    assert count(db, TaskScheduleEntry) == count(db, AIWriteReceipt) == 0
    error = failure_result(caught.value, tool='apply_day_plan', arguments={'day':'2026-09-08'})
    assert error['write_status'] == 'not_applied' and error['next_call']['tool'] == 'plan_day'
    result = json.loads(macro.apply_day_plan(db, **plan['next_call']['args'], ctx=ctx))
    assert len(result['applied']) == 2 and result['next_call']['tool'] == 'list_day_schedule'
    assert json.loads(macro.apply_day_plan(db, **plan['next_call']['args'], ctx=ctx))['replayed']


def test_timetable_prevalidates_whole_batch_and_surfaces_bad_periods(db):
    good = {'title':'A','weekday':2,'periods':[1,2],'start_week':1,'end_week':4}
    bad = {**good,'title':'B','periods':[1,3]}
    result = json.loads(macro.import_timetable(db, '2026-09-07', [good,bad]))
    assert result['ok'] is False and result['write_status'] == 'not_applied'
    assert count(db, Event) == 0


def test_reschedule_uses_real_free_slots_and_does_not_duplicate_future_work(db):
    from freezegun import freeze_time

    from zhishi.domain.schedule import conflicts, service
    with freeze_time('2026-09-08 08:00'):
        ctx = context(db)
        for i in range(5):
            aw.create_task(db, title=f'Overdue {i}', due_date='2026-09-07', estimated_minutes=90)
        service.create_event(db, title='Busy', date=date(2026,9,8), start_time='09:00', end_time='11:00')
        result = json.loads(macro.reschedule_overdue(db, horizon_days=2, ctx=ctx))
        assert len(result['moved']) == 5
        assert all(item['start'] < item['end'] for item in result['moved'])
        assert not conflicts.check_conflicts(db, date(2026,9,8), date(2026,9,9))
        again = context(db, cid=ctx.deps.conversation_id, capture='another-request')
        assert json.loads(macro.reschedule_overdue(db, horizon_days=2, ctx=again))['moved'] == []
        assert count(db, TaskScheduleEntry) == 5


def test_failure_policy_blocks_uncertain_write_without_retrying():
    tracker = FailureTracker()
    failure = {'ok':False,'write_status':'unknown','error':'lost response'}
    tracker.record('remote_pay', {'amount':10}, failure)
    assert tracker.blocked('remote_pay', {'amount':10})['code'] == 'unresolved_write'
    for _ in range(2):
        tracker.record('read', {'id':1}, {'ok':False,'write_status':'not_applicable','error':'offline'})
    assert tracker.blocked('read', {'id':1})['code'] == 'repeated_failure'
    assert tracker.blocked('read', {'id':2}) is None
    tracker.record('read', {'id':1}, {'ok':True})
    assert tracker.blocked('read', {'id':1}) is None


def test_work_plan_evidence_rejects_failed_and_other_conversation_calls(db):
    ctx = context(db)
    other = context(db)
    db.add_all([AIRun(run_id='r1', conversation_id=ctx.deps.conversation_id),
                AIRun(run_id='r2', conversation_id=other.deps.conversation_id)])
    db.commit()
    db.add_all([AIToolExecution(run_id='r1',call_id='success',tool='create_task',status='completed',result_json='{"id":1}'),
                AIToolExecution(run_id='r1',call_id='failed',tool='create_task',status='completed',result_json='{"ok":false}'),
                AIToolExecution(run_id='r2',call_id='other',tool='create_task',status='completed',result_json='{"id":2}')])
    db.commit()
    saved = json.loads(aw.update_work_plan(db, [{'title':'Create','status':'已完成','evidence_call_ids':['success']}], ctx=ctx))
    assert saved['steps'][0]['verification'] == 'tool_receipt'
    for invalid in ['failed','other','invented']:
        with pytest.raises(ValueError):
            aw.update_work_plan(db, [{'title':'Create','status':'已完成','evidence_call_ids':[invalid]}], ctx=ctx)
    state = json.loads(db.get(AIConversation, ctx.deps.conversation_id).meta_json)
    assert state['work_plan'][0]['evidence'][0]['call_id'] == 'success'


def test_soft_delete_batch_rolls_back_on_failure_and_returns_exact_missing_ids(db, monkeypatch):
    from zhishi.domain.tasks import service
    ids = [json.loads(aw.create_task(db, title=f'Task {index}'))['id'] for index in range(2)]
    ctx = context(db)
    original = service.soft_delete_task
    def failing(db, task_id, **kwargs):
        original(db, task_id, **kwargs)
        if task_id == ids[1]:
            raise RuntimeError('simulated second delete failure')
    monkeypatch.setattr(service, 'soft_delete_task', failing)
    with pytest.raises(RuntimeError):
        aw.bulk_delete_tasks(db, ids, ctx=ctx)
    assert all(db.get(Task, task_id).deleted_at is None for task_id in ids)
    monkeypatch.setattr(service, 'soft_delete_task', original)
    result = json.loads(aw.bulk_delete_tasks(db, [*ids,99999], ctx=ctx))
    assert result['deleted'] == ids and result['missing'] == [99999]


def test_destructive_cleanup_reports_partial_result_instead_of_losing_successes(db, monkeypatch):
    from zhishi.domain.tasks import service
    ids = [json.loads(aw.create_task(db, title=f'Trash {index}'))['id'] for index in range(2)]
    for task_id in ids:
        service.soft_delete_task(db, task_id)
    original = service.purge_task
    def failing(db, task_id):
        if task_id == ids[1]:
            raise RuntimeError('simulated protected reference')
        original(db, task_id)
    monkeypatch.setattr(service, 'purge_task', failing)
    result = json.loads(aw.empty_trash(db))
    assert result['ok'] is False and result['write_status'] == 'partial'
    assert result['purged'] == 1 and result['failed_items'][0]['id'] == ids[1]
    assert db.get(Task, ids[0]) is None and db.get(Task, ids[1]) is not None


def test_equivalent_defaults_replay_and_existing_links_are_returned(db):
    ctx = context(db)
    first = json.loads(aw.create_task(db, title=' Task ', remind_offsets=[30,0], tag_names=['b','a'], ctx=ctx))
    second = json.loads(aw.create_task(db, title='Task', remind_offsets=[0,30], tag_names=['a','b'], ctx=ctx))
    assert first['id'] == second['id'] and second['replayed']
    link = {'title':'Link','url':'https://example.org/resource'}
    result = json.loads(aw.import_web_resources(db, [link,link], ctx=ctx))
    assert len(result['created']) == len(result['skipped']) == 1
    assert count(db, LibraryFile) == 1
    from zhishi.agent.tools.atomic_read import get_task
    from zhishi.domain.library import service
    service.attach_to_task(db, first['id'], result['created'][0]['id'])
    assert json.loads(get_task(db, first['id']))['files'][0]['name'] == 'Link'
