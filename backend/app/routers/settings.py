from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import AppSettingsBatch
from app.services import app_setting_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def list_settings(db: Session = Depends(get_db)):
    return app_setting_service.list_settings(db)


@router.put("")
def update_settings(payload: AppSettingsBatch, db: Session = Depends(get_db)):
    return app_setting_service.update_settings(db, payload.settings)
