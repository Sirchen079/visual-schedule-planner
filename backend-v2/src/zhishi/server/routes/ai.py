# src/zhishi/server/routes/ai.py
"""AI 端点：会话 CRUD / 配置 CRUD / SSE 流 / 审批 / 取消。
SSE 生成器：runtime 事件进 asyncio.Queue，消费端 wait_for 超时 5s → yield heartbeat。"""
from __future__ import annotations
import asyncio
import json
import uuid
from typing import Literal
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from zhishi.agent.permissions import IRREVOCABLE_TOOLS
from zhishi.agent.providers import build_model  # 测试 monkeypatch 锚点
from zhishi.agent.providers import ReasoningEffort, validate_reasoning_effort
from zhishi.agent.runtime import AgentRuntime
from zhishi.adapters.model_catalog import ModelCatalogRequest, ModelCatalogResponse
from zhishi.domain.models import AIConfig, AIConversation, AIMessage


class EventStreamResponse(StreamingResponse):
    """SSE 响应（OpenAPI 媒体类型显式声明为 text/event-stream，替代自动标注的 json）。"""
    media_type = "text/event-stream"


class ActionResolveOut(BaseModel):
    """审批/计划结案端点的统一返回体（re #013 minor：typed schema）。
    re #023 建议③：ready_to_resume=该 action 所属 run 批次内已无 pending
    （全部 confirmed/rejected/executed）——前端只在 ready 后才开 resume 流。"""
    ok: bool = True
    resume: str = ""
    ready_to_resume: bool = False


class EnableOut(BaseModel):
    """启用/切换类端点的统一回包（re #038：McpEnableResult 手写收敛依据）。"""
    ok: bool = True
    enabled: bool | None = None


class CreatedOut(BaseModel):
    """创建类端点的最小回包：只回新行 id，调用方随后重拉列表（re #047）。"""
    id: int


class AttachmentOut(BaseModel):
    """对话附件上传回包（re #048）：file_id 供聊天 attachment_ids 引用。"""
    file_id: int
    name: str
    kind: str
    parse_status: str


class ConversationOut(BaseModel):
    """会话列表项（re #048）：updated_at 为 ISO 串。"""
    id: int
    title: str
    updated_at: str


class MessageOut(BaseModel):
    """会话消息项（re #048）：display 为展示元数据对象（{"text": ...}）。"""
    id: int
    role: str
    display: dict
    created_at: str


class CancelOut(BaseModel):
    """运行取消回包（re #048）：无该 run 令牌时 ok=false。"""
    ok: bool


class ConfigOut(BaseModel):
    """AI 配置列表项（re #047：前端 AiConfigInfo 手写收敛依据；api_key 敏感永不回显）。"""
    id: int
    name: str
    provider_kind: str
    model: str
    base_url: str | None = None
    enabled: bool
    context_window: int | None = None
    max_output_tokens: int | None = None
    reasoning_effort: ReasoningEffort | None = None
    input_modalities: list[Literal['text', 'image', 'audio', 'video']] = ['text']
    has_api_key: bool = False
    request_limit: int = 30
    price_input: float = 0.0
    price_output: float = 0.0


class SkillOut(BaseModel):
    """AI 技能列表项（re #047：前端 SkillInfo 手写收敛依据）。"""
    id: int
    name: str
    description: str
    enabled: bool
    is_builtin: bool


class ToolGrantOut(BaseModel):
    """「始终允许」规则（re #019：可审计、可撤销）。"""
    id: int
    tool_name: str
    arg_pattern: str
    created_at: str


class PlanRejectOut(BaseModel):
    """计划拒绝：无可续跑流，不提供 resume（re #016 minor）。"""
    ok: bool = True


class ResumeBlockedPending(BaseModel):
    """一条未决审批卡的定位信息。"""
    action_id: int
    tool_name: str


class ResumeBlockedOut(BaseModel):
    """resume 拒绝体（re #020 k3 major）：本轮仍有未决审批卡。
    前端按 pending 清单提示用户逐张批准/拒绝后再续跑。
    re #023④：consumed=true 表示该轮审批批次已被 resume 消费（confirmed 已转
    executed，源 run 已记 resumed_by_runs）——重复 resume 幂等拒绝，不会重复回填。"""
    pending: list[ResumeBlockedPending]
    consumed: bool = False
    message: str = ""
from zhishi.server.deps import get_db

router = APIRouter(prefix="/ai", tags=["ai"])


class ChatBody(BaseModel):
    message: str
    research_project_id: int | None = Field(default=None, gt=0)
    conversation_id: int | None = None
    attachment_ids: list[int] = []          # 对话附件：解析文本注入模型输入
    plan_mode: bool = False                 # 计划模式：只读工具 + propose_plan


@router.post("/attachments", status_code=201, response_model=AttachmentOut)
def upload_attachment(request: Request, file: UploadFile = File(...)):
    """上传对话附件：落盘 + 立即解析缓存（extracted_text）。
    返回 file_id 供聊天时以 attachment_ids 引用；image 落 needs_vision。"""
    app = request.app
    from zhishi.domain.library import service as ls
    with app.state.session_factory() as db:
        row = ls.save_upload(db, storage_root=app.state.storage_root, upload=file,
                             notes="对话附件")
        from zhishi.agent.attachments import detect_media
        kind = detect_media(row)
        if kind in ('audio', 'video'):
            row.parse_status = 'needs_media'
            db.commit()
        else:
            try:
                doc = ls.ensure_parsed(db, row, storage_root=app.state.storage_root)
                kind = doc.kind
            except ValueError:
                kind = 'failed'
    return {"file_id": row.id, "name": row.original_name,
            "kind": kind, "parse_status": row.parse_status}


def _enabled_config(db: Session) -> AIConfig:
    cfg = db.scalar(select(AIConfig).where(AIConfig.enabled.is_(True)))
    if cfg is None:
        raise HTTPException(400, "尚未启用任何 AI 配置，请先在设置中添加并启用")
    return cfg


def _frame(event: dict) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _with_close(aiter, db):
    """流结束（含异常/取消）后关闭覆盖整个 SSE 生命周期的 session。"""
    try:
        async for event in aiter:
            yield event
    finally:
        db.close()


