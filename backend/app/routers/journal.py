from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import JournalListItem, JournalResponse, JournalUpsert
from app.services import journal_service

router = APIRouter(prefix="/journal", tags=["journal"])


@router.get("", response_model=list[JournalListItem])
def list_entries(limit: int = Query(30, ge=1, le=200), db: Session = Depends(get_db)):
    entries = journal_service.list_entries(db, limit)
    return [
        JournalListItem(
            id=e.id,
            date=e.date,
            preview=(e.content or "")[:120],
            mood=e.mood,
            updated_at=e.updated_at,
        )
        for e in entries
    ]


@router.get("/today", response_model=JournalResponse)
def get_today(db: Session = Depends(get_db)):
    entry = journal_service.get_entry(db, date_type.today())
    if entry is None:
        raise HTTPException(status_code=404, detail="今天还没有日记")
    return entry


@router.get("/{day}", response_model=JournalResponse)
def get_entry(day: date_type, db: Session = Depends(get_db)):
    entry = journal_service.get_entry(db, day)
    if entry is None:
        raise HTTPException(status_code=404, detail="该日没有日记")
    return entry


@router.put("/{day}", response_model=JournalResponse)
def upsert_entry(day: date_type, payload: JournalUpsert, db: Session = Depends(get_db)):
    return journal_service.upsert_entry(db, day, payload)


@router.delete("/{day}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(day: date_type, db: Session = Depends(get_db)):
    if not journal_service.delete_entry(db, day):
        raise HTTPException(status_code=404, detail="该日没有日记")
