"""Commit supported local writes and their idempotency receipts together."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from zhishi.domain.models import AIWriteReceipt


class MutationConflict(ValueError):
    pass


def execute_mutation(db, *, tool: str, arguments: dict, action: Callable[[], dict],
                     ctx=None, request_key: str | None = None) -> str:
    """Actions must flush, never commit. Failures leave neither writes nor receipts.

    Default keys deduplicate identical arguments within one user request, including
    approval/question resumes. Explicit keys are scoped to the conversation and
    allow separate, intentionally identical operations when the user requests them.
    """
    if request_key is not None and (not request_key.strip() or len(request_key) > 128):
        raise ValueError('request_key 必须为1至128个字符；同一次操作重试复用原键')
    encoded = json.dumps(arguments, sort_keys=True, ensure_ascii=False, separators=(',', ':'), default=str)
    fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
    deps = getattr(ctx, 'deps', None)
    cid = getattr(deps, 'conversation_id', None)
    capture = getattr(deps, 'capture_key', '') or getattr(deps, 'run_id', '')
    scope = 'explicit' if request_key else capture
    key = request_key or fingerprint
    try:
        receipt = None
        if cid is not None and scope:
            # The unique insert also serializes competing writers before they read
            # business state; a failed transaction never reserves a key permanently.
            claimed = db.execute(insert(AIWriteReceipt).values(
                conversation_id=cid, scope=scope, tool=tool, request_key=key,
                fingerprint=fingerprint).on_conflict_do_nothing(
                    index_elements=['conversation_id', 'scope', 'tool', 'request_key']))
            receipt = db.scalar(select(AIWriteReceipt).where(
                AIWriteReceipt.conversation_id == cid, AIWriteReceipt.scope == scope,
                AIWriteReceipt.tool == tool, AIWriteReceipt.request_key == key))
            if not claimed.rowcount:
                if receipt.fingerprint != fingerprint:
                    raise MutationConflict('此 request_key 已对应另一组参数；先核对已有结果，不要换键重试同一操作')
                result = json.loads(receipt.result_json)
                if result is None:
                    raise MutationConflict('此操作结果尚未确认，请先读取当前状态')
                db.rollback()
                result['replayed'] = True
                result['replay_note'] = '这是原操作回执，没有再次写入；当前状态可能已被修改，需要时读取详情核对。'
                return json.dumps(result, ensure_ascii=False, default=str)
        result = action()
        result.setdefault('ok', True)
        result.setdefault('write_status', 'committed')
        if receipt is not None:
            receipt.result_json = json.dumps(result, ensure_ascii=False, default=str)
        db.commit()
        return json.dumps(result, ensure_ascii=False, default=str)
    except BaseException:
        db.rollback()
        raise