async def _stream_response(event_aiter, app, run_id: str,
                           conversation_id: int | None) -> StreamingResponse:
    """chat 与 resume 共用的 SSE 生成器：心跳/并发锁/清理一致。"""
    queue: asyncio.Queue = asyncio.Queue()
    detached = False

    async def _drive():
        try:
            async for event in event_aiter:
                if not detached:
                    await queue.put(event)
        except Exception as exc:
            if not detached:
                await queue.put({"type": "run_error", "run_id": run_id,
                                 "message": str(exc)[:500], "retryable": False, "v": 1})
        finally:
            # Release only after the runtime and its already-started tools have
            # settled. A disconnected browser does not own the backend lifetime.
            try:
                with app.state.session_factory() as cleanup_db:
                    from zhishi.agent import session_store
                    from zhishi.domain.models import AIRun
                    row = cleanup_db.get(AIRun,run_id)
                    if row is not None and row.status == 'running':
                        session_store.interrupt_run(cleanup_db,row,'stream_interrupted')
                        cleanup_db.commit()
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Failed to finalize run %s',run_id)
            finally:
                _release_run_slot(app, run_id, conversation_id)
                await queue.put(None)

    task = asyncio.create_task(_drive())
    if not hasattr(app.state, 'run_tasks'):
        app.state.run_tasks = set()
    app.state.run_tasks.add(task)
    task.add_done_callback(app.state.run_tasks.discard)

    async def gen():
        nonlocal detached
        started = asyncio.get_event_loop().time()
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=5.0)
                except asyncio.TimeoutError:
                    elapsed = int((asyncio.get_event_loop().time() - started) * 1000)
                    yield _frame({"type": "heartbeat", "v": 1, "elapsed_ms": elapsed,
                                  "stage": "running", "last_event_age_ms": 5000})
                    continue
                if event is None:
                    break
                yield _frame(event)
        finally:
            detached = True
            token = app.state.cancel_tokens.get(run_id)
            if not task.done() and token is not None:
                token.cancel()

    return EventStreamResponse(gen(), media_type="text/event-stream")


def _raw_conversation_history(db: Session, cid: int):
    from pydantic_ai.messages import ModelMessagesTypeAdapter
    last = db.scalars(select(AIMessage).where(
        AIMessage.conversation_id == cid,
        AIMessage.history_json != "[]").order_by(AIMessage.id.desc())).first()
    return ModelMessagesTypeAdapter.validate_json(last.history_json) if last else None


def load_conversation_history(db: Session, cid: int, config: AIConfig | None = None):
    """取会话最近一条带 history 的 assistant 消息 → ModelMessage 列表。
    config 给定时先做摘要压缩（清账 11：轮数超 compaction_threshold → 最旧一半
    轮次折叠为【会话摘要】对，结果持久化 meta_json.summary 供重放优先注入；
    模型失败降级原样），再轮边界硬截断兜底。
    chat 续轮与审批恢复共用；无历史时返回 None（新会话首轮）。
    同步入口；异步路由必须使用 _load_conversation_history_async，不能把请求 Session 交给线程。"""
    messages = _raw_conversation_history(db, cid)
    if messages is None:
        return None
    if config is not None:
        messages = _compact_history(db, cid, config, messages)
    # A failed summary must not become a successful, permanently shortened turn.
    # The complete outgoing request is checked by the runtime after preparation.
    return messages


def _conversation_meta(conv) -> dict:
    try:
        meta = json.loads(conv.meta_json or "{}")
    except (ValueError, TypeError):
        return {}
    return meta if isinstance(meta, dict) else {}


def _save_compaction(db: Session, cid: int, summary, fingerprint, history=None) -> None:
    if summary is None:
        return
    # 摘要等待期间可能更新计划等 meta 字段，重新读取并只合并摘要键。
    conv = db.get(AIConversation, cid, populate_existing=True)
    if conv is None:
        return
    meta = _conversation_meta(conv)
    if summary != meta.get("summary") or fingerprint != meta.get("summary_fingerprint"):
        if history is not None and fingerprint:
            from zhishi.agent.session_store import archive_compaction
            archive_compaction(db, cid, history, summary, fingerprint)
        meta["summary"] = summary
        meta["summary_fingerprint"] = fingerprint
        conv.meta_json = json.dumps(meta, ensure_ascii=False)
        db.commit()


async def _load_conversation_history_async(db: Session, cid: int, config):
    """线程只接收普通值做摘要；取消后不再写库，Session 始终留在请求线程。"""
    from types import SimpleNamespace
    from zhishi.agent import compaction
    messages = _raw_conversation_history(db, cid)
    if messages is None:
        return None
    threshold = compaction.compaction_threshold(db)
    timeout = compaction.compaction_timeout(db)
    conv = db.get(AIConversation, cid)
    if conv is not None:
        meta = _conversation_meta(conv)
        original = list(messages)
        # 不能把 SQLAlchemy 实体交给晚到线程，以免过期属性触发数据库懒加载。
        snapshot = SimpleNamespace(**{key: getattr(config, key) for key in (
            "api_key_ref", "name", "provider_kind", "base_url", "model",
            "context_window", "max_output_tokens", "input_modalities_json", "reasoning_effort")})
        messages, summary, fingerprint = await asyncio.to_thread(
            compaction.summarize_history, None, snapshot, messages,
            stored_summary=meta.get("summary"),
            stored_fingerprint=meta.get("summary_fingerprint"),
            threshold=threshold, timeout=timeout)
        # await 被取消时不会运行到这里；后台计算无 Session，无法自行补写。
        _save_compaction(db, cid, summary, fingerprint, original)
    return messages


def _compact_history(db: Session, cid: int, config, messages):
    """摘要压缩 + meta_json 持久化（re #066 major1：摘要随存折叠集指纹；
    同一历史重放（指纹命中）复用不调模型；继续聊天后再次压缩走合并生成新摘要）。
    超时/失败时 summary 为 None，绝不补写 meta（下次重试）。"""
    from zhishi.agent import compaction
    conv = db.get(AIConversation, cid)
    if conv is None:
        return messages
    meta = _conversation_meta(conv)
    new_history, summary, fingerprint = compaction.summarize_history(
        db, config, messages, stored_summary=meta.get("summary"),
        stored_fingerprint=meta.get("summary_fingerprint"))
    _save_compaction(db, cid, summary, fingerprint, messages)
    return new_history


def _release_run_slot(app, run_id: str, conversation_id: int | None) -> None:
    """释放并发锁与取消令牌（初始化失败路径与流结束路径共用，re #016）。"""
    app.state.cancel_tokens.pop(run_id, None)
    if conversation_id is not None and app.state.active_runs.get(conversation_id) == run_id:
        app.state.active_runs.pop(conversation_id, None)


