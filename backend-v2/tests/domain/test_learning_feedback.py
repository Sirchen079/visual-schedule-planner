# ruff: noqa: DTZ001
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from zhishi.domain import followups
from zhishi.domain.models import (
    KeyResult,
    ResearchFeedback,
    ResearchPlanFeedback,
    Task,
    TaskScheduleEntry,
)
from zhishi.domain.research import feedback, service
from zhishi.domain.research.schemas import ExtensionDraft, FeedbackCreate, PlanDraft, ProjectCreate

NOW = datetime(2026, 9, 8, 9)


def seeded(db):
    project = service.create_project(db, ProjectCreate(title='学习概率', objective='能分析实验结果',
        start_date=date(2026, 9, 8), end_date=date(2026, 9, 20),
        daily_minutes=90, window_start='18:00', window_end='21:00'))
    plan = service.preview_plan(db, project.id, PlanDraft(version=1, rationale='从例子开始',
        steps=[{'title':'理解概率', 'outcome':'解释概率含义', 'minutes':45}]), now=NOW)
    service.apply_plan(db, plan.id, now=NOW)
    return service.detail(db, project.id)


def report(db, detail, **kwargs):
    return feedback.record(db, detail.project.id, FeedbackCreate(version=detail.project.version,
        request_key=kwargs.pop('request_key', 'one'), note='条件概率还是不明白，需要具体例子',
        difficulty='too_hard', actual_minutes=75, task_link_id=detail.tasks[0].id, **kwargs))


def extension(db, pid, fid=None):
    return service.preview_extension(db, pid, ExtensionDraft(version=service.get_project(db, pid).version,
        rationale='用具体抽球实验巩固条件概率', feedback_ids=[fid] if fid else [],
        steps=[{'title':'抽球实验', 'outcome':'画出树形图并解释条件概率', 'minutes':45}]), now=NOW)


def test_feedback_is_self_report_idempotent_and_never_completes_task(db):
    detail = seeded(db)
    first = report(db, detail)
    assert report(db, detail).id == first.id
    current = service.detail(db, detail.project.id)
    assert current.project.version == detail.project.version + 1
    assert current.tasks[0].status == 'todo'
    assert current.feedback.items[0].actual_minutes == 75
    assert current.tasks[0].minutes == 45
    wrong = FeedbackCreate(version=current.project.version, request_key='one', note='另一份内容')
    with pytest.raises(service.ResearchConflict, match='同一反馈'):
        feedback.record(db, detail.project.id, wrong)


def test_append_after_existing_work_and_keep_history_under_concurrent_apply(db):
    detail = seeded(db)
    original_slot = db.scalar(select(TaskScheduleEntry))
    before = (original_slot.id, original_slot.date, original_slot.start_time, original_slot.end_time)
    fid = report(db, detail).id
    plan = extension(db, detail.project.id, fid)
    assert plan.kind == 'extension' and plan.feedback_ids == [fid]
    assert plan.assignments[0].start == '18:45'
    assert db.scalar(select(func.count()).select_from(Task)) == 1
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    def apply(_):
        with factory() as session:
            return service.apply_plan(session, plan.id, now=NOW).result
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(apply, range(8)))
    assert all(r == results[0] for r in results)
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Task)) == 2
    assert db.scalar(select(KeyResult)).target_value == 2
    assert (original_slot.id, original_slot.date, original_slot.start_time, original_slot.end_time) == before
    assert feedback.list_feedback(db, detail.project.id).items[0].applied_plan_ids == [plan.id]
    assert not feedback.pending_difficulties(db, detail.project.id)
    assert db.scalar(select(func.count()).select_from(ResearchPlanFeedback)) == 1


