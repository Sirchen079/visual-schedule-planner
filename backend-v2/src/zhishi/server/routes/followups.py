# ruff: noqa: B008
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from zhishi.domain import followups, settingsvc
from zhishi.domain.followup_schemas import (
    FollowupCheck,
    FollowupPreferences,
    FollowupRead,
    FollowupResponse,
    FollowupStatus,
)
from zhishi.domain.models import SecretaryFollowup
from zhishi.domain.research import service
from zhishi.domain.research.schemas import VersionInput
from zhishi.server.deps import get_db

router = APIRouter(prefix='/api/followups', tags=['followups'])


to_read = followups.to_read


def call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except LookupError as exc:
        raise HTTPException(404,str(exc)) from exc
    except (followups.FollowupConflict, service.ResearchConflict) as exc:
        raise HTTPException(409,str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc


@router.get('', response_model=list[FollowupRead])
def list_followups(project_id: int | None = None, db: Session = Depends(get_db)):
    query = select(SecretaryFollowup).order_by(SecretaryFollowup.updated_at.desc(), SecretaryFollowup.id.desc()).limit(50)
    if project_id is not None:
        query = query.where(SecretaryFollowup.project_id == project_id)
    return [to_read(db,row) for row in db.scalars(query)]


@router.get('/status', response_model=FollowupStatus)
def status(db: Session = Depends(get_db)):
    try:
        last_scan = json.loads(settingsvc.get_setting(db,'followup_last_scan','null'))
    except ValueError:
        last_scan = None
    return FollowupStatus(enabled=settingsvc.feature_enabled(db,'feature_followup_enabled'),
        autopilot_enabled=settingsvc.feature_enabled(db,'feature_autopilot_enabled'),
        autonomy=settingsvc.get_setting(db,'agent_autonomy','standard'),
        last_scan=last_scan if isinstance(last_scan,dict) else None)


@router.put('/preferences', response_model=FollowupStatus)
def preferences(body: FollowupPreferences, db: Session = Depends(get_db)):
    settingsvc.set_setting(db,'feature_followup_enabled','true' if body.enabled else 'false')
    return status(db)


@router.post('/check', response_model=FollowupRead | None)
def check(body: FollowupCheck, db: Session = Depends(get_db)):
    row = call(followups.check_project,db,body.project_id)
    return to_read(db,row,include_plan=True) if row else None


@router.get('/{followup_id}', response_model=FollowupRead)
def get_followup(followup_id: int, db: Session = Depends(get_db)):
    return to_read(db,call(followups.get,db,followup_id),include_plan=True)


@router.post('/{followup_id}/apply', response_model=FollowupRead)
def apply(followup_id: int, body: VersionInput, db: Session = Depends(get_db)):
    return to_read(db,call(followups.apply,db,followup_id,body.version),include_plan=True)


@router.post('/{followup_id}/respond', response_model=FollowupRead)
def respond(followup_id: int, body: FollowupResponse, db: Session = Depends(get_db)):
    return to_read(db,call(followups.respond,db,followup_id,body.version,snooze_until=body.snooze_until))
