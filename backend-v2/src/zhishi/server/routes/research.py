# ruff: noqa: B008
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from zhishi.domain.research import feedback, service, sources
from zhishi.domain.research.schemas import (
    AddSourceInput,
    ArchiveInput,
    ExtensionDraft,
    FeedbackCreate,
    FeedbackPage,
    FeedbackRead,
    GatherInput,
    GatherResult,
    MaterialInput,
    PlanDraft,
    PlanHistory,
    PlanRead,
    ProjectCreate,
    ProjectDetail,
    ProjectRead,
    ProjectUpdate,
    RevisionDraft,
    SourceRead,
    VersionInput,
)
from zhishi.server.deps import get_db
from zhishi.domain.research import watches
from zhishi.domain.research.watch_schemas import WatchRead, WatchRunRead, WatchUpdate

router = APIRouter(prefix='/api/research', tags=['research'])


@router.get('/projects/{project_id}/watch', response_model=WatchRead)
def read_watch(project_id: int, before: int | None = None, db: Session = Depends(get_db)):
    return call(watches.read, db, project_id, before)


@router.put('/projects/{project_id}/watch', response_model=WatchRead)
def configure_watch(project_id: int, payload: WatchUpdate, db: Session = Depends(get_db)):
    return call(watches.configure, db, project_id, payload)


@router.post('/projects/{project_id}/watch/run', response_model=WatchRunRead)
def run_watch(project_id: int, db: Session = Depends(get_db)):
    return call(watches.execute, db, project_id)


def call(fn, *args, **kwargs):
    from zhishi.domain.library.reading import MaterialConflict
    try:
        return fn(*args, **kwargs)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except service.ResearchConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except MaterialConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post('/projects', response_model=ProjectRead, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    return call(service.create_project, db, payload)


@router.get('/projects', response_model=list[ProjectRead])
def list_projects(archived: bool = False, db: Session = Depends(get_db)):
    return service.list_projects(db, archived=archived)


@router.get('/projects/{project_id}', response_model=ProjectDetail)
def detail(project_id: int, db: Session = Depends(get_db)):
    return call(service.detail, db, project_id)


@router.put('/projects/{project_id}', response_model=ProjectRead)
def update_project(project_id: int, payload: ProjectUpdate, db: Session = Depends(get_db)):
    return call(service.update_project, db, project_id, payload)


@router.post('/projects/{project_id}/archive', response_model=ProjectRead)
def archive(project_id: int, payload: ArchiveInput, db: Session = Depends(get_db)):
    return call(service.archive_project, db, project_id, payload.version, payload.archived)


@router.post('/projects/{project_id}/sources/gather', response_model=GatherResult)
def gather(project_id: int, payload: GatherInput, db: Session = Depends(get_db)):
    return call(sources.gather, db, project_id, payload)


@router.post('/projects/{project_id}/sources', response_model=SourceRead, status_code=201)
def add_source(project_id: int, payload: AddSourceInput, db: Session = Depends(get_db)):
    return call(sources.add_source, db, project_id, payload.url, payload.title, refresh=payload.refresh)


@router.post('/projects/{project_id}/materials', response_model=SourceRead, status_code=201)
def attach_material(project_id: int, payload: MaterialInput, request: Request, db: Session = Depends(get_db)):
    return call(sources.attach_material, db, project_id, payload.file_id, request.app.state.storage_root)


@router.post('/projects/{project_id}/sources/{source_id}/fetch', response_model=SourceRead)
def fetch_source(project_id: int, source_id: int, refresh: bool = False, db: Session = Depends(get_db)):
    return call(sources.fetch_source, db, project_id, source_id, refresh=refresh)


@router.post('/projects/{project_id}/plans', response_model=PlanRead, status_code=201)
def preview_plan(project_id: int, payload: PlanDraft, db: Session = Depends(get_db)):
    return call(service.preview_plan, db, project_id, payload)


@router.post('/projects/{project_id}/replan', response_model=PlanRead, status_code=201)
def preview_replan(project_id: int, payload: VersionInput, db: Session = Depends(get_db)):
    return call(service.preview_replan, db, project_id, payload.version)


@router.post('/projects/{project_id}/extensions', response_model=PlanRead, status_code=201)
def preview_extension(project_id: int, payload: ExtensionDraft, db: Session = Depends(get_db)):
    return call(service.preview_extension, db, project_id, payload)


@router.post('/projects/{project_id}/revisions', response_model=PlanRead, status_code=201)
def preview_revision(project_id: int, payload: RevisionDraft, db: Session = Depends(get_db)):
    return call(service.preview_revision, db, project_id, payload)


@router.get('/projects/{project_id}/plans', response_model=PlanHistory)
def plan_history(project_id: int, before: int | None = None, db: Session = Depends(get_db)):
    return call(service.plan_history, db, project_id, before)


@router.get('/projects/{project_id}/feedback', response_model=FeedbackPage)
def list_feedback(project_id: int, before: int | None = None, db: Session = Depends(get_db)):
    return call(feedback.list_feedback, db, project_id, before)


@router.post('/projects/{project_id}/feedback', response_model=FeedbackRead, status_code=201)
def record_feedback(project_id: int, payload: FeedbackCreate, db: Session = Depends(get_db)):
    return call(feedback.record, db, project_id, payload)


@router.post('/projects/{project_id}/feedback/{feedback_id}/withdraw', response_model=FeedbackRead)
def withdraw_feedback(project_id: int, feedback_id: int, payload: VersionInput, db: Session = Depends(get_db)):
    return call(feedback.withdraw, db, project_id, feedback_id, payload.version)


@router.get('/plans/{plan_id}', response_model=PlanRead)
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    return service.plan_read(call(service.get_plan, db, plan_id))


@router.post('/plans/{plan_id}/apply', response_model=PlanRead)
def apply_plan(plan_id: int, db: Session = Depends(get_db)):
    return call(service.apply_plan, db, plan_id)
