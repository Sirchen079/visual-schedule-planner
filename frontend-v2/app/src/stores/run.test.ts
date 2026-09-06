import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { STAGE_LABELS, resumeBlockedPending, resumeConsumed, useRunStore } from './run'
import { SSERequestError } from '../api/sse'
import type { SSEEvent } from '../api/contracts/events'

/** 录制的事件序列：run_started → stage_changed×n → reasoning/text delta → 工具生命周期 →
 *  审批请求 → run_completed(awaiting_approval) → done（本测试里 done 在断言后手动喂）。 */
const RECORDED: SSEEvent[] = [
  { v: 1, type: 'run_started', run_id: 'r1', conversation_id: 7 },
  { v: 1, type: 'stage_changed', stage: 'preparing' },
  { v: 1, type: 'stage_changed', stage: 'connecting' },
  { v: 1, type: 'stage_changed', stage: 'waiting_first_token' },
  { v: 1, type: 'stage_changed', stage: 'streaming_reasoning' },
  { v: 1, type: 'reasoning_delta', delta: '先想一下' },
  { v: 1, type: 'stage_changed', stage: 'streaming_text' },
  { v: 1, type: 'text_delta', delta: '你好' },
  { v: 1, type: 'text_delta', delta: '，世界' },
  { v: 1, type: 'stage_changed', stage: 'executing_tools' },
  { v: 1, type: 'tool_call_started', call_id: 'c1', tool: 'api__tasks__create_task', args_preview: '{"title"' },
  { v: 1, type: 'tool_call_args_delta', call_id: 'c1', args_delta: ':"写周报"}' },
  { v: 1, type: 'tool_call_result', call_id: 'c1', ok: true, result_preview: '{"id":11}', duration_ms: 120 },
  { v: 1, type: 'heartbeat', elapsed_ms: 900, stage: 'executing_tools', last_event_age_ms: 30 },
  { v: 1, type: 'stage_changed', stage: 'awaiting_approval' },
  {
    v: 1,
    type: 'tool_approval_requested',
    action_id: 42,
    tool: 'api__schedule__delete_entry',
    args: { id: 3 },
    preview: '将删除 1 条日程',
    grant_available: true,
  },
  { v: 1, type: 'usage_updated', tokens_in: 100, tokens_out: 50, cost_estimate: 0.01, model: 'test-model' },
  { v: 1, type: 'run_completed', run_id: 'r1', usage: { tokens_in: 110, tokens_out: 55 }, elapsed_ms: 1500, done_reason: 'awaiting_approval' },
]

function feed(store: ReturnType<typeof useRunStore>, events: SSEEvent[]): void {
  for (const ev of events) store.consume(ev)
}

