# src/zhishi/domain/library/schemas.py
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel


class LinkCreate(BaseModel):
    title: str
    url: str
    notes: str = ""
    resource_type: str = "link"  # link/video
