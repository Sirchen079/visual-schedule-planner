/**
 * 管理对话执行状态并归约 SSE 事件。
 * 工具审批完成后通过 resume 续接执行；只有 done 事件关闭当前流。
 * 同一会话只允许一个执行，恢复流保留现有文本与审批记录。
 */
import { defineStore } from 'pinia'
import type { SSEEvent } from '../api/contracts/events'
import type { components } from '../api/contracts/rest'
import { http } from '../api/http'
import type { ConversationState } from '../api/sessions'
import { SSERequestError, streamSSE } from '../api/sse'

export type RunPhase =
  | 'idle'
  | 'streaming'
  | 'awaiting_approval'
  | 'completed'
  | 'error'
  | 'cancelled'

/** stage_changed 八阶段 → 中文标签 */
export const STAGE_LABELS = {
  preparing: '准备中',
  connecting: '连接中',
  waiting_first_token: '等待首个 token',
  streaming_reasoning: '思考中',
  streaming_text: '输出中',
  executing_tools: '执行工具',
  awaiting_approval: '等待审批',
  finalizing: '收尾中',
} as const

export type StageKey = keyof typeof STAGE_LABELS

export interface TextSegment {
  kind: 'text' | 'reasoning'
  content: string
  /** 事件到达序（时间线合并排序用） */
  seq: number
}

export interface ToolCallItem {
  callId: string
  tool: string
  argsPreview: string
  status: 'running' | 'ok' | 'error' | 'pending' | 'interrupted'
  resultPreview: string | null
  durationMs: number | null
  seq: number
}

export interface PendingApproval {
  actionId: number
  tool: string
  args: Record<string, unknown>
  preview: string
  grantAvailable: boolean
  busy?: boolean
  outcome: 'approved' | 'denied' | 'expired' | null
}

export interface PlanCardItem {
  planId: number
  title: string
  steps: Array<Record<string, unknown>>
}

export interface SubagentItem {
  subagentId: string
  description: string
  delta: string
  summary: string | null
  ok: boolean | null
}

export interface UsageSnapshot {
  tokensIn: number
  tokensOut: number
  costEstimate: number
  model: string
}

export interface RunState {
  renderedRunIds: string[]
  streamOpen: boolean
  connecting: boolean
  phase: RunPhase
  runId: string | null
  conversationId: number | null
  stage: StageKey | null
  lastHeartbeat: { elapsedMs: number; at: number } | null
  /** 本 run 开始时刻（本地时钟，心跳前估算「已进行」用） */
  startedAt: number | null
  /** segments/toolCalls 的流内顺序号（时间线按此合并排序） */
  nextSeq: number
  /** text/reasoning 分段累积（工具调用会把正文切成多段） */
  segments: TextSegment[]
  toolCalls: ToolCallItem[]
  pendingApproval: PendingApproval | null
  /**
   * 审批账目：本 run 内请求过的全部审批。协议上 run 在每个审批门前暂停，
   * pendingApproval 只持有当前待决的一个；账目则累积历史请求，供日历把多个
   * create_event 幽灵块并存投影（批准未落地/待决的都留在纸面上）。
   * 恢复流保留审批预览，直到对应日程加载；新消息清空旧预览。
   */
  approvalLedger: PendingApproval[]
  planCard: PlanCardItem | null
  workPlanSteps: Array<Record<string, unknown>>
  subagents: SubagentItem[]
  usage: UsageSnapshot | null
  /** 本地回显：刚发送的用户消息（新会话首条消息时列表里还没有它） */
  sentMessage: string | null
  /** run_completed 终态预告（done 前不落定 UI） */
  runCompleted: { doneReason: string; elapsedMs: number } | null
  error: { message: string; retryable: boolean } | null
  /** 409：同会话已有 run 在跑 */
  conflict: boolean
  /** 当前流是审批后续跑的 resume 新流（run_started 时不清空内容） */
  resuming: boolean
  /**
   * 信息级微文本（非错误）：consumed 幂等提示、ready_to_resume=false 的「同批还有 N 项待决」。
   * 与 error 分开计数——按任务要求这些是「信息」不是「错误」，错误计数/重试语义不被污染。
   */
  notice: string | null
}

