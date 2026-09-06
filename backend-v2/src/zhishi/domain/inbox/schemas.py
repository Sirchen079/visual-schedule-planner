from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from zhishi.domain.ledger.schemas import EntryData
from zhishi.domain.schedule.schemas import EventCreate
from zhishi.domain.tasks.schemas import TaskCreate


class TaskDraft(TaskCreate):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    priority: Literal["high", "medium", "low"] = "medium"
    status: Literal["todo"] = "todo"
    estimated_minutes: int | None = Field(default=None, gt=0)
    recur_rule: Literal["none", "daily", "weekdays", "weekly", "monthly"] = "none"
    recur_interval: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def valid_schedule(self):
        if self.due_time and self.due_date is None:
            raise ValueError("截止时间须有对应的截止日期")
        if self.recur_rrule:
            from dateutil.rrule import rrulestr
            rrulestr(self.recur_rrule)
        return self


class EventDraft(EventCreate):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def valid_times(self):
        if bool(self.start_time) != bool(self.end_time):
            raise ValueError("日程起止时间须同时提供，或同时留空表示全天")
        if self.start_time and self.end_time <= self.start_time:
            raise ValueError("结束时间必须晚于开始时间；跨天事项请分日整理")
        if self.recur_rrule:
            from dateutil.rrule import rrulestr
            rrulestr(self.recur_rrule)
        return self


class LedgerDraft(EntryData):
    source_file_id: None = None
    source_excerpt: Literal[""] = ""


class TaskProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["task"]
    data: TaskDraft


class EventProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["event"]
    data: EventDraft


class LedgerProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["ledger"]
    data: LedgerDraft


Proposal = Annotated[TaskProposal | EventProposal | LedgerProposal, Field(discriminator="kind")]


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_file_id: int | None = Field(default=None, gt=0, description="附件上下文提供的材料编号；纯文字输入留空。不是文件名或路径。")
    item_key: str = Field(min_length=1, max_length=120, description="同一原文事项的稳定位置；单笔收据用 receipt-total，多行用 p1-row2。重试不要换键。")
    source_excerpt: str = Field(min_length=1, max_length=8000, description="支持此条目的原文摘录；保留实际日期、金额等依据，不能编造。")
    uncertainty: str = Field(default="", max_length=2000)
    proposal: Proposal


class CaptureBatch(BaseModel):
    capture_key: str = Field(min_length=1, max_length=80)
    items: list[Candidate] = Field(min_length=1, max_length=30)


class Revision(BaseModel):
    version: int = Field(ge=1)
    proposal: Proposal
    uncertainty: str = Field(default="", max_length=2000)


class VersionInput(BaseModel):
    version: int = Field(ge=1)


class InboxRead(BaseModel):
    id: int
    source_file_id: int | None
    source_name: str
    source_excerpt: str
    item_key: str
    proposal: Proposal
    uncertainty: str
    status: Literal["pending", "applied", "rejected"]
    version: int
    target_id: int | None
    target_state: Literal["active", "deleted", "missing"] | None
    created_at: datetime
    updated_at: datetime


class InboxPage(BaseModel):
    items: list[InboxRead]
    total: int