async def _start_run(app, *, message: str, conversation_id: int | None,
                     attachment_ids: list[int] | None = None,
                     plan_mode: bool = False, research_project_id: int | None = None) -> StreamingResponse:
    """chat 与计划批准共用：并发锁/session/模型/runtime/SSE 组装一致。"""
    run_id = uuid.uuid4().hex
    active = app.state.active_runs
    if conversation_id is not None and conversation_id in active:
        raise HTTPException(409, "该会话已有进行中的请求")
    if conversation_id is not None:
        active[conversation_id] = run_id

    # session 生命周期覆盖整个流（StreamingResponse 生命周期长于请求依赖）
    db = app.state.session_factory()
    try:
        if conversation_id is not None and db.get(AIConversation, conversation_id) is None:
            raise HTTPException(404, '会话不存在，请重新选择会话')
        latest = db.scalar(select(AIRun).where(AIRun.conversation_id==conversation_id)
                           .order_by(AIRun.created_at.desc())) if conversation_id is not None else None
        if latest and latest.status == 'awaiting_approval' and not _batch_consumed(db, {latest.run_id}):
            raise HTTPException(409, '该会话还有待恢复的审批，请先处理审批或停止该批次。')
        if research_project_id is not None:
            from zhishi.domain.research.service import get_project
            try:
                get_project(db, research_project_id)
            except LookupError as exc:
                raise HTTPException(404, str(exc)) from exc
        cfg = _enabled_config(db)
        model = build_model(cfg)
        if conversation_id is None:
            conv = AIConversation(title=message[:30] or '新会话')
            db.add(conv); db.commit(); db.refresh(conv)
            conversation_id = conv.id
            active[conversation_id] = run_id
        runtime = AgentRuntime(model=model, db=db,
                               model_config=cfg,
                               session_factory=app.state.session_factory,
                               storage_root=app.state.storage_root)
        # M1：续轮加载既有会话历史（多轮记忆），首轮为 None
        # 后台只计算摘要，Session 与写库仍归当前请求所有。
        history = (await _load_conversation_history_async(db, conversation_id, cfg)
                   if conversation_id is not None else None)
    except asyncio.CancelledError:
        db.close()
        _release_run_slot(app, run_id, conversation_id)
        raise
    except HTTPException:
        db.close()
        _release_run_slot(app, run_id, conversation_id)   # 锁不随初始化异常泄漏（re #016）
        raise
    except Exception as exc:
        db.close()
        _release_run_slot(app, run_id, conversation_id)
        raise HTTPException(500, f"AI 运行时初始化失败：{exc}") from exc

    from pydantic_ai import CancellationToken
    token = CancellationToken()
    app.state.cancel_tokens[run_id] = token
    aiter = _with_close(runtime.run_stream(user_text=message,
                                           conversation_id=conversation_id,
                                           history=history,
                                           attachment_ids=attachment_ids or [],
                                           plan_mode=plan_mode,
                                           research_project_id=research_project_id,
                                           run_id=run_id, cancel_token=token,
                                           usage_meta={"config_id": cfg.id,
                                                       "provider": cfg.provider_kind,
                                                       "model": cfg.model}), db)
    return await _stream_response(aiter, app, run_id, conversation_id)


@router.post("/chat/stream", response_class=EventStreamResponse)
async def chat_stream(body: ChatBody, request: Request):
    return await _start_run(request.app, message=body.message,
                            conversation_id=body.conversation_id,
                            attachment_ids=body.attachment_ids,
                            plan_mode=body.plan_mode, research_project_id=body.research_project_id)


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(db: Session = Depends(get_db)):
    rows = db.scalars(select(AIConversation).order_by(AIConversation.updated_at.desc())).all()
    return [{"id": r.id, "title": r.title,
             "updated_at": r.updated_at.isoformat()} for r in rows]


@router.get("/conversations/{cid}", response_model=list[MessageOut])
def conversation_detail(cid: int, db: Session = Depends(get_db)):
    if db.get(AIConversation, cid) is None:
        raise HTTPException(404, '会话不存在')
    rows = db.scalars(select(AIMessage).where(AIMessage.conversation_id == cid)
                      .order_by(AIMessage.id)).all()
    return [{"id": m.id, "role": m.role, "display": json.loads(m.display_json),
             "created_at": m.created_at.isoformat()} for m in rows]


@router.delete("/conversations/{cid}", status_code=204)
def delete_conversation(cid: int, request: Request, db: Session = Depends(get_db)):
    if cid in request.app.state.active_runs:
        raise HTTPException(409, '会话仍在运行，停止并保存后才能删除')
    conv = db.get(AIConversation, cid)
    if conv is None:
        raise HTTPException(404, "会话不存在")
    from zhishi.domain.models import AIContextCheckpoint, AIToolExecution
    db.query(AIContextCheckpoint).filter(AIContextCheckpoint.conversation_id == cid).delete(synchronize_session=False)
    db.query(AIToolExecution).filter(AIToolExecution.run_id.in_(select(AIRun.run_id).where(
        AIRun.conversation_id == cid))).delete(synchronize_session=False)
    for m in db.scalars(select(AIMessage).where(AIMessage.conversation_id == cid)).all():
        db.delete(m)
    # M3：AIRun/AIPendingAction 挂会话 FK，硬删会话须一并清理
    db.query(AIRun).filter(AIRun.conversation_id == cid).delete(synchronize_session=False)
    db.query(AIPendingAction).filter(
        AIPendingAction.conversation_id == cid).delete(synchronize_session=False)
    db.delete(conv)
    db.commit()


class ConfigBody(BaseModel):
    name: str
    provider_kind: Literal['openai_compat', 'openai_responses', 'anthropic'] = 'openai_compat'
    model: str
    base_url: str | None = None
    api_key: str | None = None             # 传空=不变（keyring 引用不变）
    price_input: float = 0.0
    price_output: float = 0.0
    request_limit: int = 30
    context_window: int | None = Field(default=None, ge=1024, le=10_000_000, strict=True)
    max_output_tokens: int | None = Field(default=None, ge=1, le=1_000_000, strict=True)
    reasoning_effort: ReasoningEffort | None = None
    input_modalities: list[Literal['text', 'image', 'audio', 'video']] = Field(default=['text'], min_length=1, max_length=4)

    @model_validator(mode='after')
    def _capabilities(self):
        validate_reasoning_effort(self.provider_kind, self.reasoning_effort)
        if 'text' not in self.input_modalities:
            raise ValueError('知时助手需要文字输入，请保留文字能力')
        self.input_modalities = list(dict.fromkeys(self.input_modalities))
        if (self.context_window is not None and self.max_output_tokens is not None
                and self.max_output_tokens >= self.context_window):
            raise ValueError('最大输出 token 必须小于上下文容量，为输入保留空间')
        return self

    @field_validator("request_limit")
    @classmethod
    def _non_positive_falls_back_to_default(cls, v: int) -> int:
        """re k3#049 观察②：前端表单硬编码显式传 0（bundle 实证），0/负值直穿
        pydantic 默认落库，与列默认 30 分裂。非正值一律回退 30（步数预算 >=1 才合法）。"""
        return v if v > 0 else 30


