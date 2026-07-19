"""日记：一天一篇（date upsert），供日记视图与幕僚上下文使用。"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import JournalEntry
from app.schemas import JournalUpsert


def upsert_entry(db: Session, day: date, payload: JournalUpsert) -> JournalEntry:
    stmt = select(JournalEntry).where(JournalEntry.date == day)
    entry = db.execute(stmt).scalar_one_or_none()
    if entry is None:
        entry = JournalEntry(date=day, content=payload.content, mood=payload.mood)
        db.add(entry)
    else:
        entry.content = payload.content
        entry.mood = payload.mood
    db.commit()
    db.refresh(entry)
    return entry


def get_entry(db: Session, day: date) -> JournalEntry | None:
    stmt = select(JournalEntry).where(JournalEntry.date == day)
    return db.execute(stmt).scalar_one_or_none()


def list_entries(db: Session, limit: int = 30) -> list[JournalEntry]:
    stmt = (
        select(JournalEntry)
        .order_by(JournalEntry.date.desc())
        .limit(max(1, min(limit, 200)))
    )
    return list(db.execute(stmt).scalars().all())


def delete_entry(db: Session, day: date) -> bool:
    entry = get_entry(db, day)
    if entry is None:
        return False
    db.delete(entry)
    db.commit()
    return True
