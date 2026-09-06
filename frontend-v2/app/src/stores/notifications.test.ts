import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useNotificationsStore, NOTIFICATIONS_POLL_MS } from './notifications'
import type { Notification } from '../api/notifications'

function jsonResponse(payload: unknown, status = 200): Response {
  const text = payload === undefined ? '' : JSON.stringify(payload)
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => text,
    json: async () => (text ? JSON.parse(text) : undefined),
  } as unknown as Response
}

function makeNotification(partial: Partial<Notification>): Notification {
  return {
    id: 1,
    task_id: null,
    kind: 'reminder',
    title: '任务提醒',
    body: '「写周报」该开始了',
    remind_at: '2026-09-05T15:00:00',
    read_at: null,
    ...partial,
  }
}

/** 按 URL 分派响应的最小 fetch 桩；返回捕获到的请求记录 */
function stubFetch(handler: (url: string, init?: RequestInit) => Response): { calls: string[] } {
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: unknown, init?: RequestInit) => {
      calls.push(String(input))
      return handler(String(input), init)
    }),
  )
  return { calls }
}

function stubUnread(count: number): { calls: string[] } {
  return stubFetch((url) => {
    if (url.includes('/api/notifications/unread')) return jsonResponse({ count })
    return jsonResponse([])
  })
}

/** 刷掉 refreshUnread 的微任务链（fetch 桩是 async） */
async function flush(): Promise<void> {
  await vi.advanceTimersByTimeAsync(0)
}

