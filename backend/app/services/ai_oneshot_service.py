"""单次 AI 文本/JSON 生成助手：内嵌 AI 动作与秘书自动档共用的最小封装。

与 agent loop 的区别：不走多轮工具循环，一次调用拿结果；
每次调用都记 token 用量（ai_usage_logs），失败向上抛由调用方降级。
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import AIConfig
from app.services import ai_client, ai_config_service, ai_usage_service


async def generate_text(
    db: Session,
    config: AIConfig,
    system: str,
    user: str,
    *,
    kind: str,
) -> str:
    """单次文本生成。kind 用于用量归类（briefing/report 之外的内嵌动作）。"""
    req = ai_client.build_provider_request(
        provider=config.provider,
        model=config.model,
        api_key=config.api_key,
        messages=[{"role": "user", "content": user}],
        system_prompt=system,
        extra_headers=ai_config_service.headers_from_json(config.extra_headers),
        base_url=config.base_url,
        full_url=config.full_url,
        proxy_url=config.proxy_url,
    )
    raw = await ai_client.call_provider(req)
    ai_usage_service.log_usage(db, config=config, kind=kind, payload=raw)
    return (ai_client.extract_text(config.provider, raw) or "").strip()


async def generate_json(
    db: Session,
    config: AIConfig,
    system: str,
    user: str,
    *,
    kind: str,
) -> dict[str, Any] | None:
    """单次 JSON 生成：要求模型只输出一个 JSON 对象，宽松提取；失败返回 None。"""
    text = await generate_text(
        db, config, system, user + "\n\n只输出一个 JSON 对象，不要输出任何其他文字。", kind=kind
    )
    for candidate in ai_client._extract_json_objects(text):
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None
