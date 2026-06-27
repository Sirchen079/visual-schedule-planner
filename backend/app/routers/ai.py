from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AIConfig, AIConversation, AIMessage
from app.schemas import (
    AIActionExecute,
    AIChatRequest,
    AIChatResponse,
    AIConfigCreate,
    AIConfigResponse,
    AIConfigUpdate,
    AIModelsRequest,
    AIModelsResponse,
    AIPendingActionResponse,
    AISkillCreate,
    AISkillImport,
    AISkillResponse,
    AISkillUpdate,
)
from app.services import (
    ai_action_service,
    ai_client,
    ai_config_service,
    ai_prompt_service,
    ai_skill_service,
    ai_tool_service,
)

router = APIRouter(prefix="/ai", tags=["ai"])


def sanitize_provider_error(exc: Exception) -> str:
    text = str(exc)
    text = re.sub(
        r"(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s,;\"'}]+",
        r"\1[已隐藏]",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"(x-api-key\s*[:=]\s*)[^\s,;\"'}]+",
        r"\1[已隐藏]",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"((?:api[_-]?key|token|secret|password)[\"']?\s*[:=]\s*[\"']?)[^\"',\s}]+",
        r"\1[已隐藏]",
        text,
        flags=re.I,
    )
    text = re.sub(r"\b(sk|ak|pk)-[A-Za-z0-9_-]{8,}\b", r"\1-[已隐藏]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300] if text else exc.__class__.__name__


def provider_failure_detail(operation: str, exc: Exception) -> str:
    return f"{operation}失败: {sanitize_provider_error(exc)}"


def pending_action_response(db: Session, action) -> AIPendingActionResponse:
    data = AIPendingActionResponse.model_validate(action)
    data.preview = ai_action_service.action_preview(db, action)
    return data


@router.get("/configs", response_model=list[AIConfigResponse])
def list_configs(db: Session = Depends(get_db)):
    return ai_config_service.list_configs(db)


@router.post(
    "/configs", response_model=AIConfigResponse, status_code=status.HTTP_201_CREATED
)
def create_config(payload: AIConfigCreate, db: Session = Depends(get_db)):
    return ai_config_service.create_config(db, payload)


@router.put("/configs/{config_id}", response_model=AIConfigResponse)
def update_config(
    config_id: int, payload: AIConfigUpdate, db: Session = Depends(get_db)
):
    config = ai_config_service.update_config(db, config_id, payload)
    if config is None:
        raise HTTPException(status_code=404, detail="AI 配置不存在")
    return config


@router.post("/configs/{config_id}/enable", response_model=AIConfigResponse)
def enable_config(config_id: int, db: Session = Depends(get_db)):
    config = ai_config_service.enable_config(db, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="AI 配置不存在")
    return config


@router.post("/configs/{config_id}/test")
async def test_config(config_id: int, db: Session = Depends(get_db)):
    config = db.get(AIConfig, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="AI 配置不存在")
    req = ai_client.build_provider_request(
        provider=config.provider,
        model=config.model,
        api_key=config.api_key,
        messages=[{"role": "user", "content": "请回复：连接成功"}],
        system_prompt="你是连接测试助手，只需要简短回复。",
        extra_headers=ai_config_service.headers_from_json(config.extra_headers),
        base_url=config.base_url,
        full_url=config.full_url,
        proxy_url=config.proxy_url,
    )
    try:
        await ai_client.call_provider(req)
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=provider_failure_detail("模型连接", exc)
        ) from exc
    return {"ok": True, "message": "模型连接测试成功"}


@router.post("/models", response_model=AIModelsResponse)
async def list_models(payload: AIModelsRequest, db: Session = Depends(get_db)):
    config = db.get(AIConfig, payload.config_id) if payload.config_id else None
    provider = payload.provider or (config.provider if config else None)
    api_key = payload.api_key or (config.api_key if config else None)
    base_url = (
        payload.base_url
        if payload.base_url is not None
        else config.base_url if config else None
    )
    full_url = (
        payload.full_url
        if payload.full_url is not None
        else config.full_url if config else None
    )
    proxy_url = (
        payload.proxy_url
        if payload.proxy_url is not None
        else config.proxy_url if config else None
    )
    extra_headers = (
        ai_config_service.merge_masked_headers(config, payload.extra_headers)
        if payload.extra_headers and config
        else payload.extra_headers
        if payload.extra_headers
        else ai_config_service.headers_from_json(config.extra_headers) if config else {}
    )
    if not provider or not api_key:
        raise HTTPException(status_code=400, detail="需要 provider 和 API key 才能获取模型列表")
    req = ai_client.build_models_request(
        provider=provider,
        api_key=api_key,
        extra_headers=extra_headers,
        base_url=base_url,
        full_url=full_url,
        proxy_url=proxy_url,
    )
    try:
        data = await ai_client.call_models(req)
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=provider_failure_detail("模型列表获取", exc)
        ) from exc
    return AIModelsResponse(models=ai_client.extract_model_ids(data))


