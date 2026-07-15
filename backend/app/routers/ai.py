from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

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
    AIReportGenerateRequest,
    AIReportResponse,
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
    ai_harness_service,
    ai_prompt_service,
    ai_report_service,
    ai_skill_service,
    ai_tool_service,
)

router = APIRouter(prefix="/ai", tags=["ai"])
AGENT_MAX_STEPS = 5
AGENT_OBSERVATION_CHAR_LIMIT = 12000
AGENT_TOOL_RETRY_LIMIT = 2


@dataclass
class AgentRunResult:
    final_text: str
    final_plan: dict
    tool_results: list[dict]
    run_summary: dict
    reached_limit: bool = False
    stopped_for_repeat: bool = False
    stop_message: str = ""


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


def tool_signature(item: dict) -> str:
    return json.dumps(
        {"name": item.get("name", ""), "args": dict(item.get("args", {}))},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )


def execute_plan_tools(
    db: Session,
    plan: dict,
    skip_successful_signatures: set[str] | None = None,
) -> list[dict]:
    skip_successful_signatures = skip_successful_signatures or set()
    tool_results = []
    for item in plan["tools"]:
        if not isinstance(item, dict):
            tool_results.append(
                {"tool": "", "args": {}, "result": {"ok": False, "error": "工具调用必须是对象"}}
            )
            continue
        name = item.get("name", "")
        raw_args = item.get("args", {})
        if raw_args is None:
            raw_args = {}
        if not isinstance(raw_args, dict):
            tool_results.append(
                {
                    "tool": str(name),
                    "args": {},
                    "result": {"ok": False, "error": "工具 args 必须是对象"},
                }
            )
            continue
        args = dict(raw_args)
        signature = tool_signature(item)
        if signature in skip_successful_signatures:
            result = {"ok": True, "skipped": True, "message": "已跳过重复成功工具"}
        else:
            result = ai_tool_service.execute_tool(db, name, args)
        tool_results.append({"tool": name, "args": args, "result": result})
    return tool_results


def successful_tool_signatures(tool_results: list[dict]) -> set[str]:
    signatures = set()
    for item in tool_results:
        result = item.get("result")
        if isinstance(result, dict) and result.get("ok") is True and not result.get("skipped"):
            signatures.add(
                json.dumps(
                    {"name": item.get("tool", ""), "args": item.get("args", {})},
                    sort_keys=True,
                    ensure_ascii=False,
                    default=str,
                )
            )
    return signatures


def build_agent_observation_message(
    user_text: str,
    plan: dict,
    step_results: list[dict],
    step: int,
) -> str:
    payload = json.dumps(step_results, ensure_ascii=False, default=str)
    if len(payload) > AGENT_OBSERVATION_CHAR_LIMIT:
        payload = payload[:AGENT_OBSERVATION_CHAR_LIMIT] + "\n...[工具结果过长，已截断]"
    return (
        f"连续工作第 {step} 轮工具执行结果如下。请像 coding agent 一样基于观察继续推进。\n"
        f"本轮 harness 状态：step={step}, max_steps={AGENT_MAX_STEPS}, tool_retry_limit={AGENT_TOOL_RETRY_LIMIT}。\n"
        "要求：\n"
        "- 已成功完成的工具不要重复执行。\n"
        "- 如果工具失败，请修正参数后重试；无法修正时，在 reply 中说明需要用户补充什么。\n"
        "- 如果目标已经完成，返回最终 reply，tools 和 dangerous_actions 置为空数组。\n"
        "- 如果需要用户确认危险操作，放入 dangerous_actions 后停止继续执行。\n\n"
        f"用户原始请求：{user_text}\n\n"
        f"上一轮计划：{json.dumps(plan, ensure_ascii=False, default=str)}\n\n"
        f"工具执行结果：{payload}"
    )


def compact_attachments_for_followup(messages: list[dict]) -> list[dict]:
    compacted = []
    for message in messages:
        attachments = message.get("attachments") or []
        if not attachments:
            compacted.append(message)
            continue
        lines = [
            (
                f"- {item.get('filename')} | 附件 ID:{item.get('id')} | "
                f"类型:{item.get('mime_type') or '未知'} | 大小:{item.get('size') or 0} bytes"
            )
            for item in attachments
        ]
        compacted.append(
            {
                "role": message.get("role", "user"),
                "content": (
                    f"{message.get('content', '')}\n\n"
                    "[附件已在上一轮完整发送，本轮仅保留引用]\n"
                    + "\n".join(lines)
                ).strip(),
            }
        )
    return compacted


