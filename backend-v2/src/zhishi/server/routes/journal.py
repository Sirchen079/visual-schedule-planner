from datetime import date, datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from zhishi.domain.journal import service
from zhishi.domain.journal.schemas import JournalUpsert
from zhishi.server.deps import get_db

router = APIRouter(prefix="/api/journal", tags=["journal"])


# ---- typed 响应（openapi 从空 schema 变 $ref，字段与实际返回形状一致） ----

class JournalEntryOut(BaseModel):
    id: int
    date: str                       # YYYY-MM-DD
    content: str
    mood: str | None = None
    created_at: datetime
    updated_at: datetime


@router.get("/today", response_model=JournalEntryOut | None)
def today_entry(db: Session = Depends(get_db)):
    return _entry_dict(service.get_entry(db, date.today()))


@router.get("", response_model=list[JournalEntryOut])
def list_entries(limit: int = 50, db: Session = Depends(get_db)):
    return [_entry_dict(e) for e in service.list_entries(db, limit=limit)]


@router.get("/{day}", response_model=JournalEntryOut | None)
def get_entry(day: date, db: Session = Depends(get_db)):
    return _entry_dict(service.get_entry(db, day))


@router.put("/{day}", response_model=JournalEntryOut)
def upsert_entry(day: date, payload: JournalUpsert, db: Session = Depends(get_db)):
    e = service.upsert(db, day, content=payload.content, mood=payload.mood)
    return _entry_dict(e)


@router.delete("/{day}", status_code=204)
def delete_entry(day: date, db: Session = Depends(get_db)) -> None:
    service.delete_entry(db, day)


def _entry_dict(e):
    if e is None:
        return None
    return {"id": e.id, "date": e.date.isoformat(), "content": e.content, "mood": e.mood,
            "created_at": e.created_at, "updated_at": e.updated_at}