@router.get("/skills", response_model=list[AISkillResponse])
def list_skills(db: Session = Depends(get_db)):
    return ai_skill_service.list_skills(db)


@router.post("/skills", response_model=AISkillResponse, status_code=status.HTTP_201_CREATED)
def create_skill(payload: AISkillCreate, db: Session = Depends(get_db)):
    return ai_skill_service.create_skill(db, payload)


@router.put("/skills/{skill_id}", response_model=AISkillResponse)
def update_skill(skill_id: int, payload: AISkillUpdate, db: Session = Depends(get_db)):
    skill = ai_skill_service.update_skill(db, skill_id, payload)
    if skill is None:
        raise HTTPException(status_code=404, detail="AI skill 不存在")
    return skill


@router.delete("/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(skill_id: int, db: Session = Depends(get_db)):
    if not ai_skill_service.delete_skill(db, skill_id):
        raise HTTPException(status_code=404, detail="AI skill 不存在")


@router.post("/skills/{skill_id}/enable", response_model=AISkillResponse)
def enable_skill(skill_id: int, db: Session = Depends(get_db)):
    skill = ai_skill_service.enable_skill(db, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="AI skill 不存在")
    return skill


@router.post("/skills/import", response_model=AISkillResponse, status_code=status.HTTP_201_CREATED)
def import_skill(payload: AISkillImport, db: Session = Depends(get_db)):
    try:
        return ai_skill_service.import_skill(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/actions/{action_id}/confirm")
def confirm_action(action_id: int, db: Session = Depends(get_db)):
    action, token, error = ai_action_service.confirm_action(db, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail=error)
    if error:
        raise HTTPException(status_code=409, detail=error)
    return {
        "action": pending_action_response(db, action),
        "confirm_token": token,
    }


@router.post("/actions/{action_id}/execute")
def execute_action(
    action_id: int, payload: AIActionExecute, db: Session = Depends(get_db)
):
    ok, message = ai_action_service.execute_action(
        db, action_id, payload.confirm_token
    )
    if not ok and "token" in message:
        raise HTTPException(status_code=403, detail=message)
    if not ok:
        raise HTTPException(status_code=409, detail=message)
    return {"ok": True, "message": message}


@router.post("/chat", response_model=AIChatResponse)
async def chat(payload: AIChatRequest, db: Session = Depends(get_db)):
    config = ai_config_service.get_enabled_config(db)
    if config is None:
        raise HTTPException(status_code=400, detail="未启用 AI 配置")

    conversation = (
        db.get(AIConversation, payload.conversation_id)
        if payload.conversation_id
        else None
    )
    if conversation is None:
        conversation = AIConversation(title=payload.message[:60] or "新的对话")
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    user_msg = AIMessage(
        conversation_id=conversation.id, role="user", content=payload.message
    )
    db.add(user_msg)
    db.commit()

    history = (
        db.query(AIMessage)
        .filter(AIMessage.conversation_id == conversation.id)
        .order_by(AIMessage.id)
        .all()
    )
    messages = [
        {"role": m.role, "content": m.content}
        for m in history
        if m.role in {"user", "assistant"}
    ][-20:]
    system_prompt = (
        ai_prompt_service.build_system_prompt(db, config)
        + "\n\n"
        + ai_prompt_service.build_local_context(db)
    )
    req = ai_client.build_provider_request(
        provider=config.provider,
        model=config.model,
        api_key=config.api_key,
        messages=messages,
        system_prompt=system_prompt,
        extra_headers=ai_config_service.headers_from_json(config.extra_headers),
        base_url=config.base_url,
        full_url=config.full_url,
        proxy_url=config.proxy_url,
    )
    try:
        raw = await ai_client.call_provider(req)
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=provider_failure_detail("模型请求", exc)
        ) from exc

    text = ai_client.extract_text(config.provider, raw)
    plan = ai_client.parse_assistant_plan(text)
    tool_results = []
    for item in plan["tools"]:
        result = ai_tool_service.execute_tool(
            db, item.get("name", ""), dict(item.get("args", {}))
        )
        tool_results.append({"tool": item.get("name", ""), "result": result})

    pending = []
    for item in plan["dangerous_actions"]:
        action_type = item.get("action_type", "")
        if not ai_action_service.is_supported_action_type(action_type):
            continue
        action = ai_action_service.create_pending_action(
            db,
            conversation.id,
            action_type,
            dict(item.get("payload", {})),
            item.get("summary", "危险操作待确认"),
        )
        pending.append(action)

    reply = plan["reply"] or text
    assistant_msg = AIMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=reply,
        meta=json.dumps(
            {
                "tool_results": tool_results,
                "pending_action_ids": [action.id for action in pending],
            },
            ensure_ascii=False,
        ),
    )
    db.add(assistant_msg)
    db.commit()

    return AIChatResponse(
        conversation_id=conversation.id,
        assistant_name=config.assistant_name or "知时助手",
        reply=reply,
        tool_results=tool_results,
        pending_actions=[
            pending_action_response(db, action) for action in pending
        ],
    )
