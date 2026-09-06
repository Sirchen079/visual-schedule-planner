import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { SSERequestError } from '../api/sse'
import { useRunStore } from './run'
import type { SSEEvent } from '../api/contracts/events'

/**
 * M1 增量：seq 时序、本地回显、reset、conflict 关闭、计划批准/拒绝。
 * approvePlan 的端点直接返回 SSE 流——流消费本身由 sse.test.ts/联调覆盖，
 * 这里用 fetch stub 验证 URL/调用编排与状态变化。
 */

function jsonResponse(payload: unknown, status = 200): Response {
  const text = JSON.stringify(payload)
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => text,
    json: async () => JSON.parse(text),
  } as unknown as Response
}

describe('run store M1 增量', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('seq 单调：segments 与 toolCalls 按事件到达序编号，可用于时间线合并', () => {
    const store = useRunStore()
    const seq: SSEEvent[] = [
      { v: 1, type: 'run_started', run_id: 'r1', conversation_id: 3 },
      { v: 1, type: 'text_delta', delta: '先查一下' },
      { v: 1, type: 'tool_call_started', call_id: 'c1', tool: 'find_free_slots', args_preview: '' },
      { v: 1, type: 'text_delta', delta: '再写结论' },
      { v: 1, type: 'tool_call_result', call_id: 'c1', ok: true, result_preview: 'ok', duration_ms: 5 },
    ]
    for (const ev of seq) store.consume(ev)
    // 同类相邻 text_delta 合并进同一段（seq=1），工具卡取得中间的 seq=2
    expect(store.segments.map((s) => s.seq)).toEqual([1])
    expect(store.toolCalls[0].seq).toBe(2)
    expect(store.segments[0].content).toBe('先查一下再写结论')
  })

  it('sendMessage 记录本地回显 sentMessage；reset 保留 conversationId 清空其余', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({}))
    vi.stubGlobal('fetch', fetchMock)
    try {
      const store = useRunStore()
      store.conversationId = 9
      await store.sendMessage('帮我建个日程', { conversationId: 9 })
      expect(store.sentMessage).toBe('帮我建个日程')
      // stub 返回的是普通 JSON（非 SSE 流）：传输层报错，但 sentMessage 已记录
      store.reset()
      expect(store.sentMessage).toBeNull()
      expect(store.segments).toHaveLength(0)
      expect(store.conversationId).toBe(9)
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('run_started 不清空 sentMessage（本地回显贯穿整个 run，M2 修复）', () => {
    const store = useRunStore()
    store.sentMessage = '帮我建个日程'
    store.consume({ v: 1, type: 'run_started', run_id: 'r9', conversation_id: 3 })
    expect(store.sentMessage).toBe('帮我建个日程')
    expect(store.runId).toBe('r9')
    expect(store.phase).toBe('streaming')
  })

  it('dismissConflict 关闭 409 提示（发送恢复可用）', () => {
    const store = useRunStore()
    store.handleStreamError(new SSERequestError(409, 'busy'))
    expect(store.conflict).toBe(true)
    store.dismissConflict()
    expect(store.conflict).toBe(false)
  })

  it('approvePlan：POST 到计划批准端点并以 resume 语义消费其 SSE 流', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const sseBody =
      'event: run_started\ndata: {"v":1,"type":"run_started","run_id":"rp","conversation_id":9}\n\n' +
      'event: text_delta\ndata: {"v":1,"type":"text_delta","delta":"按计划执行"}\n\n' +
      'event: done\ndata: {"v":1,"type":"done","run_id":"rp"}\n\n'
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
        calls.push({ url: String(url), init })
        return {
          ok: true,
          status: 200,
          body: new ReadableStream<Uint8Array>({
            start(ctrl) {
              ctrl.enqueue(new TextEncoder().encode(sseBody))
              ctrl.close()
            },
          }),
        } as unknown as Response
      }),
    )
    try {
      const store = useRunStore()
      store.conversationId = 9
      store.planCard = { planId: 2, title: '三步走', steps: [] }
      await store.approvePlan()
      expect(calls[0].url).toBe('/ai/conversations/9/plans/2/approve')
      expect(calls[0].init?.method).toBe('POST')
      expect(store.planCard).toBeNull() // 新流 run_started 已结案旧计划卡
      expect(store.segments.some((s) => s.content === '按计划执行')).toBe(true)
      expect(store.phase).toBe('completed')
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('rejectPlan：POST 拒绝端点成功后本地清除计划卡；失败则记录 error 保留卡片', async () => {
    const calls: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string | URL | Request) => {
        calls.push(String(url))
        if (calls.length === 1) return jsonResponse({ ok: true })
        return jsonResponse({ detail: '计划不存在或已结案' }, 404)
      }),
    )
    try {
      const store = useRunStore()
      store.conversationId = 9
      store.planCard = { planId: 5, title: 't', steps: [] }
      await store.rejectPlan()
      expect(calls[0]).toBe('/ai/conversations/9/plans/5/reject')
      expect(store.planCard).toBeNull()

      store.planCard = { planId: 6, title: 't2', steps: [] }
      await store.rejectPlan()
      expect(store.planCard).not.toBeNull()
      expect(store.error?.message).toContain('计划不存在')
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
