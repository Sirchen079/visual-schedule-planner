"""List model IDs from the endpoint explicitly entered in the local settings form.

No configuration or key is saved. Redirects and upstream error bodies are never
forwarded: a failed catalog request must not disclose the entered credential.
"""
from __future__ import annotations

import json
import time
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, Field, SecretStr


class ModelCatalogRequest(BaseModel):
    config_id: int | None = Field(default=None, gt=0)
    provider_kind: Literal['openai_compat', 'openai_responses', 'anthropic'] = 'openai_compat'
    base_url: str = Field(min_length=1, max_length=2000)
    api_key: SecretStr = Field(default_factory=lambda: SecretStr(''))


class CatalogModel(BaseModel):
    id: str
    name: str


class ModelCatalogResponse(BaseModel):
    models: list[CatalogModel]
    truncated: bool = False


class CatalogError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def catalog_url(base_url: str, provider: str) -> str:
    value = base_url.strip()
    try:
        parts = urlsplit(value)
        port = parts.port
        if (parts.scheme not in ('http', 'https') or not parts.hostname or parts.username is not None
                or parts.password is not None or parts.query or parts.fragment or '\\' in value
                or any(ord(ch) < 32 for ch in value) or port == 0):
            raise ValueError()
    except ValueError:
        raise CatalogError('请填写有效的 HTTP(S) 基础地址，不含用户名、密码、查询参数或片段。') from None
    path = parts.path.rstrip('/')
    if path.endswith(('/chat/completions', '/responses', '/messages')):
        raise CatalogError('请填写基础地址，例如 https://服务地址/v1，不要包含 /chat/completions、/responses 或 /messages。')
    if not path:
        path = '/v1'
    elif provider == 'anthropic' and not path.endswith('/v1'):
        path += '/v1'
    return urlunsplit((parts.scheme, parts.netloc, path + '/models', '', ''))


def discover_models(body: ModelCatalogRequest, *, transport=None) -> ModelCatalogResponse:
    url = catalog_url(body.base_url, body.provider_kind)
    key = body.api_key.get_secret_value().strip()
    if any(ord(ch) < 32 or ord(ch) > 126 for ch in key):
        raise CatalogError('API Key 含有无效字符，请检查复制内容。')
    headers = {'Accept': 'application/json'}
    if body.provider_kind == 'anthropic':
        headers['anthropic-version'] = '2023-06-01'
        if key:
            headers['x-api-key'] = key
    elif key:
        headers['Authorization'] = f'Bearer {key}'
    models: dict[str, CatalogModel] = {}
    cursor = None
    cursors = set()
    truncated = False
    started = time.monotonic()
    try:
        with httpx.Client(timeout=httpx.Timeout(12, connect=5), follow_redirects=False,
                          trust_env=False, transport=transport) as client:
            for page in range(3):
                params = {'after_id' if body.provider_kind == 'anthropic' else 'after': cursor} if cursor else None
                with client.stream('GET', url, headers=headers, params=params) as response:
                    status = response.status_code
                    if status in (401, 403):
                        raise CatalogError('认证失败，请检查 API Key、访问权限及服务地址。', 400)
                    if status in (404, 405, 501):
                        raise CatalogError('该地址未提供模型列表接口；请检查基础地址，或手动填写模型名称。', 400)
                    if 300 <= status < 400:
                        raise CatalogError('服务返回了重定向；请使用最终的基础地址后重试。', 400)
                    if status == 429:
                        raise CatalogError('服务请求过于频繁，请稍后再试。', 429)
                    if status < 200 or status >= 300:
                        raise CatalogError(f'服务暂时无法返回模型列表（HTTP {status}）。', 502)
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 1024 * 1024:
                            raise CatalogError('模型列表响应过大；请手动填写模型名称。', 502)
                        if time.monotonic() - started > 25:
                            raise CatalogError('获取模型列表超时，请稍后重试。', 504)
                try:
                    payload = json.loads(raw)
                except (ValueError, UnicodeError):
                    raise CatalogError('服务返回的不是有效模型列表；请检查基础地址，或手动填写模型名称。', 502) from None
                if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
                    raise CatalogError('服务未返回受支持的模型列表格式；可以手动填写模型名称。', 502)
                for item in payload['data']:
                    if not isinstance(item, dict):
                        continue
                    model_id = item.get('id')
                    if not isinstance(model_id, str) or not model_id.strip() or len(model_id) > 200 or any(ord(c) < 32 for c in model_id):
                        continue
                    name = item.get('display_name') or item.get('name') or model_id
                    models[model_id] = CatalogModel(id=model_id, name=str(name)[:200])
                    if len(models) >= 500:
                        truncated = True
                        break
                if truncated or not payload.get('has_more'):
                    break
                cursor = payload.get('last_id') or (payload['data'][-1].get('id') if payload['data'] and isinstance(payload['data'][-1], dict) else None)
                if not isinstance(cursor, str) or not cursor or cursor in cursors or len(cursor) > 200 or page == 2:
                    truncated = True
                    break
                cursors.add(cursor)
    except httpx.TimeoutException:
        raise CatalogError('获取模型列表超时，请检查服务地址与网络后重试。', 504) from None
    except httpx.HTTPError:
        raise CatalogError('无法连接模型服务，请检查服务地址、网络或证书。', 502) from None
    return ModelCatalogResponse(models=sorted(models.values(), key=lambda row: row.id.casefold()), truncated=truncated)
