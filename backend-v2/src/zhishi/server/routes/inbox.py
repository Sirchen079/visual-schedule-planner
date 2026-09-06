# ruff: noqa: B008
# FastAPI dependency defaults follow the existing v2 route convention.
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from zhishi.domain.inbox import service
from zhishi.domain.inbox.schemas import CaptureBatch, InboxPage, InboxRead, Revision, VersionInput
from zhishi.server.deps import get_db

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


def call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except service.InboxConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("", response_model=list[InboxRead], status_code=201)
def capture(batch: CaptureBatch, db: Session = Depends(get_db)):
    return call(service.capture, db, batch)


@router.get("", response_model=InboxPage)
def list_items(status: Literal["pending", "applied", "rejected"] | None = "pending",
               source_file_id: int | None = None, limit: int = Query(50, ge=1, le=200),
               offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    return call(service.list_items, db, status=status, source_file_id=source_file_id,
                limit=limit, offset=offset)


@router.get("/{item_id}", response_model=InboxRead)
def get_item(item_id: int, db: Session = Depends(get_db)):
    return service.to_read(db, call(service.get_item, db, item_id))


@router.put("/{item_id}", response_model=InboxRead)
def revise(item_id: int, revision: Revision, db: Session = Depends(get_db)):
    return call(service.revise, db, item_id, revision)


@router.post("/{item_id}/apply", response_model=InboxRead)
def apply_item(item_id: int, payload: VersionInput, db: Session = Depends(get_db)):
    return call(service.apply_item, db, item_id, payload.version)


@router.post("/{item_id}/reject", response_model=InboxRead)
def reject(item_id: int, payload: VersionInput, db: Session = Depends(get_db)):
    return call(service.reject, db, item_id, payload.version)
