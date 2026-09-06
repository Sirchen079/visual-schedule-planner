# ruff: noqa: DTZ001
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from zhishi.domain.models import (
    KeyResult,
    ResearchCurriculum,
    ResearchTask,
    Subtask,
    Task,
    TaskScheduleEntry,
    TimeLog,
)
from zhishi.domain.research import service, sources
from zhishi.domain.research.schemas import ExtensionDraft, PlanDraft, ProjectCreate, RevisionDraft
from zhishi.domain.schedule import service as schedule
from zhishi.domain.tasks import service as tasks

NOW = datetime(2026, 9, 8, 9)


def setup(db):
    p = service.create_project(db, ProjectCreate(title='研究方法', objective='理解并完成实验',
        start_date=date(2026,9,8), end_date=date(2026,9,20), daily_minutes=180,
        window_start='18:00', window_end='21:00'))
    plan = service.preview_plan(db, p.id, PlanDraft(version=1, rationale='阅读后实验再总结', steps=[
        {'title':name, 'outcome':f'完成{name}并记录', 'minutes':45} for name in ('基础','实验','总结')]), now=NOW)
    service.apply_plan(db, plan.id, now=NOW)
    detail = service.detail(db, p.id)
    tasks.update_task(db, detail.tasks[0].task_id, status='done')
    return service.detail(db, p.id)


def draft(db, detail, mode='insert_before', minutes=45, **kwargs):
    return RevisionDraft(version=service.get_project(db, detail.project.id).version,
        mode=mode, target_link_id=detail.tasks[1].id, rationale='先通过小例子巩固，再进入实验',
        steps=[{'title':'小例子巩固', 'outcome':'逐步解释并复现结果', 'minutes':minutes}], **kwargs)


def test_insertion_order_survives_replan_and_later_extension(db):
    detail = setup(db)
    pid = detail.project.id
    plan = service.preview_revision(db, pid, draft(db, detail), now=NOW)
    assert plan.revision.new_unit_indices == [0]
    assert [u.existing_task_id for u in plan.units] == [None, detail.tasks[1].task_id, detail.tasks[2].task_id]
    assert service.detail(db,pid).project.total_tasks == 3
    applied = service.apply_plan(db, plan.id, now=NOW)
    current = service.detail(db,pid)
    assert [t.title for t in current.tasks] == ['基础','小例子巩固','实验','总结']
    assert current.tasks[0] == detail.tasks[0] and current.project.completed_tasks == 1
    assert applied.result['new_tasks'] == 1 and applied.result['replaced_tasks'] == 0
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    with factory() as fresh:
        replanned = service.preview_replan(fresh, pid, service.get_project(fresh,pid).version, now=NOW)
        assert [u.title for u in replanned.units] == ['小例子巩固','实验','总结']
        assert [a.start for a in replanned.assignments] == ['18:45','19:30','20:15']
        service.apply_plan(fresh, replanned.id, now=NOW)
        extended = service.preview_extension(fresh,pid,ExtensionDraft(version=service.get_project(fresh,pid).version,
            rationale='进入新的阶段',steps=[{'title':'下一阶段','outcome':'探索另一个方法','minutes':45}]),now=NOW)
        service.apply_plan(fresh,extended.id,now=NOW)
        assert [t.title for t in service.detail(fresh,pid).tasks] == ['基础','小例子巩固','实验','总结','下一阶段']


def test_replacement_reuses_identity_splits_extras_and_keeps_before_snapshot(db, monkeypatch):
    detail = setup(db)
    monkeypatch.setattr(sources.web,'fetch_document',lambda url:sources.web.WebDocument('用于新内容的参考正文。'))
    source = sources.add_source(db,detail.project.id,'https://example.org/new','新资料')
    payload = draft(db,detail,mode='replace',minutes=90)
    payload.steps[0].source_ids = [source.id]
    original = detail.tasks[1]
    plan = service.preview_revision(db,detail.project.id,payload,now=NOW)
    assert plan.revision.before_task == original
    applied = service.apply_plan(db,plan.id,now=NOW)
    current = service.detail(db,detail.project.id)
    assert [t.title for t in current.tasks] == ['基础','小例子巩固 · 1/2','小例子巩固 · 2/2','总结']
    replaced = current.tasks[1]
    assert replaced.id == original.id and replaced.task_id == original.task_id
    assert replaced.source_ids == [source.id] and '逐步解释' in replaced.notes
    assert db.get(Task, original.task_id).files[0].id == source.library_file_id
    assert service.plan_read(service.get_plan(db,plan.id)).revision.before_task == original
    assert applied.result['new_tasks'] == 1 and applied.result['replaced_tasks'] == 1
    assert db.scalar(select(KeyResult)).target_value == 4
    assert current.tasks[0] == detail.tasks[0]


def test_manual_anchor_stays_fixed_when_no_room_for_insertion(db):
    detail = setup(db)
    manual = db.scalar(select(TaskScheduleEntry).where(TaskScheduleEntry.task_id==detail.tasks[1].task_id))
    manual.start_time, manual.end_time, manual.note = '18:00', '18:45', '手动固定'
    db.commit()
    plan = service.preview_revision(db,detail.project.id,draft(db,detail),now=NOW)
    assert not plan.assignments
    assert plan.units[0].not_after == '2026-09-08T18:00'
    assert '后续安排' in plan.unassigned[0].reason and plan.revision.warnings
    service.apply_plan(db,plan.id,now=NOW)
    db.refresh(manual)
    assert manual.start_time == '18:00' and manual.note == '手动固定'
    replan = service.preview_replan(db,detail.project.id,service.get_project(db,detail.project.id).version,now=NOW)
    assert replan.units[0].title == '小例子巩固' and not replan.assignments
    assert replan.units[0].not_after == '2026-09-08T18:00'


