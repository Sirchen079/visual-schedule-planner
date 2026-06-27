from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AIConfig
from app.schemas import AIConfigCreate, AIConfigResponse, AIConfigUpdate

MASKED_SECRET = "***"
SENSITIVE_HEADER_PARTS = ("authorization", "api-key", "apikey", "token", "secret", "key")


def mask_key(key: str) -> str:
    if len(key) <= 8:
        return MASKED_SECRET
    return f"{key[:3]}***{key[-4:]}"


def headers_to_json(headers: dict[str, str] | None) -> str:
    return json.dumps(headers or {}, ensure_ascii=False)


def headers_from_json(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(k): str(v) for k, v in parsed.items()}


def options_to_json(options: dict[str, Any] | None) -> str:
    return json.dumps(options or {}, ensure_ascii=False)


def options_from_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def is_sensitive_header(name: str) -> bool:
    normalized = name.lower()
    return any(part in normalized for part in SENSITIVE_HEADER_PARTS)


def mask_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        name: MASKED_SECRET if is_sensitive_header(name) else value
        for name, value in headers.items()
    }


def mask_options(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(name): MASKED_SECRET if is_sensitive_header(str(name)) else mask_options(item)
            for name, item in value.items()
        }
    if isinstance(value, list):
        return [mask_options(item) for item in value]
    return value


def merge_masked_headers(config: AIConfig, headers: dict[str, str] | None) -> dict[str, str]:
    current = headers_from_json(config.extra_headers)
    merged = {}
    for name, value in (headers or {}).items():
        if value == MASKED_SECRET and is_sensitive_header(name) and name in current:
            merged[name] = current[name]
        else:
            merged[name] = value
    return merged


def merge_masked_options(config: AIConfig, options: dict[str, Any] | None) -> dict[str, Any]:
    current = options_from_json(config.native_web_search_options)
    return _merge_masked_value(current, options or {})


def _merge_masked_value(current: Any, incoming: Any) -> Any:
    if incoming == MASKED_SECRET:
        return current
    if isinstance(current, dict) and isinstance(incoming, dict):
        return {
            str(name): _merge_masked_value(current.get(str(name)), value)
            for name, value in incoming.items()
        }
    if isinstance(current, list) and isinstance(incoming, list):
        merged = []
        for index, value in enumerate(incoming):
            current_value = current[index] if index < len(current) else None
            merged.append(_merge_masked_value(current_value, value))
        return merged
    return incoming


def to_response(config: AIConfig) -> AIConfigResponse:
    return AIConfigResponse(
        id=config.id,
        name=config.name,
        assistant_name=config.assistant_name,
        persona=config.persona or "",
        provider=config.provider,
        model=config.model,
        api_key_masked=mask_key(config.api_key),
        base_url=config.base_url,
        full_url=config.full_url,
        proxy_url=config.proxy_url,
        extra_headers=mask_headers(headers_from_json(config.extra_headers)),
        native_web_search_enabled=bool(config.native_web_search_enabled),
        native_web_search_options=mask_options(
            options_from_json(config.native_web_search_options)
        ),
        enabled=config.enabled,
        active_skill_id=config.active_skill_id,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


def list_configs(db: Session) -> list[AIConfigResponse]:
    rows = db.execute(select(AIConfig).order_by(AIConfig.created_at.desc())).scalars().all()
    return [to_response(row) for row in rows]


def create_config(db: Session, payload: AIConfigCreate) -> AIConfigResponse:
    data = payload.model_dump()
    data["extra_headers"] = headers_to_json(data.pop("extra_headers", {}))
    data["native_web_search_options"] = options_to_json(
        data.pop("native_web_search_options", {})
    )
    config = AIConfig(**data)
    db.add(config)
    db.commit()
    db.refresh(config)
    return to_response(config)


def update_config(
    db: Session, config_id: int, payload: AIConfigUpdate
) -> AIConfigResponse | None:
    config = db.get(AIConfig, config_id)
    if config is None:
        return None
    data = payload.model_dump(exclude_unset=True)
    if "extra_headers" in data:
        data["extra_headers"] = headers_to_json(
            merge_masked_headers(config, data["extra_headers"])
        )
    if "native_web_search_options" in data:
        data["native_web_search_options"] = options_to_json(
            merge_masked_options(config, data["native_web_search_options"])
        )
    for field, value in data.items():
        setattr(config, field, value)
    db.commit()
    db.refresh(config)
    return to_response(config)


def enable_config(db: Session, config_id: int) -> AIConfigResponse | None:
    config = db.get(AIConfig, config_id)
    if config is None:
        return None
    for row in db.execute(select(AIConfig)).scalars().all():
        row.enabled = row.id == config_id
    db.commit()
    db.refresh(config)
    return to_response(config)


def get_enabled_config(db: Session) -> AIConfig | None:
    return db.execute(
        select(AIConfig).where(AIConfig.enabled.is_(True))
    ).scalar_one_or_none()
