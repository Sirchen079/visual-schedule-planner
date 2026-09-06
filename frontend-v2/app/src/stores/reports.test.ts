import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useReportsStore } from './reports'
import type { Report } from '../api/reports'

function jsonResponse(payload: unknown, status = 200): Response {
  const text = payload === undefined ? '' : JSON.stringify(payload)
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => text,
    json: async () => (text ? JSON.parse(text) : undefined),
  } as unknown as Response
}

function makeReport(partial: Partial<Report>): Report {
  return {
    id: 1,
    report_type: 'daily',
    period_start: '2026-09-05',
    period_end: '2026-09-05',
    title: '日报 2026-09-05',
    content: '**今日** 完成 3 件事',
    model_name: 'glm-5.3-flash',
    created_at: '2026-09-05T08:00:00',
    ...partial,
  }
}

/** 按 URL 分派响应的最小 fetch 桩；返回捕获到的请求记录 */
function stubFetch(handler: (url: string, init?: RequestInit) => Response): { calls: [string, RequestInit | undefined][] } {
  const calls: [string, RequestInit | undefined][] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: unknown, init?: RequestInit) => {
      const url = String(input)
      calls.push([url, init])
      return handler(url, init)
    }),
  )
  return { calls }
}

describe('reports store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('load 成功：落定列表并默认选中首条', async () => {
    const store = useReportsStore()
    stubFetch(() => jsonResponse([makeReport({ id: 2 }), makeReport({ id: 1 })]))
    await store.load()
    expect(store.reports).toHaveLength(2)
    expect(store.selectedId).toBe(2)
    expect(store.selected?.title).toBe('日报 2026-09-05')
    expect(store.error).toBeNull()
  })

  it('load 失败：error 落定，reports 保持原状', async () => {
    const store = useReportsStore()
    stubFetch(() => jsonResponse({ detail: 'boom' }, 500))
    await store.load()
    expect(store.error).toBe('boom')
    expect(store.reports).toBeNull()
  })

  it('setFilter 带 report_type 查询参数重拉；选中项被过滤掉时回落首条', async () => {
    const store = useReportsStore()
    const { calls } = stubFetch((url) => {
      if (url.includes('report_type=weekly')) return jsonResponse([makeReport({ id: 9, report_type: 'weekly' })])
      return jsonResponse([makeReport({ id: 1 }), makeReport({ id: 2, report_type: 'weekly' })])
    })
    await store.load()
    expect(store.selectedId).toBe(1)
    await store.setFilter('weekly')
    expect(calls[1][0]).toContain('report_type=weekly')
    expect(store.selectedId).toBe(9)
  })

  it('generate 成功：新报表插入头部并选中', async () => {
    const store = useReportsStore()
    stubFetch((_url, init) => {
      if (init?.method === 'POST') return jsonResponse(makeReport({ id: 3, title: '日报 2026-09-05 (2)' }))
      return jsonResponse([makeReport({ id: 1 })])
    })
    await store.load()
    await store.generate('daily')
    expect(store.reports?.[0].id).toBe(3)
    expect(store.selectedId).toBe(3)
    expect(store.actionError).toBeNull()
  })

  it('generate 422（LLM 不可用）：actionError 透出后端 detail，列表不动', async () => {
    const store = useReportsStore()
    stubFetch((_url, init) => {
      if (init?.method === 'POST') return jsonResponse({ detail: '报告生成失败：429 额度' }, 422)
      return jsonResponse([makeReport({ id: 1 })])
    })
    await store.load()
    await store.generate('weekly')
    expect(store.actionError).toBe('报告生成失败：429 额度')
    expect(store.reports).toHaveLength(1)
    expect(store.generating).toEqual([])
  })

  it('generate 同类型进行中不并发', async () => {
    const store = useReportsStore()
    let resolvePost: ((r: Response) => void) | null = null
    vi.stubGlobal(
      'fetch',
      vi.fn((_input: unknown, init?: RequestInit) => {
        if (init?.method === 'POST') return new Promise<Response>((res) => (resolvePost = res))
        return Promise.resolve(jsonResponse([]))
      }),
    )
    await store.load()
    const p1 = store.generate('daily')
    const p2 = store.generate('daily')
    expect(store.generating).toEqual(['daily'])
    resolvePost!(jsonResponse(makeReport({ id: 5 })))
    await Promise.all([p1, p2])
    expect(store.reports?.map((r) => r.id)).toEqual([5])
  })

  it('remove 成功：移除并回落选中；失败落 actionError', async () => {
    const store = useReportsStore()
    let failDelete = false
    stubFetch((_url, init) => {
      if (init?.method === 'DELETE') return failDelete ? jsonResponse({ detail: '报告不存在' }, 404) : jsonResponse(undefined, 204)
      return jsonResponse([makeReport({ id: 1 }), makeReport({ id: 2 })])
    })
    await store.load()
    expect(store.selectedId).toBe(1)
    await store.remove(1)
    expect(store.reports?.map((r) => r.id)).toEqual([2])
    expect(store.selectedId).toBe(2)

    failDelete = true
    await store.remove(2)
    expect(store.actionError).toBe('报告不存在')
    expect(store.reports).toHaveLength(1)
  })
})
