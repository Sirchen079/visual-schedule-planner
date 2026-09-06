# src/zhishi/domain/goals/schemas.py
from __future__ import annotations
from datetime import date
from pydantic import BaseModel


class GoalCreate(BaseModel):
    title: str
    notes: str = ""
    start_date: date | None = None
    end_date: date | None = None


class KeyResultCreate(BaseModel):
    title: str
    kind: str = "manual"          # manual/tag_task_count/habit_checkins
    target_value: float = 100.0
    unit: str = ""
    link: str = ""