@router.post('/configs/models', response_model=ModelCatalogResponse)
def list_available_models(body: ModelCatalogRequest, db: Session = Depends(get_db)):
    from zhishi.adapters.model_catalog import CatalogError, discover_models
    if body.config_id is not None and not body.api_key.get_secret_value():
        row = db.get(AIConfig, body.config_id)
        if row is None:
            raise HTTPException(404, 'AI 配置不存在')
        if (row.provider_kind != body.provider_kind
                or (row.base_url or '').rstrip('/') != body.base_url.rstrip('/')):
            raise HTTPException(400, '地址或协议已改变，请重新填写 API key 后获取模型列表')
        from zhishi.agent.providers import resolve_api_key
        body = body.model_copy(update={'api_key': SecretStr(resolve_api_key(row.api_key_ref) or '')})
    try:
        return discover_models(body)
    except CatalogError as exc:
        raise HTTPException(exc.status, str(exc)) from None


@router.get("/configs", response_model=list[ConfigOut])
def list_configs(db: Session = Depends(get_db)):
    rows = db.scalars(select(AIConfig).order_by(AIConfig.id)).all()
    return [{"id": r.id, "name": r.name, "provider_kind": r.provider_kind,
             "model": r.model, "base_url": r.base_url, "enabled": r.enabled,
             "context_window": r.context_window, "max_output_tokens": r.max_output_tokens,
             "reasoning_effort": r.reasoning_effort,
             "input_modalities": _config_modalities(r), "has_api_key": bool(r.api_key_ref),
             "request_limit": r.request_limit, "price_input": r.price_input,
             "price_output": r.price_output} for r in rows]


def _config_modalities(row) -> list[str]:
    try:
        values = json.loads(row.input_modalities_json)
        if isinstance(values, list):
            return list(dict.fromkeys(['text', *(v for v in values if v in ('image', 'audio', 'video'))]))
    except (ValueError, TypeError):
        pass
    return ['text']


@router.post("/configs", status_code=201, response_model=CreatedOut)
def create_config(body: ConfigBody, db: Session = Depends(get_db)):
    from zhishi.infra import secrets
    ref = f"ai-config-{uuid.uuid4().hex[:8]}"
    if body.api_key:
        secrets.store_api_key(ref, body.api_key)
    row = AIConfig(name=body.name, provider_kind=body.provider_kind, model=body.model,
                   base_url=body.base_url, api_key_ref=ref if body.api_key else "",
                   price_input=body.price_input, price_output=body.price_output,
                   request_limit=body.request_limit, context_window=body.context_window,
                   max_output_tokens=body.max_output_tokens,
                   reasoning_effort=body.reasoning_effort,
                   input_modalities_json=json.dumps(body.input_modalities))
    try:
        db.add(row); db.commit(); db.refresh(row)
    except Exception:
        db.rollback()
        if body.api_key:
            secrets.delete_api_key(ref)
        raise
    return {"id": row.id}


@router.put('/configs/{cid}', response_model=ConfigOut)
def update_config(cid: int, body: ConfigBody, db: Session = Depends(get_db)):
    from zhishi.infra import secrets
    row = db.get(AIConfig, cid)
    if row is None:
        raise HTTPException(404, 'AI 配置不存在')
    old_ref = row.api_key_ref
    new_ref = f'ai-config-{uuid.uuid4().hex}' if body.api_key else None
    if new_ref:
        secrets.store_api_key(new_ref, body.api_key)
    try:
        for key, value in body.model_dump(exclude={'api_key', 'input_modalities'}).items():
            setattr(row, key, value)
        row.input_modalities_json = json.dumps(body.input_modalities)
        if new_ref:
            row.api_key_ref = new_ref
        db.commit()
    except Exception:
        db.rollback()
        if new_ref:
            secrets.delete_api_key(new_ref)
        raise
    if new_ref and old_ref:
        secrets.delete_api_key(old_ref)
    return next(item for item in list_configs(db) if item['id'] == cid)


@router.post("/configs/{cid}/enable", response_model=EnableOut)
def enable_config(cid: int, db: Session = Depends(get_db)):
    # re #036 major：无效 ID 先 404——否则会把原启用配置全部关闭，AI 功能整体瘫痪
    target = db.get(AIConfig, cid)
    if target is None:
        raise HTTPException(404, "AI 配置不存在")
    for row in db.scalars(select(AIConfig)).all():
        row.enabled = (row.id == cid)
    db.commit()
    return EnableOut(ok=True)


@router.post("/runs/{run_id}/cancel", response_model=CancelOut)
async def cancel_run(run_id: str, request: Request):
    token = request.app.state.cancel_tokens.get(run_id)
    if token is None:
        return {"ok": False}
    token.cancel()
    return {"ok": True}


# ---- 审批链路 ----

from datetime import datetime  # noqa: E402
from zhishi.domain.models import AIPendingAction, AIRun  # noqa: E402


def _batch_ready(db: Session, run_id: str) -> bool:
    """re #023③：该审批批次（同 run_id 发起的全部 deferred 调用）内是否已无
    pending——全部 confirmed/rejected/executed 才算 ready，前端据此放行 resume。"""
    remaining = db.scalar(select(func.count()).select_from(AIPendingAction).where(
        AIPendingAction.run_id == run_id, AIPendingAction.status == "pending"))
    return (remaining or 0) == 0


def _batch_consumed(db: Session, run_ids: set[str]) -> bool:
    """re #023④：源 AIRun.usage_json meta 里是否已记 resumed_by_runs（该批审批
    已被某次 resume 消费）。"""
    for rid in run_ids:
        row = db.get(AIRun, rid)
        if row is None:
            continue
        try:
            usage = json.loads(row.usage_json or "{}")
        except ValueError:
            continue
        if isinstance(usage, dict) and usage.get("resumed_by_runs"):
            return True
    return False


