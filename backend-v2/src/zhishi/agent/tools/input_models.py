"""Bounded, provider-compatible schemas for composite tool arguments."""
from typing import Annotated, Literal, NotRequired

from pydantic import ConfigDict, Field, TypeAdapter, with_config
from typing_extensions import TypedDict

Title = Annotated[str, Field(min_length=1, max_length=200)]
PositiveId = Annotated[int, Field(gt=0, strict=True)]
ClockTime = Annotated[str, Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')]
RequestKey = Annotated[str, Field(min_length=1, max_length=128)]
IdBatch = Annotated[list[PositiveId], Field(min_length=1, max_length=100)]


@with_config(ConfigDict(extra='forbid'))
class SubtaskInput(TypedDict):
    title: Title
    estimated_minutes: NotRequired[Annotated[int, Field(ge=1, le=1440)] | None]


@with_config(ConfigDict(extra='forbid'))
class AssignmentInput(TypedDict):
    task_id: PositiveId
    start: ClockTime
    end: ClockTime
    title: NotRequired[Title]
    estimated_minutes: NotRequired[Annotated[int, Field(ge=1, le=1440)]]


@with_config(ConfigDict(extra='forbid'))
class TimetableInput(TypedDict):
    title: Title
    weekday: Annotated[int, Field(ge=1, le=7)]
    periods: Annotated[list[Annotated[int, Field(ge=1, le=12)]], Field(min_length=1, max_length=12)]
    start_week: Annotated[int, Field(ge=1, le=104)]
    end_week: Annotated[int, Field(ge=1, le=104)]
    week_kind: NotRequired[Literal['range', 'odd', 'even']]
    location: NotRequired[Annotated[str, Field(max_length=500)]]


@with_config(ConfigDict(extra='forbid'))
class ResourceInput(TypedDict):
    title: Title
    url: Annotated[str, Field(pattern=r'^https?://', max_length=4096)]
    notes: NotRequired[Annotated[str, Field(max_length=10000)]]


@with_config(ConfigDict(extra='forbid'))
class WorkStepInput(TypedDict):
    title: Title
    status: NotRequired[Literal['待办', '进行中', '已完成', '受阻']]
    evidence_call_ids: NotRequired[Annotated[list[str], Field(max_length=12)]]


@with_config(ConfigDict(extra='forbid'))
class PlanStepInput(TypedDict):
    action: Title
    tool: Annotated[str, Field(min_length=1, max_length=100)]
    reason: NotRequired[Annotated[str, Field(min_length=1, max_length=1000)]]
    args_preview: NotRequired[str]


def validate_items(kind, values, limit=100):
    return TypeAdapter(Annotated[list[kind], Field(max_length=limit)]).validate_python(values)
