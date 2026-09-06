/* eslint-disable */
/** 知时 SSE 事件契约 v1 —— 由 scripts/export_contracts.py 自动生成，勿手改。
 * 权威定义：src/zhishi/agent/events.py；每帧格式：event: <type>\ndata: <json>\n\n
 * 判别联合按 type 字段收窄。 */

export interface RunStarted {
  /** 协议版本 */
  v: number;
  type: "run_started";
  run_id: string;
  conversation_id: number;
}

export interface StageChanged {
  /** 协议版本 */
  v: number;
  type: "stage_changed";
  stage: "preparing" | "connecting" | "waiting_first_token" | "streaming_reasoning" | "streaming_text" | "executing_tools" | "awaiting_approval" | "finalizing";
}

export interface Heartbeat {
  /** 协议版本 */
  v: number;
  type: "heartbeat";
  elapsed_ms: number;
  stage: string;
  last_event_age_ms: number;
}

export interface TextDelta {
  /** 协议版本 */
  v: number;
  type: "text_delta";
  delta: string;
}

export interface ReasoningDelta {
  /** 协议版本 */
  v: number;
  type: "reasoning_delta";
  delta: string;
}

export interface ToolCallStarted {
  /** 协议版本 */
  v: number;
  type: "tool_call_started";
  call_id: string;
  tool: string;
  args_preview: string;
}

export interface ToolCallArgsDelta {
  /** 协议版本 */
  v: number;
  type: "tool_call_args_delta";
  call_id: string;
  args_delta: string;
}

export interface ToolCallResult {
  /** 协议版本 */
  v: number;
  type: "tool_call_result";
  call_id: string;
  ok: boolean;
  result_preview: string;
  duration_ms: number;
}

export interface ToolApprovalRequested {
  /** 协议版本 */
  v: number;
  type: "tool_approval_requested";
  action_id: number;
  tool: string;
  args: Record<string, unknown>;
  preview: string;
  grant_available?: boolean;
}

export interface ToolApprovalResolved {
  /** 协议版本 */
  v: number;
  type: "tool_approval_resolved";
  action_id: number;
  outcome: "approved" | "denied" | "expired";
}

export interface PlanCard {
  /** 协议版本 */
  v: number;
  type: "plan_card";
  plan_id: number;
  title: string;
  steps: Array<Record<string, unknown>>;
}

export interface WorkPlanUpdated {
  /** 协议版本 */
  v: number;
  type: "work_plan_updated";
  steps: Array<Record<string, unknown>>;
}

export interface SubagentStarted {
  /** 协议版本 */
  v: number;
  type: "subagent_started";
  subagent_id: string;
  description: string;
}

export interface SubagentDelta {
  /** 协议版本 */
  v: number;
  type: "subagent_delta";
  subagent_id: string;
  delta: string;
}

export interface SubagentCompleted {
  /** 协议版本 */
  v: number;
  type: "subagent_completed";
  subagent_id: string;
  ok: boolean;
  summary: string;
}

export interface UsageUpdated {
  /** 协议版本 */
  v: number;
  type: "usage_updated";
  tokens_in: number;
  tokens_out: number;
  cost_estimate: number;
  model: string;
}

export interface RunCompleted {
  /** 协议版本 */
  v: number;
  type: "run_completed";
  run_id: string;
  usage: Record<string, unknown>;
  elapsed_ms: number;
  done_reason: string;
}

export interface RunError {
  /** 协议版本 */
  v: number;
  type: "run_error";
  run_id: string;
  message: string;
  retryable: boolean;
}

export interface Done {
  /** 协议版本 */
  v: number;
  type: "done";
  run_id: string;
}

export type SSEEvent =
  | RunStarted
  | StageChanged
  | Heartbeat
  | TextDelta
  | ReasoningDelta
  | ToolCallStarted
  | ToolCallArgsDelta
  | ToolCallResult
  | ToolApprovalRequested
  | ToolApprovalResolved
  | PlanCard
  | WorkPlanUpdated
  | SubagentStarted
  | SubagentDelta
  | SubagentCompleted
  | UsageUpdated
  | RunCompleted
  | RunError
  | Done;
