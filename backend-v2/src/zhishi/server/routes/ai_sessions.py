"""Persisted window state and conversation-scoped execution/context inspection."""
import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from zhishi.agent.session_store import metadata
from zhishi.agent.user_input import UserAnswer
from zhishi.domain.models import (
    AIConfig,
    AIContextCheckpoint,
    AIConversation,
    AIMessage,
    AIPendingAction,
    AIRun,
    AIWorkspace,
)
from zhishi.server.deps import get_db

router = APIRouter(prefix='/ai', tags=['ai'])
Surface = Literal['main', 'widget']
Database = Annotated[Session, Depends(get_db)]


class DraftAttachment(BaseModel):
    id: int = Field(gt=0)
    name: str = Field(max_length=500)


class Draft(BaseModel):
    text: str = Field(default='', max_length=100000)
    attachments: list[DraftAttachment] = Field(default=[], max_length=50)


class WorkspaceState(BaseModel):
    active_id: int | None = Field(default=None, gt=0)
    drafts: dict[str, Draft] = Field(default={}, max_length=200)
    question_drafts: dict[str, dict[str, UserAnswer]] = Field(default={}, max_length=100)


class WorkspaceOut(BaseModel):
    revision: int = Field(default=0, ge=0)
    state: WorkspaceState = Field(default_factory=WorkspaceState)


@router.get('/workspaces/{surface}', response_model=WorkspaceOut)
def workspace(surface: Surface, db: Database):
    row = db.get(AIWorkspace, surface)
    return WorkspaceOut(revision=row.revision, state=json.loads(row.state_json)) if row else WorkspaceOut()


@router.put('/workspaces/{surface}', response_model=WorkspaceOut)
def save_workspace(surface: Surface, body: WorkspaceOut, db: Database):
    db.execute(insert(AIWorkspace).values(surface=surface, revision=0, state_json='{}')
               .on_conflict_do_nothing(index_elements=['surface']))
    changed = db.execute(update(AIWorkspace).where(
        AIWorkspace.surface==surface, AIWorkspace.revision==body.revision).values(
        revision=body.revision+1, state_json=body.state.model_dump_json()))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, '窗口状态已由另一实例更新；本地草稿仍保留，请重新打开窗口后核对。')
    db.commit()
    return WorkspaceOut(revision=body.revision+1, state=body.state)


class ConversationStateOut(BaseModel):
    conversation_id: int
    active_run_id: str | None
    latest_run_id: str | None
    status: str
    approvals: list[dict]
    plan: dict | None
    can_resume: bool
    message_count: int
    archive_count: int
    working_rounds: int
    summary: str
    model: str
    context_window: int | None
    questions: list[dict] = []
    work_plan: list[dict] = []


class CancelPendingBody(BaseModel):
    run_id: str


class CancelPendingOut(BaseModel):
    ok: bool = True


@router.post('/conversations/{cid}/pending/cancel', response_model=CancelPendingOut)
async def cancel_pending(cid: int, body: CancelPendingBody, request: Request, db: Database):
    from pydantic_ai.messages import ModelMessagesTypeAdapter, ToolReturnPart

    from zhishi.agent.session_store import close_unresolved_calls
    if cid in request.app.state.active_runs:
        raise HTTPException(409, '本轮仍在执行，请先停止并等待保存。')
    row = db.get(AIRun, body.run_id)
    if row is None or row.conversation_id != cid:
        raise HTTPException(404, '审批运行不存在')
    if row.status not in ('awaiting_approval', 'awaiting_input'):
        return {'ok': True}
    results = {}
    from zhishi.domain.models import AIUserInput
    for question in db.scalars(select(AIUserInput).where(AIUserInput.run_id == row.run_id)):
        question.status = 'expired'
        results[question.tool_call_id] = ToolReturnPart(tool_name='ask_user',
            tool_call_id=question.tool_call_id,
            content='用户停止了本组问题；没有提供新答案，不推定任何选择或授权。')
    for action in db.scalars(select(AIPendingAction).where(AIPendingAction.conversation_id==cid,
                                                          AIPendingAction.run_id==row.run_id)):
        if action.status != 'executed':
            action.status = 'expired'
            results[action.tool_call_id] = ToolReturnPart(tool_name=action.tool_name,
                tool_call_id=action.tool_call_id, content='用户停止本批审批，操作未获准执行；不得自动重试。')
    for message in db.scalars(select(AIMessage).where(AIMessage.conversation_id==cid, AIMessage.role=='assistant')):
        display = metadata(message.display_json)
        if display.get('run_id') == row.run_id:
            display['status'] = 'cancelled'
            message.display_json = json.dumps(display, ensure_ascii=False)
            message.history_json = ModelMessagesTypeAdapter.dump_json(close_unresolved_calls(
                ModelMessagesTypeAdapter.validate_json(message.history_json), results)).decode()
    row.status = 'cancelled'
    row.done_reason = 'cancelled'
    db.commit()
    return {'ok': True}


