from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import AIConfig, AIUsageLog


def extract_usage(provider: str, payload: dict[str, Any]) -> dict[str, int]:
    """从三种接口格式的响应中解析 token 用量；字段缺失时全部记 0。

    - openai_chat:       usage.{prompt_tokens, completion_tokens, total_tokens}
    - openai_responses:  usage.{input_tokens, output_tokens, total_tokens}
    - claude_messages:   usage.{input_tokens, output_tokens}
    """
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if provider == "openai_chat":
        prompt = usage.get("prompt_tokens")
        completion = usage.get("completion_tokens")
        total = usage.get("total_tokens")
    else:
        prompt = usage.get("input_tokens")
        completion = usage.get("output_tokens")
        total = usage.get("total_tokens")
    prompt_i = _to_int(prompt)
    completion_i = _to_int(completion)
    total_i = _to_int(total) or (prompt_i + completion_i)
    return {
        "prompt_tokens": prompt_i,
        "completion_tokens": completion_i,
        "total_tokens": total_i,
    }


def _to_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def log_usage(
    db: Session,
    *,
    config: Optional[AIConfig],
    kind: str,
    payload: dict[str, Any],
    conversation_id: Optional[int] = None,
) -> None:
    """记录一次模型调用的 token 用量。

    用量统计是附属能力：任何异常都静默回滚，绝不影响对话/报告主流程。
    """
    try:
        provider = config.provider if config else ""
        entry = AIUsageLog(
            config_id=config.id if config else None,
            conversation_id=conversation_id,
            kind=kind,
            provider=provider,
            model=config.model if config else "",
            **extract_usage(provider, payload),
        )
        db.add(entry)
        db.commit()
    except Exception:
        db.rollback()
