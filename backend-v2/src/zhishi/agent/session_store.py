"""Durable conversation state; presentation, execution and compacted context stay distinct."""
# ruff: noqa: DTZ005
import json
from datetime import datetime

from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from zhishi.domain.models import (
    AIContextCheckpoint,
    AIConversation,
    AIMessage,
    AIRun,
    AIToolExecution,
)


def recorded_results(db, run_id: str) -> dict:
    rows = db.scalars(select(AIToolExecution).where(
        AIToolExecution.run_id == run_id, AIToolExecution.status != 'running'))
    return {r.call_id:ToolReturnPart(tool_name=r.tool, tool_call_id=r.call_id,
        content=json.loads(r.result_json)) for r in rows}


def metadata(value: str | None) -> dict:
    try:
        parsed = json.loads(value or '{}')
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def archive_compaction(db, cid: int, history: list, summary: str, fingerprint: str) -> None:
    db.execute(insert(AIContextCheckpoint).values(conversation_id=cid, fingerprint=fingerprint,
        history_json=ModelMessagesTypeAdapter.dump_json(history).decode(), summary=summary)
        .on_conflict_do_nothing(index_elements=['conversation_id', 'fingerprint']))


def close_unresolved_calls(messages: list, results: dict | None = None) -> list:
    """Interrupted calls are unknown, never silently retried or reported successful."""
    pending = {}
    for msg in messages:
        for part in msg.parts:
            if isinstance(part, ToolCallPart):
                pending[part.tool_call_id] = part
            elif isinstance(part, (ToolReturnPart, RetryPromptPart)):
                pending.pop(getattr(part, 'tool_call_id', None), None)
    if not pending:
        return list(messages)
    known = results or {}
    returns = [known.get(key) or ToolReturnPart(tool_name=call.tool_name, tool_call_id=key,
        content={'ok':False, 'interrupted':True,
            'message':'执行已中断，结果未确认。先读取实际业务状态核对；不要自动重复写入。'})
        for key, call in pending.items()]
    return [*messages, ModelRequest(parts=returns)]


def begin_turn(db, cid: int, run_id: str, user_text: str | None, history: list | None, attachment_ids=()):
    row = AIRun(run_id=run_id, conversation_id=cid, status='running')
    db.add(row)
    if user_text is not None:
        from zhishi.domain.models import LibraryFile
        attachments = []
        for fid in dict.fromkeys(attachment_ids):
            file = db.get(LibraryFile, fid)
            if file is not None:
                attachments.append({'id':fid, 'name':file.original_name})
        display = {'text':user_text, 'capture_key':run_id, 'run_id':run_id}
        if attachments:
            display['attachments'] = attachments
        db.add(AIMessage(conversation_id=cid, role='user', history_json='[]',
            display_json=json.dumps(display,ensure_ascii=False)))
    db.flush()
    initial = list(history or [])
    if user_text is not None:
        initial.append(ModelRequest(parts=[UserPromptPart(user_text)]))
    assistant = AIMessage(conversation_id=cid, role='assistant',
        history_json=ModelMessagesTypeAdapter.dump_json(initial).decode(),
        display_json=json.dumps({'text':'','run_id':run_id,'status':'running'},ensure_ascii=False))
    db.add(assistant)
    conv = db.get(AIConversation,cid)
    conv.updated_at = datetime.now()
    db.commit()
    return row, assistant


def checkpoint(db, run_row, assistant, messages, events, *, status='running', error=None):
    text = ''.join(e.get('delta','') for e in events if e.get('type')=='text_delta')
    reasoning = ''.join(e.get('delta','') for e in events if e.get('type')=='reasoning_delta')
    tools = [e for e in events if e.get('type') in ('tool_call_started','tool_call_result')]
    if status != 'running':
        tools = repair_tool_display(db, run_row.run_id, tools)
    assistant.display_json = json.dumps({'text':text,'reasoning':reasoning,'tools':tools,
        'run_id':run_row.run_id,'status':status,'error':error},ensure_ascii=False)
    if messages is not None:
        assistant.history_json = ModelMessagesTypeAdapter.dump_json(messages).decode()
    run_row.tool_calls_json = json.dumps(tools,ensure_ascii=False)
    run_row.status = status
    run_row.error = error
    run_row.updated_at = datetime.now()
    conv = db.get(AIConversation,run_row.conversation_id)
    if conv is not None:
        conv.updated_at = datetime.now()
    db.commit()


def repair_tool_display(db, run_id, events):
    events = list(events)
    started = {e.get('call_id') for e in events if e.get('type')=='tool_call_started'}
    finished = {e.get('call_id') for e in events if e.get('type')=='tool_call_result'}
    for receipt in db.scalars(select(AIToolExecution).where(AIToolExecution.run_id==run_id)):
        if receipt.call_id not in started:
            events.append({'type':'tool_call_started','call_id':receipt.call_id,'tool':receipt.tool,
                'args_preview':'执行回执已保存'})
        if receipt.call_id not in finished and receipt.status != 'running':
            result = json.loads(receipt.result_json)
            parsed = metadata(result) if isinstance(result,str) else result
            ok = receipt.status=='completed' and not (isinstance(parsed,dict) and parsed.get('ok') is False)
            events.append({'type':'tool_call_result','call_id':receipt.call_id,'ok':ok,
                'result_preview':(result if isinstance(result,str) else json.dumps(result,ensure_ascii=False))[:2000],
                'duration_ms':0})
    return events


def with_partial_response(messages: list, streamed_text: str, *, committed_text: str = '') -> list:
    """Preserve uncommitted text from a provider stream that ended in an exception."""
    result = list(messages)
    # Only compare against responses produced by this model request. Compaction
    # may remove earlier responses, so a prefix of the full history is not stable.
    tail = streamed_text.removeprefix(committed_text)
    if tail:
        result.append(ModelResponse(parts=[TextPart(tail)]))
    return result


def interrupt_run(db, run, reason='process_interrupted'):
    run.status = 'interrupted'
    run.done_reason = reason
    run.error = '本轮运行中断；已保留最近检查点，请核对未确认操作。'
    run.updated_at = datetime.now()
    for message in db.scalars(select(AIMessage).where(
            AIMessage.conversation_id==run.conversation_id, AIMessage.role=='assistant')):
        display = metadata(message.display_json)
        if display.get('run_id') != run.run_id:
            continue
        display.update(status='interrupted',error=run.error)
        display['tools'] = repair_tool_display(db,run.run_id,display.get('tools',[]))
        try:
            history = ModelMessagesTypeAdapter.validate_json(message.history_json)
            message.history_json = ModelMessagesTypeAdapter.dump_json(
                close_unresolved_calls(history, recorded_results(db, run.run_id))).decode()
        except ValueError:
            display['error'] += ' 该条上下文记录无法解析，原始记录保持原样。'
        message.display_json = json.dumps(display,ensure_ascii=False)


def recover_interrupted(db) -> int:
    rows = list(db.scalars(select(AIRun).where(AIRun.status=='running')))
    for source in db.scalars(select(AIRun).where(AIRun.status=='awaiting_approval')):
        children = metadata(source.usage_json).get('resumed_by_runs', [])
        if children and not any(db.get(AIRun, rid) is not None for rid in children):
            rows.append(source)
    for run in rows:
        interrupt_run(db,run)
    db.commit()
    return len(rows)
