"""User-reported learning evidence, independent of task completion."""
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from zhishi.domain.models import ResearchFeedback, ResearchPlan, ResearchPlanFeedback, ResearchTask
from zhishi.domain.research import planning, service
from zhishi.domain.research.schemas import FeedbackCreate, FeedbackInput, FeedbackPage, FeedbackRead


def to_read(db: Session, row: ResearchFeedback) -> FeedbackRead:
    plans = list(db.scalars(select(ResearchPlanFeedback.plan_id).join(ResearchPlan).where(
        ResearchPlanFeedback.feedback_id == row.id, ResearchPlan.state == 'applied').order_by(ResearchPlan.id)))
    return FeedbackRead(**FeedbackInput.model_validate_json(row.payload_json).model_dump(),
        id=row.id, project_id=row.project_id, status=row.status, created_at=row.created_at,
        applied_plan_ids=plans)


def list_feedback(db: Session, project_id: int, before: int | None = None) -> FeedbackPage:
    service.get_project(db, project_id)
    if before is not None and before < 1:
        raise ValueError('反馈分页位置须大于0')
    query = select(ResearchFeedback).where(ResearchFeedback.project_id == project_id,
                                         ResearchFeedback.status == 'active')
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    if before is not None:
        query = query.where(ResearchFeedback.id < before)
    rows = list(db.scalars(query.order_by(ResearchFeedback.id.desc()).limit(21)))
    return FeedbackPage(items=[to_read(db, row) for row in rows[:20]], total=total,
                        next_before=rows[19].id if len(rows) > 20 else None)


def record(db: Session, project_id: int, payload: FeedbackCreate) -> FeedbackRead:
    encoded = planning.encoded(payload.model_dump(exclude={'version', 'request_key'}))

    def replay():
        old = db.scalar(select(ResearchFeedback).where(ResearchFeedback.request_key == payload.request_key))
        if old and (old.project_id != project_id or old.payload_json != encoded):
            raise service.ResearchConflict('同一反馈请求内容不同，请读取项目后使用新的请求编号', project_id)
        return to_read(db, old) if old else None

    existing = replay()
    if existing:
        return existing
    service.get_project(db, project_id, active=True)
    try:
        service._claim(db, project_id, payload.version)
        if payload.task_link_id:
            link = db.get(ResearchTask, payload.task_link_id)
            if not link or link.project_id != project_id:
                raise service.ResearchConflict('反馈关联的任务不属于本项目', project_id)
        row = ResearchFeedback(project_id=project_id, task_link_id=payload.task_link_id,
            request_key=payload.request_key, payload_json=encoded)
        db.add(row)
        db.commit()
    except (service.ResearchConflict, IntegrityError):
        db.rollback()
        existing = replay()
        if existing:
            return existing
        raise
    except Exception:
        db.rollback()
        raise
    return to_read(db, row)


def withdraw(db: Session, project_id: int, feedback_id: int, version: int) -> FeedbackRead:
    row = db.get(ResearchFeedback, feedback_id, populate_existing=True)
    if not row or row.project_id != project_id:
        raise LookupError('本项目反馈不存在')
    if row.status == 'withdrawn':
        return to_read(db, row)
    service.get_project(db, project_id, active=True)
    service._claim(db, project_id, version)
    row.status = 'withdrawn'
    db.commit()
    return to_read(db, row)


def validate(db: Session, project_id: int, ids: list[int]) -> None:
    for fid in ids:
        row = db.get(ResearchFeedback, fid, populate_existing=True)
        if not row or row.project_id != project_id or row.status != 'active':
            raise service.ResearchConflict('方案引用的反馈已撤回或不属于本项目，请重新读取', project_id)


def pending_difficulties(db: Session, project_id: int) -> list[int]:
    addressed = select(ResearchPlanFeedback.feedback_id).join(ResearchPlan).where(ResearchPlan.state == 'applied')
    rows = db.scalars(select(ResearchFeedback).where(ResearchFeedback.project_id == project_id,
        ResearchFeedback.status == 'active', ResearchFeedback.id.not_in(addressed)).order_by(ResearchFeedback.id))
    return [r.id for r in rows if FeedbackInput.model_validate_json(r.payload_json).difficulty in ('too_easy', 'too_hard')]
