import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import {
  useFocusStore,
  elapsedSecondsOf,
  formatElapsed,
  FOCUS_TICK_MS,
  FOCUS_RECONCILE_TICKS,
} from './focus'
import type { FocusLog } from '../api/focus'

function jsonResponse(payload: unknown, status = 200): Response {
  const text = payload === undefined ? '' : JSON.stringify(payload)
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => text,
    json: async () => (text ? JSON.parse(text) : undefined),
  } as unknown as Response
}

function makeLog(partial: Partial<FocusLog>): FocusLog {
  return {
    id: 1,
    task_id: null,
    task_title: '写周报',
    kind: 'focus',
    started_at: '2026-09-05T10:00:00',
    ended_at: null,
    minutes: 0,
    ...partial,
  }
}

/** 按 URL 分派响应的最小 fetch 桩；返回捕获到的请求记录 */
function stubFetch(handler: (url: string, init?: RequestInit) => Response): { calls: [string, RequestInit | undefined][] } {
  const calls: [string, RequestInit | undefined][] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: unknown, init?: RequestInit) => {
      calls.push([String(input), init])
      return handler(String(input), init)
    }),
  )
  return { calls }
}

/** 桩好 stats/current 两个只读端点的常用分派 */
function stubReads(opts: { totalMinutes: number; current: FocusLog | null }): { calls: [string, RequestInit | undefined][] } {
  return stubFetch((url, init) => {
    if (init?.method === 'POST' && url.includes('/api/focus/start')) return jsonResponse(makeLog({ id: 9 }), 201)
    if (init?.method === 'POST' && url.includes('/api/focus/stop')) return jsonResponse(makeLog({ ended_at: '2026-09-05T10:05:00' }))
    if (url.includes('/api/focus/stats')) return jsonResponse({ by_day: [], by_task: [], total_minutes: opts.totalMinutes })
    if (url.includes('/api/focus/current')) return jsonResponse(opts.current)
    return jsonResponse([])
  })
}

async function flush(): Promise<void> {
  await vi.advanceTimersByTimeAsync(0)
}

describe('focus 纯函数', () => {
  it('elapsedSecondsOf：由 started_at 推算已进行秒数', () => {
    expect(elapsedSecondsOf(null, Date.now())).toBe(0)
    const log = makeLog({ started_at: '2026-09-05T10:00:00' })
    const base = new Date('2026-09-05T10:00:00').getTime()
    expect(elapsedSecondsOf(log, base)).toBe(0)
    expect(elapsedSecondsOf(log, base + 90_500)).toBe(90)
    expect(elapsedSecondsOf(log, base - 5_000)).toBe(0) // 时钟回拨不出现负数
    expect(elapsedSecondsOf(makeLog({ started_at: 'not-a-date' }), base)).toBe(0)
  })

  it('formatElapsed：mm:ss，满一小时进位 h:mm:ss', () => {
    expect(formatElapsed(0)).toBe('00:00')
    expect(formatElapsed(5)).toBe('00:05')
    expect(formatElapsed(65)).toBe('01:05')
    expect(formatElapsed(3599)).toBe('59:59')
    expect(formatElapsed(3600)).toBe('1:00:00')
    expect(formatElapsed(3661)).toBe('1:01:01')
  })
})