describe('run store 状态机（录制序列）', () => {
  let store: ReturnType<typeof useRunStore>

  beforeEach(() => {
    setActivePinia(createPinia())
    store = useRunStore()
  })

  it('idle 起步，run_started 后进入 streaming 并记录 run/conversation', () => {
    expect(store.phase).toBe('idle')
    store.consume(RECORDED[0])
    expect(store.phase).toBe('streaming')
    expect(store.runId).toBe('r1')
    expect(store.conversationId).toBe(7)
  })

  it('阶段八标签中文映射', () => {
    feed(store, RECORDED.slice(0, 5))
    expect(store.stage).toBe('streaming_reasoning')
    expect(store.stageLabel).toBe(STAGE_LABELS.streaming_reasoning)
    expect(STAGE_LABELS).toEqual({
      preparing: '准备中',
      connecting: '连接中',
      waiting_first_token: '等待首个 token',
      streaming_reasoning: '思考中',
      streaming_text: '输出中',
      executing_tools: '执行工具',
      awaiting_approval: '等待审批',
      finalizing: '收尾中',
    })
  })

  it('text/reasoning 分段累积：同类追加、异类分段', () => {
    feed(store, RECORDED)
    expect(store.segments).toEqual([
      { kind: 'reasoning', content: '先想一下', seq: 1 },
      { kind: 'text', content: '你好，世界', seq: 2 },
    ])
  })

  it('工具卡片生命周期 started → args_delta → result（约束 2：工具调用可见）', () => {
    feed(store, RECORDED)
    expect(store.toolCalls).toHaveLength(1)
    const call = store.toolCalls[0]
    expect(call.argsPreview).toBe('{"title":"写周报"}')
    expect(call.status).toBe('ok')
    expect(call.resultPreview).toBe('{"id":11}')
    expect(call.durationMs).toBe(120)
  })

  it('heartbeat 记录耗时，usage 实时累计（run_completed 的最终用量并入）', () => {
    feed(store, RECORDED)
    expect(store.lastHeartbeat?.elapsedMs).toBe(900)
    // usage_updated 快照 100/50，随后 run_completed.usage 的 110/55 并入覆盖
    expect(store.usage).toEqual({ tokensIn: 110, tokensOut: 55, costEstimate: 0.01, model: 'test-model' })
  })

  it('约束 4：tool_approval_requested 即进入 awaiting_approval，run_completed 后、done 前保持进行中', () => {
    feed(store, RECORDED) // 最后一个是 run_completed(awaiting_approval)，还没喂 done
    expect(store.phase).toBe('awaiting_approval') // 等待用户，且绝不是 completed
    expect(store.runCompleted?.doneReason).toBe('awaiting_approval')
    expect(store.phase).not.toBe('completed')
  })

  it('约束 3：审批序列收到 done 后仍是 awaiting_approval，绝不变 completed', () => {
    feed(store, RECORDED)
    store.consume({ v: 1, type: 'done', run_id: 'r1' })
    expect(store.phase).toBe('awaiting_approval')
    expect(store.pendingApproval).toMatchObject({
      actionId: 42,
      tool: 'api__schedule__delete_entry',
      preview: '将删除 1 条日程',
      grantAvailable: true,
      outcome: null,
    })
  })

  it('run_error 只是预告：done 才落定为 error（约束 4）', () => {
    feed(store, [
      { v: 1, type: 'run_started', run_id: 'r2', conversation_id: 7 },
      { v: 1, type: 'run_error', run_id: 'r2', message: '模型超时', retryable: true },
    ])
    expect(store.phase).toBe('streaming') // 仍是进行中
    store.consume({ v: 1, type: 'done', run_id: 'r2' })
    expect(store.phase).toBe('error')
  })

  it('正常完成：run_completed(done) + done → completed，run_completed 的 usage 并入累计', () => {
    feed(store, [
      { v: 1, type: 'run_started', run_id: 'r3', conversation_id: 7 },
      { v: 1, type: 'text_delta', delta: 'ok' },
      { v: 1, type: 'run_completed', run_id: 'r3', usage: { tokens_in: 5 }, elapsed_ms: 80, done_reason: 'end_turn' },
      { v: 1, type: 'done', run_id: 'r3' },
    ])
    expect(store.phase).toBe('completed')
    expect(store.usage?.tokensIn).toBe(5)
    expect(store.elapsedMs).toBe(80)
  })

  it('审批解决 → resume 新流：内容续接、审批卡清除、最终 completed', () => {
    feed(store, RECORDED)
    store.consume({ v: 1, type: 'done', run_id: 'r1' })
    expect(store.phase).toBe('awaiting_approval')

    store.consume({ v: 1, type: 'tool_approval_resolved', action_id: 42, outcome: 'approved' })
    expect(store.pendingApproval?.outcome).toBe('approved')

    // resume 新流：run_started 不清空已累积内容（resuming 标记由 openResumeStream 设置）
    store.resuming = true
    store.consume({ v: 1, type: 'run_started', run_id: 'r4', conversation_id: 7 })
    expect(store.phase).toBe('streaming')
    expect(store.runId).toBe('r4')
    expect(store.pendingApproval).toBeNull()
    expect(store.segments).toEqual([
      { kind: 'reasoning', content: '先想一下', seq: 1 },
      { kind: 'text', content: '你好，世界', seq: 2 },
    ])

    store.consume({ v: 1, type: 'text_delta', delta: '，已继续' })
    store.consume({ v: 1, type: 'run_completed', run_id: 'r4', usage: {}, elapsed_ms: 2000, done_reason: 'end_turn' })
    store.consume({ v: 1, type: 'done', run_id: 'r4' })
    expect(store.phase).toBe('completed')
    expect(store.segments[1].content).toBe('你好，世界，已继续')
  })

  it('流在 done 之前关闭 → 异常中断 error（主动取消除外）', () => {
    feed(store, RECORDED.slice(0, 1)) // streaming 中
    store.handleStreamClose(false)
    expect(store.phase).toBe('error')
    expect(store.error?.message).toContain('done')

    // cancelled 状态下流关闭不覆盖为 error
    feed(store, [{ v: 1, type: 'run_started', run_id: 'r5', conversation_id: 7 }])
    store.phase = 'cancelled'
    store.handleStreamClose(false)
    expect(store.phase).toBe('cancelled')
  })

  it('取消幂等：无活跃 run 时 cancel 是 no-op；进行中取消后二次 cancel 不再变更', async () => {
    feed(store, RECORDED.slice(0, 1)) // streaming
    store.runId = 'r1'
    // 注：http.post 在 node 测试环境对相对路径 fetch 立即抛错并被 cancel 内部吞掉，不出网
    await store.cancel()
    expect(store.phase).toBe('cancelled')
    await store.cancel() // 幂等
    expect(store.phase).toBe('cancelled')

    // 同一 pinia 下 useRunStore 返回同一实例；开新 pinia 才是全新 store
    setActivePinia(createPinia())
    const fresh = useRunStore()
    await fresh.cancel() // idle 下 no-op
    expect(fresh.phase).toBe('idle')
  })
})

