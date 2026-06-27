from __future__ import annotations

import json
import re
from datetime import datetime

from fastapi import APIRouter, Depends, File as UploadFileParam, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AIConfig, AIConversation, AIMessage, AIPendingAction
from app.schemas import (
    AIActionExecute,
    AIChatAttachmentResponse,
    AIChatRequest,
    AIChatResponse,
    AIConversationDetailResponse,
    AIConversationMessageResponse,
    AIConversationSummaryResponse,
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
    ai_attachment_service,
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


def message_meta(message: AIMessage) -> dict:
    try:
        data = json.loads(message.meta or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def conversation_summary(conversation: AIConversation) -> AIConversationSummaryResponse:
    messages = list(conversation.messages or [])
    last = next((message for message in reversed(messages) if message.content), None)
    updated_at = conversation.updated_at or conversation.created_at
    return AIConversationSummaryResponse(
        id=conversation.id,
        title=conversation.title,
        last_message=(last.content[:120] if last else ""),
        message_count=len(messages),
        created_at=conversation.created_at,
        updated_at=updated_at,
    )


def conversation_message_response(db: Session, message: AIMessage) -> AIConversationMessageResponse:
    meta = message_meta(message)
    pending = []
    for action_id in meta.get("pending_action_ids", []):
        action = db.get(AIPendingAction, action_id)
        if action is not None:
            pending.append(pending_action_response(db, action))
    return AIConversationMessageResponse(
        id=message.id,
        role=message.role,
        content=message.content,
        tool_results=meta.get("tool_results", []) if isinstance(meta.get("tool_results", []), list) else [],
        pending_actions=pending,
        created_at=message.created_at,
    )


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


@router.post(
    "/attachments",
    response_model=AIChatAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_chat_attachment(file: UploadFile = UploadFileParam(...)):
    return ai_attachment_service.save_upload(file)


@router.get("/conversations", response_model=list[AIConversationSummaryResponse])
def list_conversations(
    limit: int = Query(50, ge=1, le=50),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AIConversation)
        .order_by(AIConversation.updated_at.desc(), AIConversation.id.desc())
        .limit(limit)
        .all()
    )
    return [conversation_summary(conversation) for conversation in rows]


@router.get("/conversations/{conversation_id}", response_model=AIConversationDetailResponse)
def get_conversation(conversation_id: int, db: Session = Depends(get_db)):
    conversation = db.get(AIConversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="AI 会话不存在")
    summary = conversation_summary(conversation)
    return AIConversationDetailResponse(
        **summary.model_dump(),
        messages=[
            conversation_message_response(db, message)
            for message in conversation.messages
            if message.role in {"user", "assistant", "system"}
        ],
    )


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

    attachment_ids = [attachment.id for attachment in payload.attachments]
    model_attachments = ai_attachment_service.build_model_attachments(attachment_ids)
    user_text = payload.message.strip() or "请分析这些附件。"
    stored_user_content = user_text
    if model_attachments:
        attachment_lines = [
            f"- {item.get('filename')} ({item.get('mime_type')}, 附件 ID: {item.get('id')})"
            for item in model_attachments
        ]
        stored_user_content = f"{user_text}\n\n[对话附件]\n" + "\n".join(attachment_lines)

    conversation = (
        db.get(AIConversation, payload.conversation_id)
        if payload.conversation_id
        else None
    )
    if conversation is None:
        conversation = AIConversation(title=user_text[:60] or "新的对话")
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    user_msg = AIMessage(
        conversation_id=conversation.id,
        role="user",
        content=stored_user_content,
        meta=json.dumps({"attachment_ids": attachment_ids}, ensure_ascii=False),
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
    if model_attachments and messages:
        messages[-1] = {
            "role": "user",
            "content": user_text,
            "attachments": model_attachments,
        }
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
    conversation.updated_at = datetime.now()
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