export function initialRunState(): RunState {
  return {
    renderedRunIds: [],
    streamOpen: false,
    connecting: false,
    phase: 'idle',
    runId: null,
    conversationId: null,
    stage: null,
    lastHeartbeat: null,
    startedAt: null,
    nextSeq: 1,
    segments: [],
    toolCalls: [],
    pendingApproval: null,
    approvalLedger: [],
    planCard: null,
    workPlanSteps: [],
    subagents: [],
    usage: null,
    sentMessage: null,
    runCompleted: null,
    error: null,
    conflict: false,
    resuming: false,
    notice: null,
  }
}

/** resume 400 拒绝体里的一条待批项 = 生成 ResumeBlockedPending 的 UI camelCase 投影。 */
export interface ResumeBlockedItem {
  actionId: number
  tool: string
}

/**
 * 从传输层错误里识别 resume 拒绝体 ResumeBlockedOut：{pending:[{action_id,tool_name}],consumed,message}。
 * wire 形状取生成 components.schemas.ResumeBlockedPending（运行时仍逐字段校验，防脏数据）。
 * 命中（400 且 pending 非空）返回待批清单，否则返回空数组。纯函数便于单测。
 */
export function resumeBlockedPending(err: SSERequestError): ResumeBlockedItem[] {
  if (err.status !== 400) return []
  const d = err.body as { pending?: components['schemas']['ResumeBlockedPending'][] } | undefined
  if (!d || typeof d !== 'object' || !Array.isArray(d.pending)) return []
  const out: ResumeBlockedItem[] = []
  for (const x of d.pending) {
    if (x && typeof x === 'object') {
      const p = x as { action_id?: unknown; tool_name?: unknown }
      if (typeof p.action_id === 'number' && typeof p.tool_name === 'string') {
        out.push({ actionId: p.action_id, tool: p.tool_name })
      }
    }
  }
  return out
}

/** 待批清单 → 可读文案（同工具多项聚合计数）。 */
export function formatResumeBlocked(pending: ResumeBlockedItem[]): string {
  const counts = new Map<string, number>()
  for (const p of pending) counts.set(p.tool, (counts.get(p.tool) ?? 0) + 1)
  const parts = [...counts].map(([tool, n]) => (n > 1 ? `${tool}×${n}` : tool))
  return `本轮仍有 ${pending.length} 项待批操作（${parts.join('、')}），请先批准或拒绝全部审批卡，知时才能继续。`
}

/** 审批结果来自 ActionResolveOut。ready_to_resume 为 false 时等待其他审批；
 * 字段缺失时尝试恢复，由服务端检查是否仍有待决操作。 */
export type ActionResolveResult = components['schemas']['ActionResolveOut']

/**
 * resume 400 且 consumed=true：该审批批次已被 resume 消费（重复 resume 的幂等拒绝，
 * ）。按信息处理、不计错误。纯函数便于单测。
 */
export function resumeConsumed(err: SSERequestError): boolean {
  if (err.status !== 400) return false
  const d = err.body as Pick<components['schemas']['ResumeBlockedOut'], 'consumed'> | undefined
  return !!d && typeof d === 'object' && d.consumed === true
}

/** 取下一个顺序号（applyEvent 内统一走这里，保证时间线单调）。 */
function nextSeq(state: RunState): number {
  return state.nextSeq++
}

function appendSegment(state: RunState, kind: 'text' | 'reasoning', delta: string): void {
  const last = state.segments[state.segments.length - 1]
  if (last && last.kind === kind) last.content += delta
  else state.segments.push({ kind, content: delta, seq: nextSeq(state) })
}

function findToolCall(state: RunState, callId: string): ToolCallItem | undefined {
  return state.toolCalls.find((t) => t.callId === callId)
}

