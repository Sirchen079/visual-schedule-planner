from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from zhishi.domain import onboarding, settingsvc
from zhishi.domain.models import AppSetting
from zhishi.server.deps import get_db

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get('/onboarding', response_model=onboarding.OnboardingState)
def get_onboarding(db: Session = Depends(get_db)):
    return onboarding.read(db)


@router.post('/onboarding', response_model=onboarding.OnboardingState)
def finish_onboarding(body: onboarding.OnboardingFinish, db: Session = Depends(get_db)):
    return onboarding.finish(db, body.outcome)


@router.get("", response_model=dict[str, str])
def get_settings(db: Session = Depends(get_db)):
    merged = dict(settingsvc.DEFAULTS)
    for row in db.scalars(select(AppSetting)):
        merged[row.key] = row.value
    return merged


@router.put("", response_model=dict[str, str])
def put_settings(body: dict, db: Session = Depends(get_db)):
    items = body.get("settings") or {}
    for key, value in items.items():
        settingsvc.set_setting(db, str(key), str(value))
    return get_settings(db)
