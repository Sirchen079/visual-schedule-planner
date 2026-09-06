# ruff: noqa: B008
# FastAPI Depends/Query defaults match the existing server route convention.
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from zhishi.domain.ledger import service
from zhishi.domain.ledger.schemas import (
    Currency,
    Direction,
    EntryCreate,
    EntryPage,
    EntryRead,
    EntryReplace,
    LedgerSummary,
    VersionInput,
)
from zhishi.server.deps import get_db

router = APIRouter(prefix="/api/ledger", tags=["ledger"])


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except service.LedgerConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("", response_model=EntryPage)
def list_entries(start: date | None = None, end: date | None = None,
                 currency: Currency | None = None, account: str | None = None,
                 direction: Direction | None = None, query: str = "", deleted: bool = False,
                 limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                 db: Session = Depends(get_db)):
    return _call(service.list_entries, db, start=start, end=end, currency=currency,
                 account=account, direction=direction, query=query, deleted=deleted,
                 limit=limit, offset=offset)


@router.get("/summary", response_model=LedgerSummary)
def summary(start: date, end: date, currency: Currency | None = None,
            account: str | None = None, db: Session = Depends(get_db)):
    return _call(service.summary, db, start, end, currency=currency, account=account)


@router.post("", response_model=EntryRead, status_code=201)
def create_entry(payload: EntryCreate, db: Session = Depends(get_db)):
    return service.to_read(_call(service.create_entry, db, payload))


@router.get("/{entry_id}", response_model=EntryRead)
def get_entry(entry_id: int, db: Session = Depends(get_db)):
    return service.to_read(_call(service.get_entry, db, entry_id))


@router.put("/{entry_id}", response_model=EntryRead)
def replace_entry(entry_id: int, payload: EntryReplace, db: Session = Depends(get_db)):
    return service.to_read(_call(service.replace_entry, db, entry_id, payload, payload.version))


@router.delete("/{entry_id}", response_model=EntryRead)
def delete_entry(entry_id: int, version: int = Query(ge=1), db: Session = Depends(get_db)):
    return service.to_read(_call(service.delete_entry, db, entry_id, version))


@router.post("/{entry_id}/restore", response_model=EntryRead)
def restore_entry(entry_id: int, payload: VersionInput, db: Session = Depends(get_db)):
    return service.to_read(_call(service.restore_entry, db, entry_id, payload.version))