def test_completed_stage_allows_continuation_and_new_feedback_stales_plan(db):
    detail = seeded(db)
    db.get(Task, detail.tasks[0].task_id).status = 'done'
    db.commit()
    assert service.detail(db, detail.project.id).next_step['tool'] == 'preview_research_extension'
    first = extension(db, detail.project.id)
    fid = report(db, service.detail(db, detail.project.id)).id
    with pytest.raises(service.ResearchConflict):
        service.apply_plan(db, first.id, now=NOW)
    second = extension(db, detail.project.id, fid)
    feedback.withdraw(db, detail.project.id, fid, service.get_project(db, detail.project.id).version)
    with pytest.raises(service.ResearchConflict):
        service.apply_plan(db, second.id, now=NOW)
    with pytest.raises(service.ResearchConflict, match='撤回'):
        extension(db, detail.project.id, fid)
    assert not feedback.list_feedback(db, detail.project.id).items
    third = extension(db, detail.project.id)
    service.apply_plan(db, third.id, now=NOW)
    assert service.detail(db, detail.project.id).project.completed_tasks == 1


def test_unscheduled_prerequisite_blocks_new_content_and_replan_can_place_it(db):
    detail = seeded(db)
    db.delete(db.scalar(select(TaskScheduleEntry)))
    db.commit()
    plan = extension(db, detail.project.id)
    assert not plan.assignments and plan.units[0].blocked_by == detail.tasks[0].task_id
    service.apply_plan(db, plan.id, now=NOW)
    replan = service.preview_replan(db, detail.project.id, service.get_project(db, detail.project.id).version, now=NOW)
    assert len(replan.assignments) == 2
    service.apply_plan(db, replan.id, now=NOW)
    assert service.detail(db, detail.project.id).project.total_tasks == 2


def test_cross_project_feedback_and_task_rejected_without_version_mutation(db):
    one, two = seeded(db), seeded(db)
    fid = report(db, one).id
    with pytest.raises(service.ResearchConflict, match='不属于'):
        extension(db, two.project.id, fid)
    version = two.project.version
    with pytest.raises(service.ResearchConflict, match='不属于'):
        feedback.record(db, two.project.id, FeedbackCreate(version=version, request_key='wrong', note='误选',
                                                          task_link_id=one.tasks[0].id))
    assert service.get_project(db, two.project.id).version == version


def test_feedback_scan_deduplicates_and_plan_response_resolves_it(db):
    detail = seeded(db)
    fid = report(db, detail).id
    row = followups.check_project(db, detail.project.id, now=NOW)
    assert row.kind == 'needs_review' and row.plan_id is None
    assert followups.check_project(db, detail.project.id, now=NOW).id == row.id
    plan = extension(db, detail.project.id, fid)
    service.apply_plan(db, plan.id, now=NOW)
    assert followups.check_project(db, detail.project.id, now=NOW) is None
    assert followups.get(db, row.id).status == 'resolved'


def test_feedback_does_not_hide_missed_schedule_or_expired_window(db):
    detail = seeded(db)
    report(db, detail)
    assert followups.observe(db, detail.project.id, datetime(2026, 9, 9, 9))['kind'] == 'replan'
    assert followups.observe(db, detail.project.id, datetime(2026, 9, 21, 9))['kind'] == 'needs_window'


def test_feedback_pagination_and_concurrent_retry(db):
    detail = seeded(db)
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    def add(_):
        with factory() as session:
            return report(session, detail).id
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(add, range(8)))
    assert len(set(ids)) == 1
    for i in range(22):
        feedback.record(db, detail.project.id, FeedbackCreate(version=service.get_project(db, detail.project.id).version,
            request_key=f'feedback-{i}', note=f'第{i}次练习自述'))
    first = feedback.list_feedback(db, detail.project.id)
    second = feedback.list_feedback(db, detail.project.id, first.next_before)
    assert first.total == 23 and len(first.items) == 20 and len(second.items) == 3
    assert len({r.id for r in first.items + second.items}) == 23
    assert db.scalar(select(func.count()).select_from(ResearchFeedback)) == 23