def has_valid_dangerous_actions(plan: dict) -> bool:
    return any(isinstance(item, dict) for item in plan.get("dangerous_actions", []))


def build_chat_provider_request(
    db: Session,
    config: AIConfig,
    messages: list[dict],
) -> ai_client.ProviderRequest:
    system_prompt = (
        ai_prompt_service.build_system_prompt(db, config)
        + "\n\n"
        + ai_prompt_service.build_local_context(db)
    )
    return ai_client.build_provider_request(
        provider=config.provider,
        model=config.model,
        api_key=config.api_key,
        messages=messages,
        system_prompt=system_prompt,
        extra_headers=ai_config_service.headers_from_json(config.extra_headers),
        base_url=config.base_url,
        full_url=config.full_url,
        proxy_url=config.proxy_url,
        native_web_search_enabled=bool(
            config.native_web_search_enabled or config.search_enhancement_enabled
        ),
        native_web_search_options=ai_config_service.options_from_json(
            config.native_web_search_options
        ),
    )


async def run_agent_loop(
    db: Session,
    config: AIConfig,
    messages: list[dict],
    user_text: str,
) -> AgentRunResult:
    run_id = uuid4().hex
    started_at = datetime.now()
    working_messages = list(messages)
    tool_results: list[dict] = []
    steps: list[dict] = []
    final_text = ""
    final_plan = {"reply": "", "tools": [], "dangerous_actions": []}
    reached_limit = False
    stopped_for_repeat = False
    done_reason = "unknown"
    stop_message = ""

    for step in range(1, AGENT_MAX_STEPS + 1):
        req = build_chat_provider_request(db, config, working_messages)
        try:
            raw = await ai_client.call_provider(req)
        except Exception as exc:
            if step == 1:
                raise
            provider_error = provider_failure_detail(f"连续工作第 {step} 轮模型请求", exc)
            tool_results.append(
                {
                    "tool": "ai_agent",
                    "args": {"step": step},
                    "result": {"ok": False, "error": provider_error},
                }
            )
            done_reason = "provider_error"
            stop_message = provider_error
            break

        final_text = ai_client.extract_text(config.provider, raw)
        final_plan = ai_client.parse_assistant_plan(final_text)
        if has_valid_dangerous_actions(final_plan):
            steps.append(
                {
                    "step": step,
                    "reply": final_plan.get("reply", ""),
                    "plan": final_plan.get("plan", {}),
                    "tools": [],
                    "dangerous_actions": final_plan.get("dangerous_actions", []),
                    "observations": [],
                    "done": bool(final_plan.get("done", False)),
                }
            )
            done_reason = "pending_confirmation"
            break
        step_results = execute_plan_tools(
            db, final_plan, successful_tool_signatures(tool_results)
        )
        tool_results.extend(step_results)
        steps.append(
            {
                "step": step,
                "reply": final_plan.get("reply", ""),
                "plan": final_plan.get("plan", {}),
                "tools": final_plan.get("tools", []),
                "dangerous_actions": final_plan.get("dangerous_actions", []),
                "observations": ai_harness_service.step_observations(step_results),
                "done": bool(final_plan.get("done", False)),
            }
        )

        if bool(final_plan.get("done", False)):
            done_reason = "model_done"
            break
        if final_plan["dangerous_actions"]:
            done_reason = "pending_confirmation"
            break
        if not final_plan["tools"]:
            done_reason = "no_tools"
            break
        if step_results and all(
            isinstance(item.get("result"), dict) and item["result"].get("skipped")
            for item in step_results
        ):
            stopped_for_repeat = True
            done_reason = "no_progress"
            break
        retry_message = ai_harness_service.failed_retry_budget_message(
            ai_harness_service.failed_tool_signatures(tool_results),
            tool_results,
            AGENT_TOOL_RETRY_LIMIT,
        )
        if retry_message:
            done_reason = "retry_budget_exhausted"
            stop_message = retry_message
            break
        if step >= AGENT_MAX_STEPS:
            reached_limit = True
            done_reason = "max_steps"
            break

        working_messages = [
            *compact_attachments_for_followup(working_messages),
            {"role": "assistant", "content": final_text},
            {
                "role": "user",
                "content": build_agent_observation_message(
                    user_text, final_plan, step_results, step
                ),
            },
        ]

    return AgentRunResult(
        final_text=final_text,
        final_plan=final_plan,
        tool_results=tool_results,
        run_summary=ai_harness_service.build_run_summary(
            run_id=run_id,
            objective=user_text,
            started_at=started_at,
            steps=steps,
            final_plan=final_plan,
            tool_results=tool_results,
            done_reason=done_reason,
            stop_message=stop_message,
            max_steps=AGENT_MAX_STEPS,
            retry_limit=AGENT_TOOL_RETRY_LIMIT,
        ),
        reached_limit=reached_limit,
        stopped_for_repeat=stopped_for_repeat,
        stop_message=stop_message,
    )


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
        native_web_search_enabled=bool(
            config.native_web_search_enabled or config.search_enhancement_enabled
        ),
        native_web_search_options=ai_config_service.options_from_json(
            config.native_web_search_options
        ),
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
    try:
        agent_run = await run_agent_loop(db, config, messages, user_text)
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=provider_failure_detail("模型请求", exc)
        ) from exc

    final_plan = agent_run.final_plan
    final_text = agent_run.final_text
    tool_results = agent_run.tool_results

    pending = []
    for item in final_plan["dangerous_actions"]:
        if not isinstance(item, dict):
            continue
        action_type = item.get("action_type", "")
        if not ai_action_service.is_supported_action_type(action_type):
            continue
        payload_data = item.get("payload", {})
        if payload_data is None:
            payload_data = {}
        if not isinstance(payload_data, dict):
            continue
        action = ai_action_service.create_pending_action(
            db,
            conversation.id,
            action_type,
            dict(payload_data),
            item.get("summary", "危险操作待确认"),
        )
        pending.append(action)

    reply = final_plan["reply"] or final_text
    agent_failed = next(
        (
            item["result"]["error"]
            for item in tool_results
            if item.get("tool") == "ai_agent"
            and isinstance(item.get("result"), dict)
            and item["result"].get("error")
        ),
        None,
    )
    if agent_failed:
        reply = f"{reply}\n\n连续工作中断：{agent_failed}"
    if agent_run.reached_limit:
        reply = f"{reply}\n\n已达到连续工作轮次上限（{AGENT_MAX_STEPS} 轮），请继续发消息让我接着处理。"
    if agent_run.stop_message and agent_run.stop_message not in reply:
        reply = f"{reply}\n\n{agent_run.stop_message}"
    assistant_msg = AIMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=reply,
        meta=json.dumps(
            {
                "tool_results": tool_results,
                "pending_action_ids": [action.id for action in pending],
                "agent_run": agent_run.run_summary,
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


# ---- AI 日报/周报 ----
@router.post("/reports/generate", response_model=AIReportResponse)
async def generate_report(
    payload: AIReportGenerateRequest, db: Session = Depends(get_db)
):
    config = ai_config_service.get_enabled_config(db)
    if config is None:
        raise HTTPException(status_code=400, detail="未启用 AI 配置")
    try:
        return await ai_report_service.generate_report(
            db, config, payload.report_type, payload.target_date
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=provider_failure_detail("生成报告", exc)
        ) from exc


@router.get("/reports", response_model=list[AIReportResponse])
def list_reports(
    report_type: str | None = Query(default=None), db: Session = Depends(get_db)
):
    return ai_report_service.list_reports(db, report_type)


@router.get("/reports/{report_id}", response_model=AIReportResponse)
def get_report(report_id: int, db: Session = Depends(get_db)):
    report = ai_report_service.get_report(db, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    return report


@router.delete("/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(report_id: int, db: Session = Depends(get_db)):
    if not ai_report_service.delete_report(db, report_id):
        raise HTTPException(status_code=404, detail="报告不存在")