def _mark_batch_consumed(db: Session, involved: list[AIPendingAction],
                         resumed_by: str) -> None:
    """re #023④：resume 已组装 DeferredToolResults 并通过并发锁（即将驱动新
    execution）时落消费标记：该批 confirmed → executed（rejected 保持 rejected），
    并在源 AIRun.usage_json 记 resumed_by_runs=[新 run_id]。
    落点选择：usage_json 本就是自由 dict meta 且在源 run 终态后不再被改写，加
    namespaced key 免加列迁移；tool_calls_json 保留其工具链 trace 列表语义不动。
    流中途失败不回滚标记——宁可拒绝重试也不重复执行已批准的副作用。"""
    run_ids: set[str] = set()
    for a in involved:
        if a.status == "confirmed":
            a.status = "executed"
        run_ids.add(a.run_id)
    for rid in run_ids:
        row = db.get(AIRun, rid)
        if row is None:
            continue
        try:
            usage = json.loads(row.usage_json or "{}")
        except ValueError:
            usage = {}
        if not isinstance(usage, dict):
            usage = {}
        resumed = usage.setdefault("resumed_by_runs", [])
        if resumed_by not in resumed:
            resumed.append(resumed_by)
        row.usage_json = json.dumps(usage, ensure_ascii=False)
    db.commit()


@router.post("/actions/{action_id}/approve", response_model=ActionResolveOut)
async def approve_action(action_id: int, request: Request, body: dict | None = None, db: Session = Depends(get_db)):
    action = db.get(AIPendingAction, action_id)
    if action is None or action.status not in ("pending",):
        raise HTTPException(404, "审批不存在或已结案")
    if action.conversation_id in request.app.state.active_runs:
        raise HTTPException(409, '本轮仍在保存，请稍后处理审批。')
    if (body or {}).get("grant_always") and action.tool_name in IRREVOCABLE_TOOLS:
        # re #019 blocker：不可豁免高危操作不得建「始终允许」，整请求拒绝（不改任何状态）
        raise HTTPException(400, "不可豁免操作不支持始终允许")
    action.status, action.resolved_at = "confirmed", datetime.now()
    if (body or {}).get("grant_always"):
        from zhishi.domain.models import AIToolGrant
        db.add(AIToolGrant(tool_name=action.tool_name,
                           arg_pattern=action.args_json if _atomic_pattern(action.args_json) else ""))
    db.commit()
    return ActionResolveOut(ok=True,
                            resume=f"/ai/conversations/{action.conversation_id}/resume/stream",
                            ready_to_resume=_batch_ready(db, action.run_id))


@router.post("/actions/{action_id}/reject", response_model=ActionResolveOut)
async def reject_action(action_id: int, request: Request, body: dict | None = None, db: Session = Depends(get_db)):
    action = db.get(AIPendingAction, action_id)
    if action is None or action.status not in ("pending", "confirmed"):
        raise HTTPException(404, "审批不存在或已结案")
    if action.conversation_id in request.app.state.active_runs:
        raise HTTPException(409, '本轮仍在执行或保存，请稍后处理审批。')
    action.status, action.resolved_at = "rejected", datetime.now()
    db.commit()
    return ActionResolveOut(ok=True,
                            resume=f"/ai/conversations/{action.conversation_id}/resume/stream",
                            ready_to_resume=_batch_ready(db, action.run_id))


def _atomic_pattern(args_json: str) -> bool:
    """单对象操作（含 id 类字段）才允许按参数模式建 grant；批量/清空类永远整工具允许。"""
    try:
        args = json.loads(args_json)
    except ValueError:
        return False
    return isinstance(args, dict) and any(
        k in args for k in ("task_id", "entry_id", "event_id", "habit_id", "goal_id",
                            "subtask_id", "kr_id", "file_id"))


# ---- 「始终允许」grant 管理（re #019：可审计、可撤销） ----

@router.get("/grants", response_model=list[ToolGrantOut])
def list_grants(db: Session = Depends(get_db)):
    from zhishi.domain.models import AIToolGrant
    rows = db.scalars(select(AIToolGrant).order_by(AIToolGrant.id)).all()
    return [ToolGrantOut(id=r.id, tool_name=r.tool_name, arg_pattern=r.arg_pattern,
                         created_at=r.created_at.isoformat()) for r in rows]


@router.delete("/grants/{grant_id}", status_code=204)
def delete_grant(grant_id: int, db: Session = Depends(get_db)) -> None:
    from zhishi.domain.models import AIToolGrant
    row = db.get(AIToolGrant, grant_id)
    if row is None:
        raise HTTPException(404, "授权规则不存在")
    db.delete(row); db.commit()


@router.post("/conversations/{cid}/resume/stream", response_class=EventStreamResponse,
             responses={400: {
                 "model": ResumeBlockedOut,
                 "description": "拒绝续跑：pending 非空=本轮仍有未决审批卡（按清单逐张处理）；"
                                "consumed=true=该批次已被消费，无可恢复审批（幂等拒绝，re #023④）",
                 # 显式 application/json：response_class 的 text/event-stream 只属于 200 流
                 "content": {"application/json": {
                     "schema": {"$ref": "#/components/schemas/ResumeBlockedOut"}}},
             }})