@router.get('/conversations/{cid}/state', response_model=ConversationStateOut)
def conversation_state(cid: int, request: Request, db: Database):
    from zhishi.agent.compaction import _round_starts
    from zhishi.agent.permissions import IRREVOCABLE_TOOLS
    from zhishi.server.routes.ai import _batch_consumed, _raw_conversation_history
    conv = db.get(AIConversation,cid)
    if conv is None:
        raise HTTPException(404, '会话不存在')
    latest = db.scalar(select(AIRun).where(AIRun.conversation_id==cid).order_by(AIRun.created_at.desc()))
    actions = []
    questions = []
    if latest and latest.status in ('awaiting_approval', 'awaiting_input') and not _batch_consumed(db, {latest.run_id}):
        actions = list(db.scalars(select(AIPendingAction).where(
            AIPendingAction.conversation_id==cid, AIPendingAction.run_id==latest.run_id).order_by(AIPendingAction.id)))
        from zhishi.agent.user_input import to_read
        from zhishi.domain.models import AIUserInput
        questions = [to_read(row).model_dump() for row in db.scalars(select(AIUserInput).where(
            AIUserInput.conversation_id == cid, AIUserInput.run_id == latest.run_id).order_by(AIUserInput.id))]
    meta = metadata(conv.meta_json)
    cfg = db.scalar(select(AIConfig).where(AIConfig.enabled.is_(True)))
    return ConversationStateOut(conversation_id=cid,
        active_run_id=request.app.state.active_runs.get(cid),
        latest_run_id=latest.run_id if latest else None, status=latest.status if latest else 'idle',
        approvals=[{'action_id': a.id, 'tool': a.tool_name, 'args': metadata(a.args_json), 'preview': a.preview,
            'grant_available': a.tool_name not in IRREVOCABLE_TOOLS, 'status': a.status} for a in actions],
        plan=next((p for p in reversed(meta.get('plans',[])) if p.get('status')=='proposed'),None),
        can_resume=bool(actions or questions) and all(a.status in ('confirmed','rejected') for a in actions)
                   and all(q['status'] in ('answered','skipped') for q in questions),
        message_count=db.scalar(select(func.count()).select_from(AIMessage).where(AIMessage.conversation_id==cid)),
        archive_count=db.scalar(select(func.count()).select_from(AIContextCheckpoint).where(AIContextCheckpoint.conversation_id==cid)),
        working_rounds=len(_round_starts(_raw_conversation_history(db,cid) or [])),
        summary=meta.get('summary',''), model=cfg.model if cfg else '', context_window=cfg.context_window if cfg else None,
        questions=questions, work_plan=meta.get('work_plan', []))


from zhishi.agent.user_input import UserInputOut, UserInputReply, answer_request, to_read  # noqa: E402


class UserInputResolutionOut(BaseModel):
    request: UserInputOut
    ready_to_resume: bool


@router.post('/runtime/update-prepare')
def prepare_desktop_update(request: Request) -> dict[str, bool]:
    if request.app.state.active_runs:
        raise HTTPException(409, '还有 AI 任务正在运行。完成或停止后，点击“安装并重启”。')
    request.app.state.update_preparing = True
    return {'ok': True}


@router.post('/runtime/update-cancel')
def cancel_desktop_update(request: Request) -> dict[str, bool]:
    request.app.state.update_preparing = False
    return {'ok': True}


@router.post('/conversations/{cid}/questions/{question_id}/answer', response_model=UserInputResolutionOut)
def answer_question(cid: int, question_id: int, body: UserInputReply, request: Request, db: Database):
    from zhishi.domain.models import AIUserInput
    from zhishi.server.routes.ai import _batch_consumed, _batch_ready
    row = db.scalar(select(AIUserInput).where(AIUserInput.id == question_id, AIUserInput.conversation_id == cid))
    if row is None:
        raise HTTPException(404, '本会话没有该问题')
    if cid in request.app.state.active_runs:
        raise HTTPException(409, '本轮仍在保存，请稍后提交答案')
    source = db.get(AIRun, row.run_id)
    if source is None or source.status not in ('awaiting_input', 'awaiting_approval'):
        raise HTTPException(409, '该问题所属任务已结束，请同步最新状态')
    try:
        row = answer_request(db, row, body)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return UserInputResolutionOut(request=to_read(row),
        ready_to_resume=_batch_ready(db, row.run_id) and not _batch_consumed(db, {row.run_id}))
