# src/zhishi/domain/journal/service.py
"""日记：一天一篇（date upsert）。"""
from __future__ import annotations
from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session
from zhishi.domain.models import JournalEntry


def upsert(db: Session, day: date, *, content: str = "", mood: str | None = None) -> JournalEntry:
    entry = db.scalar(select(JournalEntry).where(JournalEntry.date == day))
    if entry is None:
        entry = JournalEntry(date=day, content=content, mood=mood)
        db.add(entry)
    else:
        entry.content, entry.mood = content, mood
    db.commit()
    db.refresh(entry)
    return entry


def get_entry(db: Session, day: date) -> JournalEntry | None:
    return db.scalar(select(JournalEntry).where(JournalEntry.date == day))


def list_entries(db: Session, limit: int = 50) -> list[JournalEntry]:
    return list(db.scalars(select(JournalEntry).order_by(JournalEntry.date.desc()).limit(limit)))


def delete_entry(db: Session, day: date) -> None:
    entry = get_entry(db, day)
    if entry is not None:
        db.delete(entry)
        db.commit()