describe('focus store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-05T10:00:00'))
  })

  afterEach(() => {
    useFocusStore().dispose()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('init：空闲态落定 current=null 与今日累计；进行中态恢复秒针', async () => {
    const idle = useFocusStore()
    stubReads({ totalMinutes: 42, current: null })
    await idle.init()
    expect(idle.current).toBeNull()
    expect(idle.isRunning).toBe(false)
    expect(idle.todayMinutes).toBe(42)

    vi.setSystemTime(new Date('2026-09-05T14:00:00'))
    const running = useFocusStore()
    stubReads({ totalMinutes: 42, current: makeLog({ started_at: '2026-09-05T13:59:30' }) })
    await running.init()
    expect(running.isRunning).toBe(true)
    expect(running.elapsedSeconds).toBe(30)
  })

  it('start：POST TimerStart（kind/task_title），置 current、起秒针、刷新今日累计', async () => {
    const store = useFocusStore()
    const { calls } = stubReads({ totalMinutes: 7, current: null })
    await store.start('focus', '读论文')
    const startCall = calls.find(([u, i]) => u.includes('/api/focus/start') && i?.method === 'POST')
    expect(startCall).toBeDefined()
    expect(JSON.parse(String(startCall![1]?.body))).toEqual({ kind: 'focus', task_title: '读论文' })
    expect(store.isRunning).toBe(true)
    expect(store.current?.task_title).toBe('写周报')
    expect(store.todayMinutes).toBe(7)
    expect(store.elapsedLabel).toBe('00:00')

    // 本地秒针：1s tick 推进，elapsed 由 started_at 推算（不问后端）
    await vi.advanceTimersByTimeAsync(FOCUS_TICK_MS * 5)
    expect(store.elapsedSeconds).toBe(5)
    const readCalls = calls.filter(([u]) => u.includes('/api/focus/current')).length
    await vi.advanceTimersByTimeAsync(FOCUS_TICK_MS * 5)
    expect(store.elapsedSeconds).toBe(10)
    // 秒针阶段不做额外对账（未到 45 tick）
    expect(calls.filter(([u]) => u.includes('/api/focus/current')).length).toBe(readCalls)
  })

  it('start 进行中重入被忽略；失败落 error 且不起秒针', async () => {
    const store = useFocusStore()
    const { calls } = stubReads({ totalMinutes: 0, current: null })
    await store.start('focus', 'A')
    const afterFirst = calls.length
    await store.start('break', 'B') // 已在进行中：忽略
    expect(calls.length).toBe(afterFirst)
    expect(store.current?.kind).toBe('focus')

    store.current = null
    stubFetch((_url, init) => {
      if (init?.method === 'POST') return jsonResponse({ detail: '别急' }, 422)
      return jsonResponse({ by_day: [], by_task: [], total_minutes: 0 })
    })
    await store.start('focus', 'C')
    expect(store.error).toBe('别急')
    expect(store.isRunning).toBe(false)
  })

  it('stop：POST stop 后 current 落定空、秒针停、今日累计刷新；随后瞬间的对账旧态被拒绝', async () => {
    const store = useFocusStore()
    stubReads({ totalMinutes: 3, current: null })
    await store.start('focus', 'A')
    expect(store.isRunning).toBe(true)

    const { calls: callsAfter } = stubReads({ totalMinutes: 25, current: makeLog({ id: 9, started_at: '2026-09-05T10:00:00' }) })
    await store.stop()
    expect(store.isRunning).toBe(false)
    expect(store.todayMinutes).toBe(25)

    // stop 之后 5s 内到达的 /current 旧态（stop 前的 current）不被采纳
    await store.reconcile()
    expect(store.isRunning).toBe(false)

    // 秒针已停：时间推进不再产生任何请求
    const total = callsAfter.length
    await vi.advanceTimersByTimeAsync(FOCUS_TICK_MS * FOCUS_RECONCILE_TICKS * 2)
    expect(callsAfter.length).toBe(total)
  })

  it('进行中每 45 个秒针对账一次 /current；远端已被其它端停止则以远端为准', async () => {
    // 模块级 lastStopAt 护栏跨用例共存：把系统时间推离上一用例的 stop 时刻（>5s 窗口）
    vi.setSystemTime(new Date('2026-09-05T12:00:00'))
    const store = useFocusStore()
    const { calls } = stubReads({ totalMinutes: 0, current: makeLog({ id: 5, started_at: '2026-09-05T11:59:30' }) })
    await store.init()
    expect(store.isRunning).toBe(true)
    calls.length = 0

    // 前 44 tick 不对账，第 45 tick 触发
    await vi.advanceTimersByTimeAsync(FOCUS_TICK_MS * (FOCUS_RECONCILE_TICKS - 1))
    expect(calls.filter(([u]) => u.includes('/api/focus/current')).length).toBe(0)
    await vi.advanceTimersByTimeAsync(FOCUS_TICK_MS)
    expect(calls.filter(([u]) => u.includes('/api/focus/current')).length).toBe(1)
    expect(store.isRunning).toBe(true)

    // 远端变为 null（其它端已停止）：本地以远端为准落定空
    stubReads({ totalMinutes: 9, current: null })
    await vi.advanceTimersByTimeAsync(FOCUS_TICK_MS * FOCUS_RECONCILE_TICKS)
    await flush()
    expect(store.isRunning).toBe(false)
    expect(store.todayMinutes).toBe(9)
  })

  it('refreshToday 失败落 error，不影响 current', async () => {
    const store = useFocusStore()
    stubFetch((url) => {
      if (url.includes('/api/focus/stats')) return jsonResponse({ detail: '统计挂了' }, 500)
      if (url.includes('/api/focus/current')) return jsonResponse(null)
      return jsonResponse([])
    })
    await store.init()
    expect(store.error).toBe('统计挂了')
    expect(store.current).toBeNull()
  })

  it('loadLogs：days=1 拉今日记录，按 started_at 倒序落定', async () => {
    const store = useFocusStore()
    const { calls } = stubFetch((url) => {
      if (url.includes('/api/focus/logs')) {
        return jsonResponse([
          makeLog({ id: 1, started_at: '2026-09-05T09:00:00', ended_at: '2026-09-05T09:25:00', minutes: 25 }),
          makeLog({ id: 2, started_at: '2026-09-05T11:00:00', ended_at: null, minutes: 0 }),
          makeLog({ id: 3, started_at: '2026-09-05T10:00:00', ended_at: '2026-09-05T10:30:00', minutes: 30 }),
        ])
      }
      if (url.includes('/api/focus/stats')) return jsonResponse({ by_day: [], by_task: [], total_minutes: 55 })
      return jsonResponse(null)
    })
    expect(store.logs).toBeNull()
    await store.loadLogs()
    const logsCall = calls.find(([u]) => u.includes('/api/focus/logs'))
    expect(logsCall).toBeDefined()
    expect(logsCall![0]).toContain('/api/focus/logs?days=1')
    expect(store.logs?.map((l) => l.id)).toEqual([2, 3, 1]) // 最新在最上
    expect(store.logsLoading).toBe(false)
    expect(store.logsError).toBeNull()
  })

  it('loadLogs 失败落 logsError，logs 保持 null', async () => {
    const store = useFocusStore()
    stubFetch((url) => {
      if (url.includes('/api/focus/logs')) return jsonResponse({ detail: '记录挂了' }, 500)
      return jsonResponse(null)
    })
    await store.loadLogs()
    expect(store.logs).toBeNull()
    expect(store.logsError).toBe('记录挂了')
    expect(store.logsLoading).toBe(false)
  })

  it('removeLog：DELETE 到正确 URL、出列并经 stats 刷新今日累计', async () => {
    const store = useFocusStore()
    stubFetch((url, init) => {
      if (init?.method === 'DELETE') return jsonResponse(undefined, 204)
      if (url.includes('/api/focus/logs')) {
        return jsonResponse([
          makeLog({ id: 7, started_at: '2026-09-05T10:00:00', ended_at: '2026-09-05T10:25:00', minutes: 25 }),
          makeLog({ id: 8, started_at: '2026-09-05T11:00:00', ended_at: '2026-09-05T11:30:00', minutes: 30 }),
        ])
      }
      if (url.includes('/api/focus/stats')) return jsonResponse({ by_day: [], by_task: [], total_minutes: 30 })
      return jsonResponse(null)
    })
    await store.loadLogs()
    expect(store.logs?.map((l) => l.id)).toEqual([8, 7]) // started_at 倒序

    const ok = await store.removeLog(7)
    expect(ok).toBe(true)
    expect(store.todayMinutes).toBe(30) // 删除后 stats(days=1) 重新拉过
    expect(store.logs?.map((l) => l.id)).toEqual([8])
    expect(store.logActionError).toBeNull()
  })

  it('removeLog 409：保留该条、logActionError 可见、返回 false', async () => {
    const store = useFocusStore()
    stubFetch((url, init) => {
      if (init?.method === 'DELETE') return jsonResponse({ detail: '运行中的计时不可删除' }, 409)
      if (url.includes('/api/focus/logs')) {
        return jsonResponse([makeLog({ id: 7, started_at: '2026-09-05T10:00:00', ended_at: null })])
      }
      if (url.includes('/api/focus/stats')) return jsonResponse({ by_day: [], by_task: [], total_minutes: 5 })
      return jsonResponse(null)
    })
    await store.loadLogs()
    const ok = await store.removeLog(7)
    expect(ok).toBe(false)
    expect(store.logActionError).toBe('该计时仍在进行中或删除失败')
    expect(store.logs?.map((l) => l.id)).toEqual([7]) // 该条保留
  })

  it('stop 成功后顺带刷新今日记录（仅当已加载过；start 不主动拉）', async () => {
    const store = useFocusStore()
    let logsFetched = 0
    stubFetch((url, init) => {
      if (init?.method === 'POST' && url.includes('/api/focus/start')) return jsonResponse(makeLog({ id: 9 }), 201)
      if (init?.method === 'POST' && url.includes('/api/focus/stop')) {
        return jsonResponse(makeLog({ id: 9, ended_at: '2026-09-05T10:05:00', minutes: 5 }))
      }
      if (url.includes('/api/focus/logs')) {
        logsFetched += 1
        return jsonResponse([makeLog({ id: 9, ended_at: '2026-09-05T10:05:00', minutes: 5 })])
      }
      if (url.includes('/api/focus/stats')) return jsonResponse({ by_day: [], by_task: [], total_minutes: 5 })
      return jsonResponse(null)
    })

    await store.start('focus', 'A')
    await store.stop()
    expect(logsFetched).toBe(0) // 从未打开过记录面板：stop 不主动拉

    await store.loadLogs()
    expect(logsFetched).toBe(1)

    await store.start('break', 'B')
    await store.stop()
    expect(logsFetched).toBe(2) // 已加载过：stop 后新结账记录立即入列
    expect(store.logs?.map((l) => l.id)).toEqual([9])
  })
})