async def resume_stream(cid: int, request: Request):
    """审批结案后恢复：取会话最后 assistant 消息的 history + 该轮全部 deferred 调用的
    结案结果，构造 DeferredToolResults 重启新 execution。
    回填范围 = history 末条模型响应中「尚未结算」的工具调用（re #028：同响应可混合
    safe/readonly 直行调用——其结果已在 trailing ModelRequest 里、不落审批表，须从
    末条响应的调用中扣除；pydantic-ai 恢复时对已结算调用自动以 skip 覆盖，路由层若
    重复回填反而触发「already executed」UserError。剩余 open 调用一个不漏，缺任一
    即 UserError 崩流，re #020 k3 major）；
    仍有 pending 审批卡 → 400 + 未决清单（typed），不启动流；
    该批次已被消费（confirmed 已转 executed / 源 run 已记 resumed_by_runs）→
    400 typed consumed，幂等拒绝，不重复回填（re #023④）。"""
    app = request.app
    run_id = uuid.uuid4().hex
    active = app.state.active_runs
    if cid in active:
        raise HTTPException(409, "该会话已有进行中的请求")
    active[cid] = run_id
    db = app.state.session_factory()
    try:
        cfg = _enabled_config(db)
        history = await _load_conversation_history_async(db, cid, cfg)
        if history is None:
            raise HTTPException(404, "无可恢复的运行")
        from pydantic_ai.messages import (
            ModelRequest, ModelResponse, RetryPromptPart, ToolCallPart, ToolReturnPart)
        needed: dict[str, str] = {}      # tool_call_id → tool_name（末条响应的全部调用）
        settled: set[str] = set()        # trailing request 已有结果（已结算）的调用
        for msg in reversed(history):
            if isinstance(msg, ModelResponse):
                for part in msg.parts:
                    if isinstance(part, ToolCallPart):
                        needed[part.tool_call_id] = part.tool_name
                break
            if isinstance(msg, ModelRequest):
                # re #028：末个 ModelResponse 之后的 trailing request 里已有
                # ToolReturnPart/RetryPromptPart 的调用 = 同轮 safe/readonly 直行
                # （或上轮 resume 已结算）——判定口径与 pydantic-ai
                # _handle_deferred_tool_results 的 skip 集合一致。
                settled.update(part.tool_call_id for part in msg.parts
                               if isinstance(part, (ToolReturnPart, RetryPromptPart)))
        # open = 末条响应全部调用 − 已结算：仅这些须落审批卡、须回填结果
        open_ids = [c for c in needed if c not in settled]
        if not open_ids:
            # 末条响应已无可回填调用：上轮 resume 已消费该批（或本无待回填调用）
            db.close()
            _release_run_slot(app, run_id, cid)
            return JSONResponse(status_code=400, content=ResumeBlockedOut(
                pending=[], consumed=True,
                message="该批次已被消费，无可恢复审批").model_dump())
        actions = {a.tool_call_id: a for a in db.scalars(select(AIPendingAction).where(
            AIPendingAction.conversation_id == cid).order_by(AIPendingAction.id)).all()}
        blocked = [actions[c] for c in open_ids
                   if c in actions and actions[c].status == "pending"]
        if blocked:
            db.close()
            _release_run_slot(app, run_id, cid)
            return JSONResponse(status_code=400, content=ResumeBlockedOut(pending=[
                ResumeBlockedPending(action_id=a.id, tool_name=a.tool_name)
                for a in blocked],
                message="本轮仍有未决审批卡，请先批准或拒绝清单中的审批后再续跑",
            ).model_dump())
        involved = [actions.get(c) for c in open_ids]
        if any(a is None for a in involved):
            raise HTTPException(
                400, "审批数据不完整：该轮存在未落审批卡的调用，无法回填")
        if any(a.status == "expired" for a in involved):
            # re #063：MCP 服务器 DELETE/连接语义字段变更已把旧 pending 卡置
            # expired——批次作废，不再回填（旧卡若续命，resume 会以
            # tool_call_approved 绕过权限门直执行同 sid 新服务器的同名工具）
            db.close()
            _release_run_slot(app, run_id, cid)
            return JSONResponse(status_code=400, content=ResumeBlockedOut(
                pending=[], consumed=True,
                message="该审批批次已过期：对应 MCP 服务器已被删除或配置变更，旧审批不再回填").model_dump())
        if (any(a.status == "executed" for a in involved)
                or _batch_consumed(db, {a.run_id for a in involved})):
            # re #023④：该批已由上次 resume 消费——幂等拒绝，防重复回填重复执行
            db.close()
            _release_run_slot(app, run_id, cid)
            return JSONResponse(status_code=400, content=ResumeBlockedOut(
                pending=[], consumed=True,
                message="该批次已被消费，无可恢复审批").model_dump())
        from pydantic_ai.tools import DeferredToolResults, ToolApproved, ToolDenied
        results = DeferredToolResults()
        for a in involved:
            results.approvals[a.tool_call_id] = (
                ToolApproved() if a.status == "confirmed"
                else ToolDenied("用户拒绝了该操作；不得重试同一调用。"))
        model = build_model(cfg)
        runtime = AgentRuntime(model=model, db=db,
                               model_config=cfg,
                               session_factory=app.state.session_factory,
                               storage_root=app.state.storage_root)
        # 已持有会话槽位；落消费标记失败也必须经过统一清理路径。
        _mark_batch_consumed(db, involved, resumed_by=run_id)
    except asyncio.CancelledError:
        db.close()
        _release_run_slot(app, run_id, cid)
        raise
    except HTTPException:
        db.close()
        _release_run_slot(app, run_id, cid)
        raise
    except Exception as exc:
        db.close()
        _release_run_slot(app, run_id, cid)
        raise HTTPException(500, f"恢复执行初始化失败：{exc}") from exc

    from pydantic_ai import CancellationToken
    token = CancellationToken()
    app.state.cancel_tokens[run_id] = token
    aiter = _with_close(runtime.run_stream(user_text=None, conversation_id=cid,
                                           history=history, deferred_results=results,
                                           run_id=run_id, cancel_token=token,
                                           usage_meta={"config_id": cfg.id,
                                                       "provider": cfg.provider_kind,
                                                       "model": cfg.model}), db)
    # 恢复轮放行边界：只有本轮回填 ToolApproved 的调用经 ctx.tool_call_approved
    # 跳过权限门；模型随后对同名工具的全新调用照常落审批门（re #020 k3 A3 验证）。
    return await _stream_response(aiter, app, run_id, cid)


# ---- 计划模式 ----

def _find_plan(db: Session, cid: int, plan_id: int):
    """在指定会话的 meta 中定位计划（v1 plans 存 AIConversation.meta_json，不建新表）。
    M2：plan_id 仅会话内唯一，查找必须限定 (conversation_id, plan_id)，
    否则跨会话撞号会误批准/误拒绝别人的计划。"""
    conv = db.get(AIConversation, cid)
    if conv is None:
        return None
    try:
        meta = json.loads(conv.meta_json or "{}")
    except ValueError:
        return None
    for p in meta.get("plans", []):
        if p.get("id") == plan_id:
            return conv, meta, p
    return None