describe('notifications store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })

  afterEach(() => {
    useNotificationsStore().stopPolling()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('startPolling：立即拉一次未读数，此后每 30s 一 tick', async () => {
    const store = useNotificationsStore()
    const { calls } = stubUnread(3)
    store.startPolling()
    await flush()
    expect(store.unreadCount).toBe(3)
    expect(calls).toHaveLength(1)

    await vi.advanceTimersByTimeAsync(NOTIFICATIONS_POLL_MS)
    expect(calls).toHaveLength(2)
    await vi.advanceTimersByTimeAsync(NOTIFICATIONS_POLL_MS)
    expect(calls).toHaveLength(3)
  })

  it('startPolling 幂等：重复调用不叠加定时器', async () => {
    const store = useNotificationsStore()
    const { calls } = stubUnread(0)
    store.startPolling()
    store.startPolling()
    store.startPolling()
    await flush()
    await vi.advanceTimersByTimeAsync(NOTIFICATIONS_POLL_MS)
    // 立即 1 次 + 每个 30s 周期 1 次（而非 3 次）
    expect(calls).toHaveLength(2)
  })

  it('页面隐藏时暂停 tick；恢复可见立即补拉', async () => {
    const doc = {
      visibilityState: 'hidden',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }
    vi.stubGlobal('document', doc)
    const store = useNotificationsStore()
    const { calls } = stubUnread(1)
    store.startPolling()
    await flush()
    expect(calls).toHaveLength(1)

    // 隐藏期间：tick 空转不发请求
    await vi.advanceTimersByTimeAsync(NOTIFICATIONS_POLL_MS * 3)
    expect(calls).toHaveLength(1)

    // 恢复可见：visibilitychange 监听器立即补拉一次
    expect(doc.addEventListener).toHaveBeenCalledWith('visibilitychange', expect.any(Function))
    doc.visibilityState = 'visible'
    const onVisible = doc.addEventListener.mock.calls.find((c) => c[0] === 'visibilitychange')?.[1] as () => void
    onVisible()
    await flush()
    expect(calls).toHaveLength(2)

    // 可见期间恢复常规轮询
    await vi.advanceTimersByTimeAsync(NOTIFICATIONS_POLL_MS)
    expect(calls).toHaveLength(3)
  })

  it('stopPolling：interval 与可见性监听一并清理，之后不再发请求', async () => {
    const doc = { visibilityState: 'visible', addEventListener: vi.fn(), removeEventListener: vi.fn() }
    vi.stubGlobal('document', doc)
    const store = useNotificationsStore()
    const { calls } = stubUnread(2)
    store.startPolling()
    await flush()
    expect(calls).toHaveLength(1)

    store.stopPolling()
    store.stopPolling() // 幂等
    expect(doc.removeEventListener).toHaveBeenCalledWith('visibilitychange', expect.any(Function))
    await vi.advanceTimersByTimeAsync(NOTIFICATIONS_POLL_MS * 2)
    expect(calls).toHaveLength(1)
  })

  it('openPanel：并发拉列表 + 未读数并落定', async () => {
    const store = useNotificationsStore()
    stubFetch((url) => {
      if (url.includes('/api/notifications/unread')) return jsonResponse({ count: 1 })
      if (url.includes('/api/notifications?')) {
        return jsonResponse([makeNotification({ id: 7 }), makeNotification({ id: 6, read_at: '2026-09-05T10:00:00' })])
      }
      return jsonResponse({ detail: 'boom' }, 500)
    })
    await store.openPanel()
    expect(store.panelOpen).toBe(true)
    expect(store.loading).toBe(false)
    expect(store.notifications?.map((n) => n.id)).toEqual([7, 6])
    expect(store.unreadCount).toBe(1)
    expect(store.error).toBeNull()
  })

  it('openPanel 失败：error 落定，notifications 保持 null', async () => {
    const store = useNotificationsStore()
    stubFetch(() => jsonResponse({ detail: '网络炸了' }, 500))
    await store.openPanel()
    expect(store.panelOpen).toBe(true)
    expect(store.error).toBe('网络炸了')
    expect(store.notifications).toBeNull()
  })

  it('markRead：未读落章并扣减未读数；失败落 actionError；已读项不白发请求', async () => {
    const store = useNotificationsStore()
    let failRead = false
    const { calls } = stubFetch((url, init) => {
      if (init?.method === 'POST' && url.endsWith('/api/notifications/7/read')) {
        return failRead ? jsonResponse({ detail: '已读失败' }, 500) : jsonResponse({ ok: true })
      }
      if (url.includes('/unread')) return jsonResponse({ count: 2 })
      return jsonResponse([makeNotification({ id: 7 }), makeNotification({ id: 8, read_at: '2026-09-05T09:00:00' })])
    })
    await store.openPanel()
    expect(store.unreadCount).toBe(2)

    await store.markRead(7)
    expect(store.notifications?.[0].read_at).not.toBeNull()
    expect(store.unreadCount).toBe(1)
    expect(store.actionError).toBeNull()

    const readCalls = calls.filter((u) => u.endsWith('/7/read')).length
    await store.markRead(7) // 已是已读：不白发请求
    await store.markRead(8) // 已读项：不白发请求
    expect(calls.filter((u) => u.endsWith('/7/read')).length).toBe(readCalls)

    failRead = true
    store.notifications![0].read_at = null // 复位为未读，再触发一次失败
    await store.markRead(7)
    expect(store.actionError).toBe('已读失败')
    expect(store.unreadCount).toBe(1)
  })

  it('markAllRead：面板未读全部就地落章、未读数清零；失败落 actionError 不动本地', async () => {
    const store = useNotificationsStore()
    let fail = false
    stubFetch((_url, init) => {
      if (init?.method === 'POST' && _url.includes('/read-all')) {
        return fail ? jsonResponse({ detail: '批量失败' }, 500) : jsonResponse({ ok: true })
      }
      if (_url.includes('/unread')) return jsonResponse({ count: 2 })
      return jsonResponse([makeNotification({ id: 1 }), makeNotification({ id: 2 }), makeNotification({ id: 3, read_at: '2026-09-05T09:00:00' })])
    })
    await store.openPanel()
    await store.markAllRead()
    expect(store.notifications?.every((n) => n.read_at !== null)).toBe(true)
    expect(store.unreadCount).toBe(0)
    expect(store.markingAll).toBe(false)

    store.notifications![0].read_at = null
    fail = true
    await store.markAllRead()
    expect(store.actionError).toBe('批量失败')
    expect(store.notifications![0].read_at).toBeNull()
    expect(store.unreadCount).toBe(0)
  })
})
