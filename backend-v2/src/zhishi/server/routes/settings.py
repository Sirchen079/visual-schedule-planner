from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from zhishi.domain import settingsvc
from zhishi.domain.models import AppSetting
from zhishi.server.deps import get_db

router = APIRouter(prefix="/api/settings", tags=["settings"])


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
