"""Standalone /ai/web-services router; app owner must register router explicitly.

GET/PUT root: nonsecret config. PUT/DELETE /credentials/tavily: keyring only.
POST /search and /fetch: explicit user requests against saved config; optional
provider selects builtin/tavily/mcp for one request, without mutating defaults.
MCP input fields are literal names; output paths use dot-separated keys/indices.
Example fetch: url_argument='urls', url_as_list=true,
content_path='results.0.raw_content'. No arbitrary arguments or new servers.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, SecretStr
from sqlalchemy.orm import Session

from zhishi.adapters import web_services as service
from zhishi.server.deps import get_db

router = APIRouter(prefix="/ai/web-services", tags=["web-services"])
DB = Annotated[Session, Depends(get_db)]


class WebServicesOut(service.StrictModel):
    config: service.WebServicesConfig
    tavily_has_api_key: bool


class CredentialBody(service.StrictModel):
    api_key: SecretStr = Field(min_length=1, max_length=4096)


class CredentialOut(service.StrictModel):
    tavily_has_api_key: bool


class SearchBody(service.StrictModel):
    query: str = Field(min_length=1, max_length=service.MAX_QUERY_CHARS)
    max_results: int = Field(default=5, ge=1, le=service.MAX_RESULTS)
    provider: service.Provider | None = None


class FetchBody(service.StrictModel):
    url: str = Field(min_length=1, max_length=service.MAX_URL_CHARS)
    provider: service.Provider | None = None


class SearchHit(service.StrictModel):
    title: str = Field(max_length=300)
    url: str = Field(max_length=service.MAX_URL_CHARS)
    description: str = Field(max_length=service.MAX_DESCRIPTION_CHARS)


class SearchError(service.StrictModel):
    error: str = Field(max_length=300)


class FetchOut(service.StrictModel):
    ok: bool
    url: str
    content: str | None = Field(default=None, max_length=service.MAX_CONTENT_CHARS)
    error: str | None = Field(default=None, max_length=300)


@router.get("", response_model=WebServicesOut)
def get_web_services(db: DB):
    try:
        return WebServicesOut(config=service.get_config(db),
                              tavily_has_api_key=service.has_tavily_key(db))
    except service.WebServiceError as exc:
        raise HTTPException(400, str(exc)) from None


@router.put("", response_model=WebServicesOut)
def put_web_services(body: service.WebServicesConfig, db: DB):
    try:
        service.save_config(db, body)
    except service.WebServiceError as exc:
        raise HTTPException(400, str(exc)) from None
    return get_web_services(db)


@router.put("/credentials/tavily", response_model=CredentialOut)
def put_tavily_key(body: CredentialBody, db: DB):
    try:
        service.save_tavily_key(db, body.api_key.get_secret_value())
    except service.WebServiceError as exc:
        raise HTTPException(400, str(exc)) from None
    return CredentialOut(tavily_has_api_key=service.has_tavily_key(db))


@router.delete("/credentials/tavily", response_model=CredentialOut)
def delete_tavily_key(db: DB):
    service.delete_tavily_key(db)
    return CredentialOut(tavily_has_api_key=False)


@router.post("/search", response_model=list[SearchHit | SearchError])
def search_web(body: SearchBody, db: DB):
    return service.search(db, body.query, limit=body.max_results, provider=body.provider)


@router.post("/fetch", response_model=FetchOut, response_model_exclude_none=True)
def fetch_web(body: FetchBody, db: DB):
    try:
        return FetchOut(ok=True, url=body.url,
                        content=service.fetch(db, body.url, provider=body.provider))
    except service.WebServiceError as exc:
        return FetchOut(ok=False, url=body.url, error=str(exc))
