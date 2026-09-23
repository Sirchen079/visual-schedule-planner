import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useMemoriesStore } from './memories'
import type { MemoryItem } from '../api/memories'

function jsonResponse(payload: unknown, status = 200): Response {
  const text = payload === undefined ? '' : JSON.stringify(payload)
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => text,
    json: async () => (text ? JSON.parse(text) : undefined),
  } as unknown as Response
}

function makeMemory(partial: Partial<MemoryItem>): MemoryItem {
  return {
    id: 1,
    kind: 'preference',
    content: '用户偏好喝美式咖啡',
    keywords: '咖啡 偏好',
    source: 'ai',
    source_conversation_id: null,
    created_at: '2026-09-20T08:00:00',
    updated_at: '2026-09-21T09:30:00',
    ...partial,
  }
}

/** 按 URL/方法分派响应的最小 fetch 桩；返回捕获到的请求记录 */
function stubFetch(handler: (url: string, init?: RequestInit) => Response): { calls: { url: string; init?: RequestInit }[] } {
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: unknown, init?: RequestInit) => {
      calls.push({ url: String(input), init })
      return handler(String(input), init)
    }),
  )
  return { calls }
}

describe('memories store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('load：并行拉列表与开关，开关默认开；失败落 error 可重试', async () => {
    const store = useMemoriesStore()
    expect(store.enabled).toBeNull() // 未加载不预设
    const { calls } = stubFetch((url) => {
      if (url.includes('/api/memories/enabled')) return jsonResponse({ enabled: true })
      return jsonResponse([makeMemory({})])
    })
    await store.load()
    expect(store.items).toHaveLength(1)
    expect(store.enabled).toBe(true)
    expect(calls.map((c) => c.url.split('/api')[1]).sort()).toEqual(['/memories', '/memories/enabled'])

    stubFetch(() => jsonResponse({ detail: '加载失败' }, 500))
    await store.load()
    expect(store.error).toBe('加载失败')
  })

  it('add：POST source 由后端落 user，成功后就地插入列表头部', async () => {
    const store = useMemoriesStore()
    stubFetch((url, init) => {
      if (url.endsWith('/api/memories') && init?.method === 'POST') {
        return jsonResponse(makeMemory({ id: 2, source: 'user', content: '回复要简短' }), 201)
      }
      return jsonResponse([])
    })
    const ok = await store.add({ kind: 'preference', content: '回复要简短' })
    expect(ok).toBe(true)
    expect(store.items?.map((i) => i.id)).toEqual([2])
    expect(store.adding).toBe(false)
  })

  it('edit：PATCH 后就地替换该条；remove：DELETE 后就地移除', async () => {
    const store = useMemoriesStore()
    store.items = [makeMemory({ id: 1 }), makeMemory({ id: 2, kind: 'fact', content: '第二条' })]
    stubFetch((url, init) => {
      if (url.endsWith('/api/memories/1') && init?.method === 'PATCH') {
        return jsonResponse(makeMemory({ id: 1, content: '已更新', updated_at: '2026-09-22T10:00:00' }))
      }
      if (url.endsWith('/api/memories/2') && init?.method === 'DELETE') return jsonResponse({ ok: true })
      return jsonResponse({}, 404)
    })
    expect(await store.edit(1, { content: '已更新' })).toBe(true)
    expect(store.items?.[0].content).toBe('已更新')
    expect(await store.remove(2)).toBe(true)
    expect(store.items?.map((i) => i.id)).toEqual([1])
    expect(store.busyIds).toEqual([])
  })

  it('groupedByKind：固定 kind 顺序分组，空组不出现', () => {
    const store = useMemoriesStore()
    store.items = [
      makeMemory({ id: 1, kind: 'fact' }),
      makeMemory({ id: 2, kind: 'profile' }),
      makeMemory({ id: 3, kind: 'fact' }),
    ]
    expect(store.groupedByKind.map((g) => g.kind)).toEqual(['profile', 'fact'])
    expect(store.groupedByKind[1].items).toHaveLength(2)
  })

  it('toggle：PUT 写开关并落回 store；失败不动本地状态', async () => {
    const store = useMemoriesStore()
    store.enabled = true
    const { calls } = stubFetch((_url, init) => (
      jsonResponse({ enabled: init ? JSON.parse(String(init.body)).enabled : true })
    ))
    expect(await store.toggle(false)).toBe(true)
    expect(store.enabled).toBe(false)
    expect(calls[0].init?.method).toBe('PUT')
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ enabled: false })

    stubFetch(() => jsonResponse({ detail: '开关保存失败' }, 500))
    expect(await store.toggle(true)).toBe(false)
    expect(store.enabled).toBe(false) // 失败不翻转
    expect(store.actionError).toBe('开关保存失败')
  })
})