def test_replace_manual_requires_exact_consent_and_preserves_other_manual_slot(db):
    detail = setup(db)
    first = db.scalar(select(TaskScheduleEntry).where(TaskScheduleEntry.task_id==detail.tasks[1].task_id))
    second = db.scalar(select(TaskScheduleEntry).where(TaskScheduleEntry.task_id==detail.tasks[2].task_id))
    first.note, second.note = '人工安排一', '人工安排二'
    second.date = date(2026,9,10)
    db.commit()
    with pytest.raises(service.ResearchConflict,match='手工'):
        service.preview_revision(db,detail.project.id,draft(db,detail,mode='replace'),now=NOW)
    plan = service.preview_revision(db,detail.project.id,draft(db,detail,mode='replace',movable_task_link_ids=[detail.tasks[1].id]),now=NOW)
    assert [t['task_link_id'] for t in plan.revision.moved_manual] == [detail.tasks[1].id]
    service.apply_plan(db,plan.id,now=NOW)
    db.refresh(second)
    assert second.note == '人工安排二' and second.date == date(2026,9,10)
    assert db.get(Task,detail.tasks[1].task_id).title == '小例子巩固'


@pytest.mark.parametrize('change',['notes','progress','subtask','focus'])
def test_changes_since_preview_reject_replacement_without_writes(db,change):
    detail = setup(db)
    tid = detail.tasks[1].task_id
    plan = service.preview_revision(db,detail.project.id,draft(db,detail,mode='replace'),now=NOW)
    task = db.get(Task,tid)
    if change == 'notes':
        task.notes = '用户刚刚补充的重要笔记'
    elif change == 'progress':
        task.progress = 25
    elif change == 'subtask':
        db.add(Subtask(task_id=tid,title='刚刚拆解的子任务'))
    else:
        db.add(TimeLog(task_id=tid,task_title=task.title,started_at=NOW,kind='focus'))
    db.commit()
    with pytest.raises(service.ResearchConflict,match='日历或任务'):
        service.apply_plan(db,plan.id,now=NOW)
    assert db.get(Task,tid).title == '实验'
    assert service.get_plan(db,plan.id).state == 'draft'


def test_original_slot_starting_after_preview_requires_fresh_preview(db):
    detail = setup(db)
    schedule.create_event(db,title='新增占用',date=NOW.date(),start_time='18:45',end_time='20:00')
    plan = service.preview_revision(db,detail.project.id,draft(db,detail,mode='replace'),now=NOW)
    assert plan.assignments[0].start == '20:00'
    with pytest.raises(service.ResearchConflict,match='原安排已经开始'):
        service.apply_plan(db,plan.id,now=datetime(2026,9,8,19))
    assert db.get(Task,detail.tasks[1].task_id).title == '实验'


def test_mid_apply_failure_rolls_back_content_links_slots_and_order(db,monkeypatch):
    detail = setup(db)
    plan = service.preview_revision(db,detail.project.id,draft(db,detail,mode='replace',minutes=90),now=NOW)
    old_link = (db.get(ResearchTask,detail.tasks[1].id).plan_id,db.get(ResearchTask,detail.tasks[1].id).unit_index)
    def fail(*args,**kwargs):
        raise RuntimeError('injected new-task failure')
    monkeypatch.setattr(tasks,'create_task',fail)
    with pytest.raises(RuntimeError):
        service.apply_plan(db,plan.id,now=NOW)
    assert service.task_rows(db,detail.project.id) == [t.model_dump() for t in detail.tasks]
    assert (db.get(ResearchTask,detail.tasks[1].id).plan_id,db.get(ResearchTask,detail.tasks[1].id).unit_index) == old_link
    assert db.get(ResearchCurriculum,detail.project.id) is None
    assert service.get_project(db,detail.project.id).version == detail.project.version


def test_concurrent_replacement_and_history_are_idempotent(db):
    detail = setup(db)
    plan = service.preview_revision(db,detail.project.id,draft(db,detail,mode='replace',minutes=90),now=NOW)
    factory = sessionmaker(bind=db.get_bind(),expire_on_commit=False)
    def apply(_):
        with factory() as session:
            return service.apply_plan(session,plan.id,now=NOW).result
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(apply,range(8)))
    assert all(r==results[0] for r in results)
    assert db.scalar(select(func.count()).select_from(Task)) == 4
    history = service.plan_history(db,detail.project.id)
    assert [p.kind for p in history.items] == ['revision','initial']
    assert not history.next_before


@pytest.mark.parametrize('mode',['insert_before','replace'])
def test_started_and_cross_project_targets_rejected(db,mode):
    detail = setup(db)
    payload = draft(db,detail,mode=mode)
    payload.target_link_id = detail.tasks[0].id
    with pytest.raises(service.ResearchConflict,match='尚未开始'):
        service.preview_revision(db,detail.project.id,payload,now=NOW)
    other = setup(db)
    payload.target_link_id = other.tasks[1].id
    with pytest.raises(service.ResearchConflict,match='本项目'):
        service.preview_revision(db,detail.project.id,payload,now=NOW)
    payload.target_link_id = detail.tasks[1].id
    payload.movable_task_link_ids = [other.tasks[1].id]
    with pytest.raises(service.ResearchConflict,match='不属于'):
        service.preview_revision(db,detail.project.id,payload,now=NOW)