/** 从 run_completed.usage（松散 Record）里尽量补充用量快照。 */
function mergeUsage(state: RunState, usage: Record<string, unknown> | undefined): void {
  if (!usage) return
  const prev = state.usage ?? { tokensIn: 0, tokensOut: 0, costEstimate: 0, model: '' }
  state.usage = {
    tokensIn: typeof usage.tokens_in === 'number' ? usage.tokens_in : prev.tokensIn,
    tokensOut: typeof usage.tokens_out === 'number' ? usage.tokens_out : prev.tokensOut,
    costEstimate: typeof usage.cost_estimate === 'number' ? usage.cost_estimate : prev.costEstimate,
    model: typeof usage.model === 'string' ? usage.model : prev.model,
  }
}

/**
 * 事件归约：按 19 事件判别联合逐一收窄，更新状态。
 * 不变量：任何事件都不会把 phase 直接置为 completed/error——只有 done（或传输层异常）可以。
 */
export function applyEvent(state: RunState, ev: SSEEvent): void {
  switch (ev.type) {
    case 'run_started': {
      const fresh = ev // resume 新流续接：不清空已累积内容
      if (!state.resuming) {
        const keepConversation = state.conversationId
        const keepSentMessage = state.sentMessage // 本地回显贯穿整个 run（否则 run_started 一到用户气泡就消失）
        Object.assign(state, initialRunState(), { streamOpen: state.streamOpen, conversationId: keepConversation, sentMessage: keepSentMessage })
      }
      if (!state.resuming || !(state.sentMessage || state.segments.length || state.toolCalls.length)) state.renderedRunIds = []
      state.renderedRunIds.push(fresh.run_id)
      state.resuming = false
      state.runId = fresh.run_id
      state.conversationId = fresh.conversation_id
      state.phase = 'streaming'
      state.startedAt = Date.now()
      state.pendingApproval = null // resume 开始：审批卡已解决
      state.planCard = null // 新流启动：旧计划卡已结案（批准即在新流执行/拒绝即终止）
      state.error = null
      state.notice = null // 新流启动即清信息微文本（如「同批还有 N 项待决」已过时）
      state.conflict = false
      break
    }
    case 'stage_changed':
      state.stage = ev.stage
      if (ev.stage === 'awaiting_approval') for (const call of state.toolCalls) if (call.status === 'running') call.status = 'pending'
      break
    case 'heartbeat':
      state.lastHeartbeat = { elapsedMs: ev.elapsed_ms, at: Date.now() }
      break
    case 'text_delta':
      appendSegment(state, 'text', ev.delta)
      // 后端实际不发 streaming_text 阶段（见观察清单），从 delta 派生显示阶段
      state.stage = 'streaming_text'
      break
    case 'reasoning_delta':
      appendSegment(state, 'reasoning', ev.delta)
      state.stage = 'streaming_reasoning'
      break
    case 'tool_call_started':
      state.stage = 'executing_tools' // 与服务端 stage 对齐，工具执行中不显示「输出中」
      {
        // resume 流会以同一 call_id 重发 started（后端 DeferredToolResults 语义：审批后续跑
        // 重新执行获批的延迟调用，call_id 不变），这是协议行为不是异常——同 callId 已有卡时
        // 绝不新增，而是在原卡上复位续跑（保留原 seq，时间线位置不动），否则会出两张工具卡，
        // 且审批前那张永远停在 running。
        const existing = findToolCall(state, ev.call_id)
        if (existing) {
          existing.status = 'running'
          existing.argsPreview = ev.args_preview // 重置为本次值（不是追加）
          existing.resultPreview = null
          existing.durationMs = null
        } else {
          state.toolCalls.push({
            callId: ev.call_id,
            tool: ev.tool,
            argsPreview: ev.args_preview,
            status: 'running',
            resultPreview: null,
            durationMs: null,
            seq: nextSeq(state),
          })
        }
      }
      break
    case 'tool_call_args_delta': {
      const call = findToolCall(state, ev.call_id)
      if (call) call.argsPreview += ev.args_delta
      break
    }
    case 'tool_call_result': {
      const call = findToolCall(state, ev.call_id)
      if (call) {
        call.status = ev.ok ? 'ok' : 'error'
        call.resultPreview = ev.result_preview
        call.durationMs = ev.duration_ms
      }
      break
    }
    case 'tool_approval_requested': {
      const approval: PendingApproval = {
        actionId: ev.action_id,
        tool: ev.tool,
        args: ev.args,
        preview: ev.preview,
        grantAvailable: ev.grant_available === true,
        outcome: null,
      }
      state.pendingApproval = approval
      // 记入审批账目（同 actionId 不重复入账）：幽灵块投影的数据源
      if (!state.approvalLedger.some((x) => x.actionId === approval.actionId)) {
        state.approvalLedger.push(approval)
      }
      // 审批门打开：UI 即刻渲染确认卡。awaiting_approval 仍属「进行中」（isActive 覆盖），
      // 绝不是 completed（约束 3）；后续 run{completed,error} 与 done 只会再确认它。
      state.phase = 'awaiting_approval'
      break
    }
    case 'tool_approval_resolved': {
      if (state.pendingApproval?.actionId === ev.action_id) state.pendingApproval.outcome = ev.outcome
      // 账目同步落章（与 pendingApproval 同引用，这里兜底显式更新）
      const entry = state.approvalLedger.find((x) => x.actionId === ev.action_id)
      if (entry) entry.outcome = ev.outcome
      break
    }
    case 'plan_card':
      state.planCard = { planId: ev.plan_id, title: ev.title, steps: ev.steps }
      break
    case 'work_plan_updated':
      state.workPlanSteps = ev.steps
      break
    case 'subagent_started':
      state.subagents.push({
        subagentId: ev.subagent_id,
        description: ev.description,
        delta: '',
        summary: null,
        ok: null,
      })
      break
    case 'subagent_delta': {
      const sub = state.subagents.find((s) => s.subagentId === ev.subagent_id)
      if (sub) sub.delta += ev.delta
      break
    }
    case 'subagent_completed': {
      const sub = state.subagents.find((s) => s.subagentId === ev.subagent_id)
      if (sub) {
        sub.ok = ev.ok
        sub.summary = ev.summary
      }
      break
    }
    case 'usage_updated':
      // usage_updated 是累计快照，直接覆盖
      state.usage = {
        tokensIn: ev.tokens_in,
        tokensOut: ev.tokens_out,
        costEstimate: ev.cost_estimate,
        model: ev.model,
      }
      break
    case 'run_completed':
      // 仅记录终态预告，不改 phase——done 前保持进行中（约束 4）
      state.runCompleted = { doneReason: ev.done_reason, elapsedMs: ev.elapsed_ms }
      mergeUsage(state, ev.usage)
      break
    case 'run_error':
      // 终态预告：记录错误，phase 仍等 done 收敛
      state.error = { message: ev.message, retryable: ev.retryable }
      break
    case 'done':
      if (state.runCompleted?.doneReason === 'budget_exceeded') state.error = { message: '本轮达到执行预算，消息与执行记录已保存。', retryable: true }
      if (state.runCompleted?.doneReason === 'cancelled' || state.error) for (const call of state.toolCalls) if (call.status === 'running') call.status = 'interrupted'
      // 唯一权威终点
      state.phase = state.error
        ? 'error'
        : state.runCompleted?.doneReason === 'cancelled' ? 'cancelled'
        : state.runCompleted?.doneReason === 'budget_exceeded' ? 'error'
        : state.runCompleted?.doneReason === 'awaiting_approval'
          ? 'awaiting_approval' // 审批中不得显示为已完成（约束 3）
          : 'completed'
      break
  }
}