describe('run store 409 与防重入', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('409 → conflict=true，phase 不变，友好提示可读', () => {
    const store = useRunStore()
    store.handleStreamError(new SSERequestError(409, 'conversation busy'))
    expect(store.conflict).toBe(true)
    expect(store.phase).toBe('idle')
    expect(store.conflictMessage).toContain('已有任务在运行')
  })

  it('非 409 请求错误且 idle → error', () => {
    const store = useRunStore()
    store.handleStreamError(new SSERequestError(0, '网络错误'))
    expect(store.phase).toBe('error')
    expect(store.error?.retryable).toBe(true)
  })

  it('isActive 时 sendMessage 拒绝重入', async () => {
    const store = useRunStore()
    store.phase = 'streaming'
    store.runId = 'r1'
    await store.sendMessage('新消息')
    expect(store.runId).toBe('r1') // 未被重置/未开新流
    expect(store.phase).toBe('streaming')
  })
})

describe('run store 审批账目（多幽灵块并存投影的数据源）', () => {
  const APPROVAL_A = {
    v: 1 as const,
    type: 'tool_approval_requested' as const,
    action_id: 101,
    tool: 'schedule.create_event',
    args: { title: '测试A', date: '2026-09-05', start_time: '09:00', end_time: '10:00' },
    preview: '创建：测试A',
    grant_available: true,
  }
  const APPROVAL_B = {
    v: 1 as const,
    type: 'tool_approval_requested' as const,
    action_id: 102,
    tool: 'schedule.create_event',
    args: { title: '测试B', date: '2026-09-05', start_time: '15:00', end_time: '16:00' },
    preview: '创建：测试B',
    grant_available: true,
  }

  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('请求过的审批都入账（同一 run 先后两个 create_event），当前待决者仍是 pendingApproval', () => {
    const store = useRunStore()
    store.consume({ v: 1, type: 'run_started', run_id: 'r1', conversation_id: 7 })
    store.consume(APPROVAL_A)
    expect(store.approvalLedger.map((x) => x.actionId)).toEqual([101])
    // 批准 A → resume 续跑（账目保留）→ 请求 B
    store.consume({ v: 1, type: 'done', run_id: 'r1' })
    store.consume({ v: 1, type: 'tool_approval_resolved', action_id: 101, outcome: 'approved' })
    store.resuming = true
    store.consume({ v: 1, type: 'run_started', run_id: 'r2', conversation_id: 7 })
    store.consume(APPROVAL_B)
    expect(store.approvalLedger.map((x) => x.actionId)).toEqual([101, 102])
    expect(store.approvalLedger[0].outcome).toBe('approved') // A 已落章，幽灵块等实体化
    expect(store.approvalLedger[1].outcome).toBeNull() // B 待决
    expect(store.pendingApproval?.actionId).toBe(102) // 对话内审批卡只看当前待决
  })

  it('resolved 落章同步账目；拒绝的条目保留在账（由投影层过滤）', () => {
    const store = useRunStore()
    store.consume({ v: 1, type: 'run_started', run_id: 'r1', conversation_id: 7 })
    store.consume(APPROVAL_A)
    store.consume({ v: 1, type: 'tool_approval_resolved', action_id: 101, outcome: 'denied' })
    // 语义：解决后 pendingApproval 保留对象并带 outcome（resume 的 run_started 才清空）
    expect(store.pendingApproval?.outcome).toBe('denied')
    expect(store.approvalLedger[0].outcome).toBe('denied')
    // 账目与待决卡是同一份对象：落章一处、两处可见
    expect(store.approvalLedger[0]).toBe(store.pendingApproval)
  })

  it('同一 actionId 重复请求不重复入账', () => {
    const store = useRunStore()
    store.consume({ v: 1, type: 'run_started', run_id: 'r1', conversation_id: 7 })
    store.consume(APPROVAL_A)
    store.consume({ ...APPROVAL_A, preview: '重复推送' })
    expect(store.approvalLedger).toHaveLength(1)
  })

  it('新消息清空旧审批预览，恢复执行保留预览', () => {
    const store = useRunStore()
    store.consume({ v: 1, type: 'run_started', run_id: 'r1', conversation_id: 7 })
    store.consume(APPROVAL_A)
    // resume：账目保留（幽灵块要留到数据实体化）
    store.resuming = true
    store.consume({ v: 1, type: 'run_started', run_id: 'r2', conversation_id: 7 })
    expect(store.approvalLedger).toHaveLength(1)
    // 新消息开始时清空旧审批预览。
    store.consume({ v: 1, type: 'run_started', run_id: 'r3', conversation_id: 7 })
    expect(store.approvalLedger).toEqual([])
  })
})

