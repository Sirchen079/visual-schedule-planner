from __future__ import annotations
from pydantic import BaseModel


class HabitCreate(BaseModel):
    name: str
    notes: str = ""
    period: str = "daily"     # daily/weekly
    target_count: int = 1
    color: str = "#22c55e"
