import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel
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


# ---- 扫描件 OCR 模型配置（openai_compat 视觉/OCR 端点，如硅基流动 DeepSeek-OCR） ----

class OcrConfigOut(BaseModel):
    base_url: str = ''
    model: str = ''
    has_api_key: bool = False


class OcrConfigIn(BaseModel):
    base_url: str = ''
    model: str = ''
    pdf_mode: str = 'auto'          # 预留；当前仅 auto（只 OCR 扫描页）
    api_key: str | None = None      # None=保留现有；空串=清除


@router.get('/ocr', response_model=OcrConfigOut)
def get_ocr(db: Session = Depends(get_db)):
    from zhishi.agent.ocr import load_ocr_config
    cfg = load_ocr_config(db) or {}
    raw = _raw_ocr(db)
    return OcrConfigOut(base_url=raw.get('base_url', ''), model=raw.get('model', ''),
                        has_api_key=bool(cfg))


@router.put('/ocr', response_model=OcrConfigOut)
def put_ocr(body: OcrConfigIn, db: Session = Depends(get_db)):
    from zhishi.infra.secrets import delete_api_key, store_api_key
    from zhishi.agent.ocr import CONFIG_KEY, KEY_REF, load_ocr_config
    raw = _raw_ocr(db)
    raw['base_url'] = body.base_url.strip()
    raw['model'] = body.model.strip()
    raw['pdf_mode'] = 'auto'
    settingsvc.set_setting(db, CONFIG_KEY, json.dumps(raw, ensure_ascii=False))
    if body.api_key is not None:
        if body.api_key.strip():
            store_api_key(KEY_REF, body.api_key.strip())
        else:
            delete_api_key(KEY_REF)
    configured = load_ocr_config(db) is not None
    return OcrConfigOut(base_url=raw['base_url'], model=raw['model'], has_api_key=configured)


def _raw_ocr(db: Session) -> dict:
    from zhishi.agent.ocr import CONFIG_KEY
    try:
        return json.loads(settingsvc.get_setting(db, CONFIG_KEY, '') or '{}')
    except (ValueError, TypeError):
        return {}