describe('run store resume 拒绝体（ResumeBlockedOut，回归）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  /** 同一轮产生两个待审批工具调用。 */
  function dualPending(store: ReturnType<typeof useRunStore>): void {
    store.consume({ v: 1, type: 'run_started', run_id: 'r1', conversation_id: 7 })
    store.consume({
      v: 1, type: 'tool_approval_requested', action_id: 20, tool: 'create_event',
      args: { title: '测试·晨跑', day: '2026-09-05', start_time: '09:00', end_time: '10:00' },
      preview: '', grant_available: true,
    })
    store.consume({
      v: 1, type: 'tool_approval_requested', action_id: 21, tool: 'create_event',
      args: { title: '测试·自习', day: '2026-09-05', start_time: '15:00', end_time: '16:00' },
      preview: '', grant_available: true,
    })
  }

  it('批准一个后 resume 被 400 拒：pending 清单落成可读文案，相位保持待决不变', () => {
    const store = useRunStore()
    dualPending(store)
    store.pendingApproval!.outcome = 'approved' // 批准了其中一个（另一项仍 pending）
    store.handleStreamError(
      new SSERequestError(400, '请求失败（HTTP 400）', {
        pending: [{ action_id: 20, tool_name: 'create_event' }],
        consumed: false,
        message: '',
      }),
    )
    expect(store.error?.message).toContain('1 项待批操作')
    expect(store.error?.message).toContain('create_event')
    expect(store.error?.retryable).toBe(false)
    expect(store.phase).toBe('awaiting_approval') // 审批确实仍待决，不落 error 相位
    expect(store.conflict).toBe(false)
  })

  it('同工具多项聚合计数：2 个 create_event → create_event×2', () => {
    const store = useRunStore()
    store.handleStreamError(
      new SSERequestError(400, '请求失败（HTTP 400）', {
        pending: [
          { action_id: 20, tool_name: 'create_event' },
          { action_id: 21, tool_name: 'create_event' },
        ],
        consumed: false,
        message: '',
      }),
    )
    expect(store.error?.message).toContain('2 项待批操作')
    expect(store.error?.message).toContain('create_event×2')
  })

  it('consumed=true（重复 resume 的幂等拒绝）：按信息级 notice 呈现，不落 error 不动相位', () => {
    const store = useRunStore()
    dualPending(store) // awaiting_approval 中
    store.handleStreamError(
      new SSERequestError(400, '请求失败（HTTP 400）', { pending: [], consumed: true, message: '该批次已被消费' }),
    )
    expect(store.notice).toContain('该批次已被消费')
    expect(store.error).toBeNull() // 信息不计错误
    expect(store.phase).toBe('awaiting_approval') // 相位不动
    // idle 下同理：不落 error 相位
    setActivePinia(createPinia())
    const idle = useRunStore()
    idle.handleStreamError(new SSERequestError(400, 'x', { pending: [], consumed: true }))
    expect(idle.notice).toContain('该批次已被消费')
    expect(idle.phase).toBe('idle')
  })

  it('consumed=false 的 400（pending 空）走普通错误路径（不误伤）', () => {
    const store = useRunStore()
    store.handleStreamError(
      new SSERequestError(400, '请求失败（HTTP 400）', { pending: [], consumed: false }),
    )
    expect(store.error?.message).toBe('请求失败（HTTP 400）')
    expect(store.notice).toBeNull()
    expect(store.phase).toBe('error') // idle 起步的普通错误路径
  })

  it('resumeConsumed 纯函数：仅 400 + consumed=true 命中（不误伤 500/缺体/非布尔）', () => {
    expect(resumeConsumed(new SSERequestError(400, 'x', { pending: [], consumed: true }))).toBe(true)
    expect(resumeConsumed(new SSERequestError(400, 'x', { consumed: false }))).toBe(false)
    expect(resumeConsumed(new SSERequestError(400, 'x', { pending: [{}] }))).toBe(false)
    expect(resumeConsumed(new SSERequestError(500, 'x', { consumed: true }))).toBe(false)
    expect(resumeConsumed(new SSERequestError(400, 'x'))).toBe(false)
  })

  it('非 400 / 缺 pending 字段 / 形状不符 → 识别为空清单（不误伤普通错误）', () => {
    expect(resumeBlockedPending(new SSERequestError(500, 'x', { pending: [{ action_id: 1, tool_name: 't' }] }))).toEqual([])
    expect(resumeBlockedPending(new SSERequestError(400, 'x'))).toEqual([])
    expect(resumeBlockedPending(new SSERequestError(400, 'x', { detail: '审批数据不完整' }))).toEqual([])
    expect(resumeBlockedPending(new SSERequestError(400, 'x', { pending: ['bad'] }))).toEqual([])
  })

  it('resume 成功开新流后错误清除（run_started 清 error，文案不再残留）', () => {
    const store = useRunStore()
    dualPending(store)
    store.handleStreamError(
      new SSERequestError(400, '请求失败（HTTP 400）', {
        pending: [{ action_id: 20, tool_name: 'create_event' }],
        consumed: false,
        message: '',
      }),
    )
    expect(store.error).not.toBeNull()
    store.consume({ v: 1, type: 'run_started', run_id: 'r2', conversation_id: 7 })
    expect(store.error).toBeNull()
  })
})

