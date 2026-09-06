"""Global nonsecret vision binding. Mount ``router`` in server.app.

GET/PUT/DELETE /ai/vision. Server/tool discovery uses existing /ai/mcp/servers
and /ai/mcp/servers/{sid}/tools endpoints. PUT saves consent but makes no calls.
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
    template_tokens,
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
        if 'image_path' in template_tokens(body.arguments) and not (
            server.transport == 'stdio' and server.trusted
        ):
            raise HTTPException(422, 'image_path 仅适用于受信任的本地 stdio 服务器')
        if body.enabled:
            if not server.enabled or server.transport == 'stdio' and not server.trusted:
                raise HTTPException(409, '请先启用并信任所选 MCP 服务器')
            if not server.auto_approve_readonly:
                raise HTTPException(409, '请先为该 MCP 服务器允许自动执行只读工具')
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
