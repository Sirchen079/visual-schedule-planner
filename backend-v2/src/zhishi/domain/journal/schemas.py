# src/zhishi/domain/journal/schemas.py
from __future__ import annotations
from pydantic import BaseModel


class JournalUpsert(BaseModel):
    content: str = ""
    mood: str | None = None