describe('run store ready_to_resume 接线', () => {
  function jsonResponse(payload: unknown, status = 200): Response {
    const text = JSON.stringify(payload)
    return {
      ok: status >= 200 && status < 300,
      status,
      text: async () => text,
      json: async () => JSON.parse(text),
    } as unknown as Response
  }

  /** resume 端点的最小 SSE 流（run_started + done），让 openStream 正常收敛。 */
  function sseResponse(frames: string): Response {
    return {
      ok: true,
      status: 200,
      body: new ReadableStream<Uint8Array>({
        start(ctrl) {
          ctrl.enqueue(new TextEncoder().encode(frames))
          ctrl.close()
        },
      }),
    } as unknown as Response
  }

  const RESUME_SSE =
    'event: run_started\ndata: {"v":1,"type":"run_started","run_id":"rr","conversation_id":7}\n\n' +
    'event: done\ndata: {"v":1,"type":"done","run_id":"rr"}\n\n'

  /** 双 deferred：同轮两个 tool_approval_requested（账目两项并存）。 */
  function dualPending(store: ReturnType<typeof useRunStore>): void {
    store.consume({ v: 1, type: 'run_started', run_id: 'r1', conversation_id: 7 })
    store.consume({
      v: 1, type: 'tool_approval_requested', action_id: 20, tool: 'create_event',
      args: { title: '测试·晨跑', day: '2026-09-05', start_time: '09:00', end_time: '10:00' },
      preview: '', grant_available: true,
    })
    store.consume({
      v: 1, type: 'tool_approval_requested', action_id: 21, tool: 'create_event',
      args: { title: '测试·自习', day: '2026-09-05', start_time: '15:00', end_time: '16:00' },
      preview: '', grant_available: true,
    })
  }

  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('双卡并存入账；批准第一张（ready_to_resume=false）→ 不开 resume 流，落章+微文本提示剩余 1 项', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
        calls.push({ url: String(url), init })
        return jsonResponse({ ok: true, ready_to_resume: false })
      }),
    )
    try {
      const store = useRunStore()
      dualPending(store)
      expect(store.approvalLedger).toHaveLength(2)
      expect(store.pendingApprovalCount).toBe(2)

      await store.approve(20)
      expect(calls.map((c) => c.url)).toEqual(['/ai/actions/20/approve']) // 未开 resume 流
      expect(store.approvalLedger[0].outcome).toBe('approved')
      expect(store.notice).toBe('已批准，同批还有 1 项待决')
      expect(store.phase).toBe('awaiting_approval') // 仍在等第二张
      expect(store.error).toBeNull() // 信息不是错误

      // 已结案卡重复批准是 no-op（不发请求）
      await store.approve(20)
      expect(calls).toHaveLength(1)
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('最后一项批准（ready_to_resume=true）→ 自动开 resume 新流；run_started 清 notice', async () => {
    const calls: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string | URL | Request) => {
        calls.push(String(url))
        if (String(url).includes('/ai/actions/21/approve')) return jsonResponse({ ok: true, ready_to_resume: true })
        return sseResponse(RESUME_SSE)
      }),
    )
    try {
      const store = useRunStore()
      dualPending(store)
      store.approvalLedger[0].outcome = 'approved' // 第一张已批（如上例）
      store.notice = '已批准，同批还有 1 项待决'
      await store.approve(21)
      expect(calls[0]).toBe('/ai/actions/21/approve')
      expect(calls[1]).toBe('/ai/conversations/7/resume/stream') // 结清即自动续跑
      expect(store.runId).toBe('rr') // resume 新流的 run_started 已接管（resuming 标志随其复位）
      expect(store.phase).toBe('completed') // SSE 流 run_started+done 正常收敛
      expect(store.notice).toBeNull() // 新流启动清信息微文本
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('向后兼容：响应无 ready_to_resume 字段 → 维持现状立即 resume（400 由 formatResumeBlocked 兜底）', async () => {
    const calls: Array<{ url: string; body: unknown }> = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
        calls.push({ url: String(url), body: init?.body })
        if (String(url).includes('/ai/actions/20/approve')) return jsonResponse({ ok: true, resume: '' })
        return sseResponse(RESUME_SSE)
      }),
    )
    try {
      const store = useRunStore()
      dualPending(store)
      store.approvalLedger[1].outcome = 'denied'
      await store.approve(20, true) // 始终允许
      expect(calls[0].body).toBe('{"grant_always":true}')
      expect(calls[1].url).toBe('/ai/conversations/7/resume/stream') // 无字段 = 旧行为立即续跑
      expect(store.approvalLedger[0].outcome).toBe('approved')
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('拒绝同理：ready_to_resume=false → 落章 denied + 「已拒绝，同批还有 N 项待决」，不开流', async () => {
    const calls: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string | URL | Request) => {
        calls.push(String(url))
        return jsonResponse({ ok: true, ready_to_resume: false })
      }),
    )
    try {
      const store = useRunStore()
      dualPending(store)
      await store.reject(21)
      expect(calls).toEqual(['/ai/actions/21/reject'])
      expect(store.approvalLedger[1].outcome).toBe('denied')
      expect(store.notice).toBe('已拒绝，同批还有 1 项待决')
      expect(store.phase).toBe('awaiting_approval')
    } finally {
      vi.unstubAllGlobals()
    }
  })
})

