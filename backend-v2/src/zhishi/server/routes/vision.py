"""Global nonsecret vision binding. Mount ``router`` in server.app.

GET/PUT/DELETE /ai/vision. Server-level consent only: the user picks the MCP
server; which tool to call is the model's runtime choice via read_image.
PUT saves consent but makes no calls.
"""
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from zhishi.agent.attachments import (
    VISION_SETTING_KEY,
    VisionConfig,
    load_vision_config,
    server_fingerprint,
)
from zhishi.domain import settingsvc
from zhishi.domain.models import AppSetting, MCPServer
from zhishi.server.deps import get_db

router = APIRouter(prefix='/ai/vision', tags=['vision'])
Database = Annotated[Session, Depends(get_db)]


@router.get('', response_model=VisionConfig)
def get_vision(db: Database):
    try:
        return load_vision_config(db)[0]
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(409, '视觉配置无效，请重新保存') from None


@router.put('', response_model=VisionConfig)
def save_vision(body: VisionConfig, db: Database):
    fingerprint = None
    if body.server_id is not None:
        server = db.get(MCPServer, body.server_id)
        if server is None:
            raise HTTPException(404, 'MCP 服务器不存在')
        if server.transport not in ('http', 'stdio'):
            raise HTTPException(422, '不支持该 MCP 传输方式')
        if body.enabled and (not server.enabled or
                             server.transport == 'stdio' and not server.trusted):
            raise HTTPException(409, '请先启用并信任所选 MCP 服务器')
        fingerprint = server_fingerprint(server)
    payload = body.model_dump()
    payload['server_fingerprint'] = fingerprint
    settingsvc.set_setting(db, VISION_SETTING_KEY, json.dumps(payload, ensure_ascii=False))
    return body


@router.delete('', response_model=VisionConfig)
def clear_vision(db: Database):
    row = db.get(AppSetting, VISION_SETTING_KEY)
    if row is not None:
        db.delete(row)
        db.commit()
    return VisionConfig()