@router.post("/conversations/{cid}/plans/{plan_id}/approve", response_class=EventStreamResponse)
async def approve_plan(cid: int, plan_id: int, request: Request, body: dict | None = None):
    """批准计划：steps 组装为执行指令，作为同一会话的新用户消息切回普通模式执行（SSE 流）。"""
    app = request.app
    with app.state.session_factory() as db:
        found = _find_plan(db, cid, plan_id)
        if found is None or found[2].get("status") != "proposed":
            raise HTTPException(404, "计划不存在或已结案")
        conv, meta, plan = found
        plan["status"] = "approved"
        conv.meta_json = json.dumps(meta, ensure_ascii=False)
        db.commit()
        lines = [f"{i}. {s.get('action', '')}（工具：{s.get('tool') or '无'}）"
                 f"{'——' + s['reason'] if s.get('reason') else ''}"
                 for i, s in enumerate(plan.get("steps", []), 1)]
        message = "请按以下计划执行：\n" + "\n".join(lines)
    try:
        return await _start_run(app, message=message, conversation_id=cid, plan_mode=False)
    except Exception:
        # 补偿（re #013）：启动失败（409 并发锁/模型初始化等）时回滚计划状态为
        # proposed，保证可重试——否则再次批准 404，计划永久卡死。
        with app.state.session_factory() as db2:
            found = _find_plan(db2, cid, plan_id)
            if found is not None and found[2].get("status") == "approved":
                found[2]["status"] = "proposed"
                found[0].meta_json = json.dumps(found[1], ensure_ascii=False)
                db2.commit()
        raise


@router.post("/conversations/{cid}/plans/{plan_id}/reject", response_model=PlanRejectOut)
async def reject_plan(cid: int, plan_id: int, request: Request, db: Session = Depends(get_db)):
    if cid in request.app.state.active_runs:
        raise HTTPException(409, '本轮仍在执行或保存，请稍后处理计划。')
    found = _find_plan(db, cid, plan_id)
    if found is None or found[2].get("status") != "proposed":
        raise HTTPException(404, "计划不存在或已结案")
    conv, meta, plan = found
    plan["status"] = "rejected"
    conv.meta_json = json.dumps(meta, ensure_ascii=False)
    db.commit()
    return PlanRejectOut(ok=True)


class SkillBody(BaseModel):
    name: str
    description: str = ""
    content: str = ""
    enabled: bool = False


@router.get("/skills", response_model=list[SkillOut])
def list_skills(db: Session = Depends(get_db)):
    from zhishi.domain.models import AISkill
    rows = db.scalars(select(AISkill).order_by(AISkill.id)).all()
    return [{"id": r.id, "name": r.name, "description": r.description,
             "enabled": r.enabled, "is_builtin": r.is_builtin} for r in rows]


@router.post("/skills", status_code=201, response_model=CreatedOut)
def create_skill(body: SkillBody, db: Session = Depends(get_db)):
    from zhishi.domain.models import AISkill
    row = AISkill(**body.model_dump(), is_builtin=False)
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id}


@router.post("/skills/{sid}/enable", response_model=EnableOut,
             response_model_exclude_none=True)   # 技能启用回 {"ok": true}，无 enabled 键（实形守恒）
def enable_skill(sid: int, db: Session = Depends(get_db)):
    from zhishi.domain.models import AISkill
    row = db.get(AISkill, sid)
    if row is None or row.is_builtin:
        raise HTTPException(404, "技能不存在或为内置技能")
    for other in db.scalars(select(AISkill).where(AISkill.is_builtin.is_(False))).all():
        other.enabled = (other.id == sid)   # 用户技能单选激活
    db.commit()
    return {"ok": True}


@router.post("/skills/disable-active", response_model=EnableOut,
             response_model_exclude_none=True)
def disable_active_skill(db: Session = Depends(get_db)):
    """停用当前激活的用户技能（内置技能不动；无激活技能时幂等 ok，re k3#049 观察①）。
    instructions 组装按 enabled 过滤（prompts._skill_text），停用后其内容自然
    退出系统提示，无需另行清理。"""
    from zhishi.domain.models import AISkill
    rows = db.scalars(select(AISkill).where(
        AISkill.is_builtin.is_(False), AISkill.enabled.is_(True))).all()
    for row in rows:
        row.enabled = False
    if rows:
        db.commit()
    return EnableOut(ok=True)


@router.delete("/skills/{sid}", status_code=204)
def delete_skill(sid: int, db: Session = Depends(get_db)):
    from zhishi.domain.models import AISkill
    row = db.get(AISkill, sid)
    if row is None or row.is_builtin:
        raise HTTPException(404, "技能不存在或为内置技能（不可删除）")
    db.delete(row); db.commit()


# ---- MCP 服务器管理 ----

class MCPServerBody(BaseModel):
    name: str
    transport: str = "http"                # stdio / http
    command: str = ""                      # stdio 可执行文件
    args_json: str = "[]"
    env_json: str = "{}"                   # 值属敏感：不回显
    url: str | None = None
    headers_json: str = "{}"               # 值属敏感：不回显
    timeout_sec: int = 30
    enabled: bool = False
    auto_approve_readonly: bool = False
    trusted: bool = False                  # B1：stdio 须显式信任才可连接/装配


class MCPServerUpdate(BaseModel):
    """部分更新：仅落传出的字段。"""
    name: str | None = None
    transport: str | None = None
    command: str | None = None
    args_json: str | None = None
    env_json: str | None = None
    url: str | None = None
    headers_json: str | None = None
    timeout_sec: int | None = None
    enabled: bool | None = None
    auto_approve_readonly: bool | None = None
    trusted: bool | None = None


# 连接语义字段（re #063）：任一实际变更 = 「同一 sid 指向了另一个服务器」，
# 该 sid 的 grants 与 pending 审批卡必须随旧端点作废（enable/timeout/name 等
# 只影响装配或展示，不改授权语义，不在其列）。
_MCP_CONNECTION_FIELDS = ("url", "command", "args_json", "env_json",
                          "headers_json", "trusted", "transport")


class MCPServerOut(BaseModel):
    """MCP 服务器元数据（re #035）：敏感值 env/headers 不回显。"""
    id: int
    name: str
    transport: str
    command: str | None
    args_json: str
    url: str | None
    timeout_sec: int
    enabled: bool
    auto_approve_readonly: bool
    trusted: bool
    last_status: str
    last_error: str | None
    created_at: str


class MCPToolSummary(BaseModel):
    """连通性测试回包里的工具摘要（实形只有 name/description，re #048）。"""
    name: str
    description: str


class MCPToolOut(BaseModel):
    """MCP 工具清单项（re #048：/tools 直连查询实形）。"""
    name: str
    description: str
    input_schema: dict = {}
    read_only: bool = False


