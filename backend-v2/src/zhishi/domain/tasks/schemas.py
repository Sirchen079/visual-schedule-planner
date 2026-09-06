from __future__ import annotations
from datetime import datetime
from typing import Annotated
from pydantic import BaseModel, Field

ReminderOffsets = Annotated[list[Annotated[int, Field(strict=True, ge=0, le=525600)]], Field(max_length=20)]


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    notes: str = ""
    due_date: datetime | None = None
    due_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    remind_offsets: ReminderOffsets = Field(default_factory=list)
    priority: str = "medium"
    status: str = "todo"
    start_date: datetime | None = None
    recur_rule: str = "none"
    recur_interval: int = 1
    recur_rrule: str | None = None
    estimated_minutes: int | None = None
    tag_names: list[str] = Field(default_factory=list)


class SubtaskRead(BaseModel):
    """子任务读取面：随 TaskRead 内嵌返回，REST 消费者可渲染子任务清单。"""
    id: int
    title: str
    done: bool
    estimated_minutes: int | None
    completed_at: datetime | None


class TagOut(BaseModel):
    """标签项（GET /api/tasks/tags 实形）。"""
    id: int
    name: str
    color: str


class TaskRead(BaseModel):
    id: int
    title: str
    notes: str
    due_date: datetime | None
    due_time: str | None
    remind_offsets: list[int]
    priority: str
    status: str
    progress: int
    start_date: datetime | None
    recur_rule: str
    recur_interval: int
    recur_rrule: str | None
    estimated_minutes: int | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    subtasks: list[SubtaskRead] = []

    model_config = {"from_attributes": True}


class TaskUpdate(BaseModel):
    title: str | None = None
    notes: str | None = None
    due_date: datetime | None = None
    due_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    remind_offsets: ReminderOffsets | None = None
    priority: str | None = None
    status: str | None = None
    start_date: datetime | None = None
    recur_rule: str | None = None
    recur_interval: int | None = None
    recur_rrule: str | None = None
    estimated_minutes: int | None = None
    tag_names: list[str] | None = None
