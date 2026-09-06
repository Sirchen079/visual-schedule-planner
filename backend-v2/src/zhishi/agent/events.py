# src/zhishi/agent/events.py
"""SSE 事件契约 v1（19 个事件）。前端契约的单一数据源：
scripts/export_contracts.py 由此生成 docs/contracts/events.schema.json。
任何变更必须重导出并更新快照测试。"""
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field


class _Frame(BaseModel):
    v: int = Field(default=1, description="协议版本")


class RunStarted(_Frame):
    type: Literal["run_started"] = "run_started"
    run_id: str
    conversation_id: int


class StageChanged(_Frame):
    type: Literal["stage_changed"] = "stage_changed"
    stage: Literal["preparing", "connecting", "waiting_first_token", "streaming_reasoning",
                    "streaming_text", "executing_tools", "awaiting_approval", "finalizing"]


class Heartbeat(_Frame):
    type: Literal["heartbeat"] = "heartbeat"
    elapsed_ms: int
    stage: str
    last_event_age_ms: int


class TextDelta(_Frame):
    type: Literal["text_delta"] = "text_delta"
    delta: str


class ReasoningDelta(_Frame):
    type: Literal["reasoning_delta"] = "reasoning_delta"
    delta: str


class ToolCallStarted(_Frame):
    type: Literal["tool_call_started"] = "tool_call_started"
    call_id: str
    tool: str
    args_preview: str


class ToolCallArgsDelta(_Frame):
    type: Literal["tool_call_args_delta"] = "tool_call_args_delta"
    call_id: str
    args_delta: str


class ToolCallResult(_Frame):
    type: Literal["tool_call_result"] = "tool_call_result"
    call_id: str
    ok: bool
    result_preview: str
    duration_ms: int


class ToolApprovalRequested(_Frame):
    type: Literal["tool_approval_requested"] = "tool_approval_requested"
    action_id: int
    tool: str
    args: dict[str, Any]
    preview: str
    grant_available: bool = True


class ToolApprovalResolved(_Frame):
    type: Literal["tool_approval_resolved"] = "tool_approval_resolved"
    action_id: int
    outcome: Literal["approved", "denied", "expired"]


class PlanCard(_Frame):
    type: Literal["plan_card"] = "plan_card"
    plan_id: int
    title: str
    steps: list[dict[str, Any]]


class WorkPlanUpdated(_Frame):
    type: Literal["work_plan_updated"] = "work_plan_updated"
    steps: list[dict[str, Any]]


class SubagentStarted(_Frame):
    type: Literal["subagent_started"] = "subagent_started"
    subagent_id: str
    description: str


class SubagentDelta(_Frame):
    type: Literal["subagent_delta"] = "subagent_delta"
    subagent_id: str
    delta: str


class SubagentCompleted(_Frame):
    type: Literal["subagent_completed"] = "subagent_completed"
    subagent_id: str
    ok: bool
    summary: str


class UsageUpdated(_Frame):
    type: Literal["usage_updated"] = "usage_updated"
    tokens_in: int
    tokens_out: int
    cost_estimate: float
    model: str


class RunCompleted(_Frame):
    type: Literal["run_completed"] = "run_completed"
    run_id: str
    usage: dict[str, Any]
    elapsed_ms: int
    done_reason: str


class RunError(_Frame):
    type: Literal["run_error"] = "run_error"
    run_id: str
    message: str
    retryable: bool


class Done(_Frame):
    type: Literal["done"] = "done"
    run_id: str


ALL_EVENTS: list[type[_Frame]] = [
    RunStarted, StageChanged, Heartbeat, TextDelta, ReasoningDelta,
    ToolCallStarted, ToolCallArgsDelta, ToolCallResult,
    ToolApprovalRequested, ToolApprovalResolved, PlanCard, WorkPlanUpdated,
    SubagentStarted, SubagentDelta, SubagentCompleted, UsageUpdated,
    RunCompleted, RunError, Done,
]


def schema_union() -> dict:
    """导出为 oneOf 判别联合的 JSON Schema（事件模型均扁平，各自自包含）。"""
    definitions = {m.__name__: m.model_json_schema(ref_template="#/definitions/{model}")
                   for m in ALL_EVENTS}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "zhishi SSE events v1",
        "oneOf": [{"$ref": f"#/definitions/{name}"} for name in definitions],
        "definitions": definitions,
    }
