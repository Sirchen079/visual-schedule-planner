from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from zhishi.domain.research.schemas import PlanRead


class FollowupRead(BaseModel):
    id: int
    project_id: int
    kind: Literal['replan', 'needs_window', 'needs_plan', 'completed', 'needs_review']
    title: str
    body: str
    status: Literal['pending', 'snoozed', 'applying', 'applied', 'resolved', 'dismissed', 'waiting']
    version: int
    plan_id: int | None
    snoozed_until: datetime | None
    error: str
    created_at: datetime
    updated_at: datetime
    target_path: str
    plan: PlanRead | None = None


class FollowupResponse(BaseModel):
    version: int = Field(ge=1)
    snooze_until: datetime | None = None


class FollowupCheck(BaseModel):
    project_id: int = Field(gt=0)


class FollowupPreferences(BaseModel):
    enabled: bool


class FollowupStatus(BaseModel):
    enabled: bool
    autopilot_enabled: bool
    autonomy: str
    last_scan: dict | None