class MCPTestOut(BaseModel):
    """MCP 连通性测试回包（re #048）：成功/失败同形收敛；
    exclude_none 保证两路实形各键守恒（成功无 error、失败无 tools）。"""
    ok: bool
    tool_count: int = 0
    tools: list[MCPToolSummary] | None = None
    error: str | None = None


def _mcp_row_out(r) -> dict:
    """敏感值（env/headers）不回显，仅返回元数据与连通状态。"""
    return {"id": r.id, "name": r.name, "transport": r.transport, "command": r.command,
            "args_json": r.args_json, "url": r.url, "timeout_sec": r.timeout_sec,
            "enabled": r.enabled, "auto_approve_readonly": r.auto_approve_readonly,
            "trusted": r.trusted,
            "last_status": r.last_status, "last_error": r.last_error,
            "created_at": r.created_at.isoformat()}


def _ensure_stdio_trusted(row) -> None:
    """B1：stdio 服务器须显式信任后才允许真实连接（/test、/tools 都会拉起子进程）。"""
    if row.transport == "stdio" and not row.trusted:
        raise HTTPException(
            403, "stdio MCP 服务器需先在配置中显式信任（trusted=true）后才能连接；"
                 "本机无认证环境下这一步防止任意进程被拉起。")


@router.get("/mcp/servers", response_model=list[MCPServerOut])
def list_mcp_servers(db: Session = Depends(get_db)):
    from zhishi.domain.models import MCPServer
    rows = db.scalars(select(MCPServer).order_by(MCPServer.id)).all()
    return [_mcp_row_out(r) for r in rows]


@router.post("/mcp/servers", status_code=201, response_model=CreatedOut)
def create_mcp_server(body: MCPServerBody, db: Session = Depends(get_db)):
    from zhishi.domain.models import MCPServer
    row = MCPServer(**body.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id}


@router.put("/mcp/servers/{sid}", response_model=MCPServerOut)
def update_mcp_server(sid: int, body: MCPServerUpdate, db: Session = Depends(get_db)):
    from zhishi.adapters import mcp_client
    from zhishi.agent.permissions import expire_mcp_pending_actions, revoke_mcp_grants
    from zhishi.domain.models import MCPServer
    row = db.get(MCPServer, sid)
    if row is None:
        raise HTTPException(404, "MCP 服务器不存在")
    updates = body.model_dump(exclude_unset=True)
    # 连接语义字段实际变更 = sid 指向了另一个服务器（re #063）：旧端点的授权与
    # pending 审批卡在 commit 前同事务作废，否则新服务器同名工具免审/旧卡续命
    reauth = any(k in updates and updates[k] != getattr(row, k)
                 for k in _MCP_CONNECTION_FIELDS)
    for k, v in updates.items():
        setattr(row, k, v)
    if reauth:
        revoke_mcp_grants(db, sid)
        expire_mcp_pending_actions(db, sid)
    db.commit()
    mcp_client.invalidate(sid)   # 行已变（url/command/env…），工具清单缓存即刻失效
    return _mcp_row_out(row)


@router.delete("/mcp/servers/{sid}", status_code=204)
def delete_mcp_server(sid: int, db: Session = Depends(get_db)):
    from zhishi.adapters import mcp_client
    from zhishi.agent.permissions import expire_mcp_pending_actions, revoke_mcp_grants
    from zhishi.domain.models import MCPServer
    row = db.get(MCPServer, sid)
    if row is None:
        raise HTTPException(404, "MCP 服务器不存在")
    # commit 前同事务撤销该 sid 的授权与 pending 审批卡（re #063）：sid 是 sqlite
    # rowid 可被新行复用，grant/pending 以 mcp__{sid}__ 为键会跨服务器继承
    revoke_mcp_grants(db, sid)
    expire_mcp_pending_actions(db, sid)
    db.delete(row); db.commit()
    mcp_client.invalidate(sid)   # id 可能被新行复用（sqlite rowid），缓存必须随删即清


class MCPEnableBody(BaseModel):
    enabled: bool = True


@router.post("/mcp/servers/{sid}/enable", response_model=EnableOut)
def enable_mcp_server(sid: int, body: MCPEnableBody | None = None, db: Session = Depends(get_db)):
    from zhishi.adapters import mcp_client
    from zhishi.domain.models import MCPServer
    row = db.get(MCPServer, sid)
    if row is None:
        raise HTTPException(404, "MCP 服务器不存在")
    row.enabled = (body.enabled if body is not None else True)
    db.commit()
    mcp_client.invalidate(sid)   # 装配与否随 enabled 切换，缓存同步失效
    return EnableOut(ok=True, enabled=row.enabled)


@router.post("/mcp/servers/{sid}/test", response_model=MCPTestOut,
             response_model_exclude_none=True)
async def test_mcp_server(sid: int, db: Session = Depends(get_db)):
    """连通性测试：连接 + list_tools，回写 last_status/last_error（错误已脱敏截断）。
    B1：untrusted 的 stdio 服务器直接 403，不拉起子进程。"""
    from zhishi.adapters import mcp_client
    from zhishi.domain.models import MCPServer
    row = db.get(MCPServer, sid)
    if row is None:
        raise HTTPException(404, "MCP 服务器不存在")
    _ensure_stdio_trusted(row)
    try:
        tools = await mcp_client.list_tools(row, use_cache=False)  # /test 的意义就是真连
        row.last_status, row.last_error = "ok", None
        db.commit()
        return {"ok": True, "tool_count": len(tools),
                "tools": [{"name": t["name"], "description": t["description"]} for t in tools]}
    except Exception as exc:
        err = str(exc)[:300]
        row.last_status, row.last_error = "error", err
        db.commit()
        return {"ok": False, "error": err, "tool_count": 0}


@router.get("/mcp/servers/{sid}/tools", response_model=list[MCPToolOut])
async def list_mcp_server_tools(sid: int, db: Session = Depends(get_db)):
    """工具清单（60s TTL 缓存；PUT/enable/DELETE 时主动失效，清账 B2）。
    B1：untrusted 的 stdio 服务器直接 403，不拉起子进程。"""
    from zhishi.adapters import mcp_client
    from zhishi.domain.models import MCPServer
    row = db.get(MCPServer, sid)
    if row is None:
        raise HTTPException(404, "MCP 服务器不存在")
    _ensure_stdio_trusted(row)
    try:
        return await mcp_client.list_tools(row)
    except mcp_client.MCPClientError as exc:
        raise HTTPException(502, str(exc)) from exc
