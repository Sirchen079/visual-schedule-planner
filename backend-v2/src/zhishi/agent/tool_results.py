"""Persist large tool outputs before replacing their model-facing text with references."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace

from pydantic_ai.messages import ModelRequest, ToolReturnPart
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from zhishi.agent.context_budget import estimate_messages_tokens, estimate_text_tokens, history_budget
from zhishi.domain.models import AIContextArtifact


def _text(content) -> str | None:
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False)
    except (TypeError, ValueError):
        return None


def save_artifact(db, conversation_id: int, tool: str, text: str) -> int:
    fingerprint = hashlib.sha256((tool + '\0' + text).encode('utf-8')).hexdigest()
    db.execute(insert(AIContextArtifact).values(conversation_id=conversation_id,
        fingerprint=fingerprint, tool=tool, content=text).on_conflict_do_nothing(
            index_elements=['conversation_id', 'fingerprint']))
    result = db.scalar(select(AIContextArtifact.id).where(
        AIContextArtifact.conversation_id == conversation_id, AIContextArtifact.fingerprint == fingerprint))
    db.commit()
    return result


def externalize_results(messages: list, *, budget: int | None, archive) -> list:
    """Keep tool-call identities and outcomes, with durable pointers to long text."""
    result = list(messages)
    limit = min(4096, max(768, (budget or 32000) // 8))
    returns = [(i, j) for i, message in enumerate(messages) if isinstance(message, ModelRequest)
               for j, part in enumerate(message.parts) if isinstance(part, ToolReturnPart)]
    under_pressure = budget is not None and estimate_messages_tokens(messages) > budget * .75
    for order, (i, j) in enumerate(returns):
        part = result[i].parts[j]
        if (part.metadata or {}).get('zhishi_result_ref') or part.tool_name in ('read_tool_result', 'search_tools'):
            continue
        text = _text(part.content)
        threshold = min(limit, 768) if under_pressure and order < len(returns) - 2 else limit
        if text is None or estimate_text_tokens(text) <= threshold:
            continue
        ref = archive(part.tool_name, text)
        value = {'result_ref': ref, 'tool': part.tool_name, 'characters': len(text),
                 'preview': text[:600],
                 'next_call': {'tool': 'read_tool_result', 'args': {'result_ref': ref}},
                 'note': '完整结果已保存。这里只是开头预览，按 next_call 分页或用 query 查找原文；不要把未读部分当作已核对。'}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                for key in ('ok', 'status', 'error', 'code'):
                    if key in parsed and isinstance(parsed[key], (bool, int, str)):
                        value[key] = parsed[key][:300] if isinstance(parsed[key], str) else parsed[key]
        except ValueError:
            pass
        parts = list(result[i].parts)
        parts[j] = replace(part, content=json.dumps(value, ensure_ascii=False),
                           metadata={**(part.metadata or {}), 'zhishi_result_ref': ref})
        result[i] = replace(result[i], parts=parts)
    return result


def tool_result_hooks(config, db, conversation_id):
    from pydantic_ai.capabilities import Hooks

    def prepare(ctx, request):
        if conversation_id is None:
            return request
        from zhishi.agent.context_budget import request_extra_tokens
        budget = history_budget(config, request_extra_tokens(request.model_request_parameters))
        messages = externalize_results(request.messages, budget=budget,
            archive=lambda tool, text: save_artifact(db, conversation_id, tool, text))
        return replace(request, messages=messages)

    return Hooks(before_model_request=prepare)