describe('run store resume 重发工具卡去重（DeferredToolResults：同 call_id 重发 started）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('resume 重发同 callId 的 tool_call_started → 仍只有一张卡（原卡复位续跑，seq 不变）', () => {
    const store = useRunStore()
    store.consume({ v: 1, type: 'run_started', run_id: 'r1', conversation_id: 7 })
    store.consume({
      v: 1, type: 'tool_call_started', call_id: 'x', tool: 'api__schedule__delete_entry', args_preview: '{"id"',
    })
    store.consume({
      v: 1,
      type: 'tool_approval_requested',
      action_id: 42,
      tool: 'api__schedule__delete_entry',
      args: { id: 3 },
      preview: '将删除 1 条日程',
      grant_available: true,
    })
    expect(store.toolCalls).toHaveLength(1)
    const firstSeq = store.toolCalls[0].seq
    expect(store.toolCalls[0].status).toBe('running') // 审批门前未执行，无 result

    // resume 新流（resuming 标记由 openResumeStream 设置）：run_started 不清内容，工具卡保留
    store.resuming = true
    store.consume({ v: 1, type: 'run_started', run_id: 'r2', conversation_id: 7 })
    // 后端以同一 call_id 重发 started，且本次 args_preview 为完整值（非追加语义）
    store.consume({
      v: 1, type: 'tool_call_started', call_id: 'x', tool: 'api__schedule__delete_entry', args_preview: '{"id":3}',
    })
    expect(store.toolCalls).toHaveLength(1) // 不新增卡
    expect(store.toolCalls[0].argsPreview).toBe('{"id":3}') // 重置为本次值，不是拼接
    expect(store.toolCalls[0].status).toBe('running')
    expect(store.toolCalls[0].resultPreview).toBeNull()
    expect(store.toolCalls[0].durationMs).toBeNull()
    expect(store.toolCalls[0].seq).toBe(firstSeq) // 时间线位置不动

    store.consume({
      v: 1, type: 'tool_call_result', call_id: 'x', ok: true, result_preview: '{"deleted":true}', duration_ms: 45,
    })
    expect(store.toolCalls).toHaveLength(1)
    expect(store.toolCalls[0].status).toBe('ok')
    expect(store.toolCalls[0].resultPreview).toBe('{"deleted":true}')
    expect(store.toolCalls[0].durationMs).toBe(45)
    expect(store.toolCalls[0].seq).toBe(firstSeq)
  })

  it('全新 callId 仍正常新增卡（两个不同 callId → 两张卡）', () => {
    const store = useRunStore()
    store.consume({ v: 1, type: 'run_started', run_id: 'r1', conversation_id: 7 })
    store.consume({ v: 1, type: 'tool_call_started', call_id: 'c1', tool: 'api__tasks__create_task', args_preview: '{"title"' })
    store.consume({ v: 1, type: 'tool_call_started', call_id: 'c2', tool: 'api__schedule__list_entries', args_preview: '{}' })
    expect(store.toolCalls).toHaveLength(2)
    expect(store.toolCalls.map((t) => t.callId)).toEqual(['c1', 'c2'])
    expect(store.toolCalls.map((t) => t.tool)).toEqual(['api__tasks__create_task', 'api__schedule__list_entries'])
    expect(store.toolCalls.every((t) => t.status === 'running')).toBe(true)
  })
})
