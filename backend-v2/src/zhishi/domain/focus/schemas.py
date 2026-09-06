from __future__ import annotations
from pydantic import BaseModel


class TimerStart(BaseModel):
    task_id: int | None = None
    task_title: str = ""
    kind: str = "focus"  # focus/break