/** 模块级 AbortController：同会话单 run，无需放进响应式状态。 */
let activeAbort: AbortController | null = null

export const useRunStore = defineStore('run', {
  state: initialRunState,

  getters: {
    /** run 活跃中（流进行中或等待审批，尚未到达 done 终点） */
    isActive(state): boolean {
      return state.connecting || state.phase === 'streaming' || state.phase === 'awaiting_approval'
    },
    stageLabel(state): string | null {
      return state.stage ? (STAGE_LABELS[state.stage] ?? state.stage) : null
    },
    elapsedMs(state): number | null {
      return state.lastHeartbeat?.elapsedMs ?? state.runCompleted?.elapsedMs ?? null
    },
    conflictMessage(state): string | null {
      return state.conflict ? '当前会话已有任务在运行，请等它结束或先取消，再发送新消息。' : null
    },
    /** 同批待决审批数（账目驱动；ready_to_resume 提示与防御性判断用） */
    pendingApprovalCount(state): number {
      return state.approvalLedger.filter((x) => x.outcome === null).length
    },
  },

  actions: {
    hasLiveStream(): boolean { return this.streamOpen || this.connecting || this.phase === 'streaming' },

    restoreState(state: ConversationState): void {
      if (this.hasLiveStream() || this.approvalLedger.some(a => a.busy)) return
      const approvals = state.approvals.map(a => ({ actionId: a.action_id, tool: a.tool, args: a.args,
        preview: a.preview, grantAvailable: a.grant_available,
        outcome: a.status === 'pending' ? null : a.status === 'confirmed' ? 'approved' as const : a.status === 'rejected' ? 'denied' as const : 'expired' as const }))
      const plan = state.plan ? { planId: state.plan.id, title: state.plan.title, steps: state.plan.steps } : null
      const pending = state.status === 'awaiting_approval'
      if (this.conversationId === state.conversation_id && this.runId === state.latest_run_id &&
          JSON.stringify(this.approvalLedger) === JSON.stringify(approvals) && JSON.stringify(this.planCard) === JSON.stringify(plan) &&
          this.phase === (pending ? 'awaiting_approval' : 'idle') && !this.sentMessage && !this.segments.length && !this.toolCalls.length) return
      this.reset(state.conversation_id)
      this.runId = state.latest_run_id
      this.approvalLedger = approvals
      this.pendingApproval = approvals.find(a => !a.outcome) ?? null
      this.planCard = plan
      this.phase = pending ? 'awaiting_approval' : 'idle'
    },

    /** 回到 idle 并清空全部 run 状态（切换会话重载历史时防内容重复）。 */
    reset(conversationId?: number | null): void {
      const selected = conversationId === undefined ? this.conversationId : conversationId
      activeAbort?.abort()
      activeAbort = null
      Object.assign(this, initialRunState(), { conversationId: selected })
    },

    /** 手动关闭 409 冲突提示（重试发送由用户决定，若仍在跑会再次 409）。 */
    dismissConflict(): void {
      this.conflict = false
    },

    /** 消费一个 SSE 事件（流回调用；单测直接喂事件序列） */
    consume(ev: SSEEvent): void {
      applyEvent(this, ev)
    },

    /** 传输层错误（非 2xx / 网络不通 / 协议错误） */
    handleStreamError(err: SSERequestError): void {
      if (err.status === 409) {
        // 同会话单 run 冲突：友好提示，UI 禁用发送
        this.conflict = true
        return
      }
      // resume 被拒：本轮还有未决审批卡。审批确实仍待决，相位保留
      // awaiting_approval；把 400 的 pending 清单落成可读文案
      // （修复前该错误只写进 store.error，UI 仍显示常规等待提示，用户无感知卡死）。
      const blocked = resumeBlockedPending(err)
      if (blocked.length) {
        this.error = { message: formatResumeBlocked(blocked), retryable: false }
        return
      }
      // consumed=true：批次已被 resume 消费（重复 resume 的幂等拒绝）。
      // 按信息级呈现，不计入错误（不写 error、不动相位）。
      if (resumeConsumed(err)) {
        this.notice = '该批次已被消费：本轮审批已续跑过，无需重复操作。'
        return
      }
      this.error = { message: err.message, retryable: err.status === 0 || err.status >= 500 || err.status < 0 }
      if (this.phase === 'idle') this.phase = 'error'
      // 流已建立后的中断由 handleStreamClose 兜底；这里不动进行中的 phase（done 才是权威终点）
    },

    /** 网络层流关闭。未见 done 的关闭 = 异常中断（主动取消时 phase 已是 cancelled，天然跳过） */
    handleStreamClose(gotDoneEvent: boolean): void {
      if (!gotDoneEvent && this.isActive && this.phase !== 'cancelled') {
        this.error = { message: '连接中断：流在 done 之前结束', retryable: true }
        this.phase = 'error'
      }
    },

    async openStream(url: string, body: unknown, onConversationStarted?: (id: number) => void): Promise<void> {
      const abort = new AbortController()
      activeAbort = abort
      this.streamOpen = true
      this.connecting = true
      try {
        await streamSSE(
          url,
          { body, signal: abort.signal },
          {
            onEvent: (ev) => {
              if (activeAbort !== abort) return
              applyEvent(this, ev)
              if (ev.type === 'run_started') {
                this.connecting = false
                onConversationStarted?.(ev.conversation_id)
              }
            },
            onError: (err) => { if (activeAbort === abort) this.handleStreamError(err) },
            onClose: ({ gotDoneEvent }) => { if (activeAbort === abort) this.handleStreamClose(gotDoneEvent) },
          },
        )
      } finally {
        if (activeAbort === abort) {
          activeAbort = null
          this.streamOpen = false
          this.connecting = false
        }
      }
    },

    /** 发送消息开新 run。run 进行中时拒绝重入（同会话单 run，后端亦会 409）。 */
    async sendMessage(
      message: string,
      opts: { conversationId?: number | null; attachmentIds?: number[]; planMode?: boolean; researchProjectId?: number; onConversationStarted?: (id: number) => void } = {},
    ): Promise<void> {
      if (this.isActive) return
      // Explicit null means a new conversation. Only omitted/undefined means continue.
      const conversationId = opts.conversationId === undefined ? this.conversationId : opts.conversationId
      Object.assign(this, initialRunState(), { conversationId })
      this.sentMessage = message // 本地回显（新会话首条消息时，历史列表里还没有它）
      const body: components['schemas']['ChatBody'] = {
        message,
        conversation_id: conversationId,
        attachment_ids: opts.attachmentIds ?? [],
        plan_mode: opts.planMode ?? false,
      }
      if (opts.researchProjectId !== undefined) body.research_project_id = opts.researchProjectId
      await this.openStream('/ai/chat/stream', body, opts.onConversationStarted)
    },

    /** 审批后续跑：POST /ai/conversations/{cid}/resume/stream 开新流，续接同一段内容。 */
    async openResumeStream(): Promise<void> {
      if (activeAbort) return
      if (!this.conversationId) {
        this.error = { message: '缺少会话 ID，无法续跑', retryable: false }
        return
      }
      this.resuming = true
      await this.openStream(`/ai/conversations/${this.conversationId}/resume/stream`, {})
    },

    /** 账目落章：指定 actionId 标记 outcome（账目与 pendingApproval 槽位共享对象，一处更新两处可见）。 */
    markResolved(actionId: number, outcome: NonNullable<PendingApproval['outcome']>): void {
      const entry = this.approvalLedger.find((x) => x.actionId === actionId)
      if (entry) entry.outcome = outcome
    },

    /**
     * 结案后的 resume 决策（approve/reject 共用）：
     * ready_to_resume === false（同批还有待决）→ 不开 resume 流，信息微文本提示剩余数；
     * true（最后一项结清）→ 自动开 resume 流；响应无该字段（旧后端兼容）→ 维持现状
     * 立即 resume，本轮仍有 pending 时由 resume 400 的 formatResumeBlocked 兜底。
     */
    async afterActionResolved(verb: string, resp: ActionResolveResult): Promise<void> {
      if (resp && resp.ready_to_resume === false && this.pendingApprovalCount > 0) {
        this.notice = `${verb}，同批还有 ${this.pendingApprovalCount} 项待决`
        return
      }
      await this.openResumeStream()
    },

    /** 批准指定审批卡（可选建立始终允许规则），按 ready_to_resume 决定是否立即续跑。 */
    async approve(actionId: number, grantAlways = false): Promise<void> {
      const entry = this.approvalLedger.find((x) => x.actionId === actionId)
      if (activeAbort || !entry || entry.outcome || entry.busy) return
      const cid = this.conversationId, rid = this.runId
      const owns = () => this.conversationId === cid && this.runId === rid && this.approvalLedger.includes(entry)
      entry.busy = true
      let resp: ActionResolveResult
      try {
        resp = await http.post<ActionResolveResult>(
          `/ai/actions/${actionId}/approve`,
          grantAlways ? { grant_always: true } : {},
        )
      } catch (e) {
        entry.busy = false
        if (!owns()) return
        this.error = { message: e instanceof Error ? e.message : '批准请求失败', retryable: true }
        return
      }
      entry.busy = false
      if (!owns()) return
      if (resp.resume && resp.resume !== `/ai/conversations/${cid}/resume/stream`) { this.error = { message: '审批恢复地址与原会话不一致，已停止续跑。', retryable: false }; return }
      this.markResolved(actionId, 'approved')
      await this.afterActionResolved('已批准', resp)
    },

    /** 拒绝指定审批卡（模型会收到不得重试约束），resume 时机同 approve。 */
    async reject(actionId: number): Promise<void> {
      const entry = this.approvalLedger.find((x) => x.actionId === actionId)
      if (activeAbort || !entry || entry.outcome || entry.busy) return
      const cid = this.conversationId, rid = this.runId
      const owns = () => this.conversationId === cid && this.runId === rid && this.approvalLedger.includes(entry)
      entry.busy = true
      let resp: ActionResolveResult
      try {
        resp = await http.post<ActionResolveResult>(`/ai/actions/${actionId}/reject`)
      } catch (e) {
        entry.busy = false
        if (!owns()) return
        this.error = { message: e instanceof Error ? e.message : '拒绝请求失败', retryable: true }
        return
      }
      entry.busy = false
      if (!owns()) return
      if (resp.resume && resp.resume !== `/ai/conversations/${cid}/resume/stream`) { this.error = { message: '审批恢复地址与原会话不一致，已停止续跑。', retryable: false }; return }
      this.markResolved(actionId, 'denied')
      await this.afterActionResolved('已拒绝', resp)
    },

    /** 计划批准：后端 approve 端点直接返回新 run 的 SSE 流（同会话续跑），照 resume 消费。 */
    async approvePlan(): Promise<void> {
      const plan = this.planCard
      if (activeAbort || !plan || !this.conversationId) return
      this.resuming = true
      await this.openStream(`/ai/conversations/${this.conversationId}/plans/${plan.planId}/approve`, {})
    },

    /** 计划拒绝：普通 REST（模型不会执行该计划），本地落定计划卡为已拒绝。 */
    async rejectPlan(): Promise<void> {
      const plan = this.planCard
      if (activeAbort || !plan || !this.conversationId) return
      const cid = this.conversationId
      try {
        await http.post(`/ai/conversations/${cid}/plans/${plan.planId}/reject`)
        if (this.conversationId === cid && this.planCard === plan) this.planCard = null
      } catch (e) {
        if (this.conversationId !== cid || this.planCard !== plan) return
        this.error = { message: e instanceof Error ? e.message : '拒绝计划失败', retryable: true }
      }
    },

    /** 取消当前 run（幂等）：本地断流 + POST cancel（后端幂等，失败不阻塞）。 */
    async cancel(): Promise<void> {
      if (this.phase === 'cancelled') return
      if (!this.isActive && !activeAbort) return
      if (this.phase === 'awaiting_approval' && !activeAbort && this.conversationId && this.runId) {
        const cid = this.conversationId, rid = this.runId
        try { await http.post(`/ai/conversations/${cid}/pending/cancel`, { run_id: rid }) }
        catch (e) { if (this.conversationId === cid && this.runId === rid) this.error = { message: String(e), retryable: true }; return }
        if (this.conversationId !== cid || this.runId !== rid) return
        this.approvalLedger = []
      }
      this.phase = 'cancelled'
      activeAbort?.abort()
      const runId = this.runId
      if (runId) {
        try {
          await http.post(`/ai/runs/${runId}/cancel`)
        } catch {
          // 后端取消幂等（未知 run 返回 ok:false 不报错）；本地已断流，忽略网络失败
        }
      }
    },
  },
})
