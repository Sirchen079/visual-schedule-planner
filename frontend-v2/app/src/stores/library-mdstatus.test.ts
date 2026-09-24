import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { MD_POLL_INTERVAL_MS, mdStatusLabel, useLibraryStore } from './library'
import type { LibraryFile } from '../api/files'

function jsonResponse(payload: unknown, status = 200): Response {
  const text = JSON.stringify(payload)
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => text,
    json: async () => JSON.parse(text),
  } as unknown as Response
}

function makeFile(partial: Partial<LibraryFile>): LibraryFile {
  return {
    id: 1,
    original_name: '扫描件.pdf',
    storage_path: 'attachments\\扫描件.pdf',
    size: 2048,
    mime_type: 'application/pdf',
    notes: '',
    source_url: null,
    resource_type: 'file',
    parse_status: 'parsed',
    md_status: 'none',
    uploaded_at: '2026-09-20T10:00:00',
    ...partial,
  }
}

interface Recorded { url: string; method: string }

describe('mdStatusLabel（Markdown 副本状态角标）', () => {
  it('枚举映射：done/pending/failed 有文案，none 不展示，未知保留原值', () => {
    expect(mdStatusLabel('done')).toBe('已转 Markdown')
    expect(mdStatusLabel('pending')).toBe('OCR 识别中')
    expect(mdStatusLabel('failed')).toBe('识别失败')
    expect(mdStatusLabel('none')).toBe('')
    expect(mdStatusLabel('weird')).toBe('weird')
  })
})

describe('library store：md_status 轮询与重新解析', () => {
  let calls: Recorded[]
  let fetchMock: ReturnType<typeof vi.fn>

  function stubFetch(handler: (url: string, method: string) => Response | Promise<Response>): void {
    fetchMock = vi.fn(async (input: unknown, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      calls.push({ url, method })
      return await handler(url, method)
    })
    vi.stubGlobal('fetch', fetchMock)
  }

  function callsTo(path: string, method: string): Recorded[] {
    return calls.filter((c) => c.url.includes(path) && c.method === method)
  }

  beforeEach(() => {
    setActivePinia(createPinia())
    calls = []
    vi.useFakeTimers()
  })

  afterEach(() => {
    useLibraryStore().stopAllMdPolling()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('syncMdPolling：pending 行按 3s 轮询详情，进入 done 原位更新并自动停表', async () => {
    let mdStatus = 'pending'
    stubFetch((url, method) => {
      if (method === 'GET' && url.endsWith('/api/files/1')) {
        return jsonResponse(makeFile({ id: 1, md_status: mdStatus }))
      }
      return jsonResponse({ detail: 'unexpected' }, 404)
    })

    const store = useLibraryStore()
    store.items = [makeFile({ id: 1, md_status: 'pending' })]
    store.syncMdPolling()

    // 间隔未到不发请求
    await vi.advanceTimersByTimeAsync(MD_POLL_INTERVAL_MS - 1)
    expect(callsTo('/api/files/1', 'GET')).toHaveLength(0)

    // 第一次 tick：仍是 pending，继续轮询
    await vi.advanceTimersByTimeAsync(MD_POLL_INTERVAL_MS)
    expect(callsTo('/api/files/1', 'GET')).toHaveLength(1)

    // 后端转 done：写回列表并停表
    mdStatus = 'done'
    await vi.advanceTimersByTimeAsync(MD_POLL_INTERVAL_MS)
    expect(store.items?.[0].md_status).toBe('done')

    const callsAtStop = callsTo('/api/files/1', 'GET').length
    await vi.advanceTimersByTimeAsync(MD_POLL_INTERVAL_MS * 3)
    expect(callsTo('/api/files/1', 'GET')).toHaveLength(callsAtStop)
  })

  it('stopAllMdPolling：视图卸载后不再发请求', async () => {
    stubFetch(() => jsonResponse(makeFile({ id: 1, md_status: 'pending' })))
    const store = useLibraryStore()
    store.items = [makeFile({ id: 1, md_status: 'pending' })]
    store.syncMdPolling()
    store.stopAllMdPolling()
    await vi.advanceTimersByTimeAsync(MD_POLL_INTERVAL_MS * 2)
    expect(calls).toHaveLength(0)
  })

  it('轮询连续失败 3 次自动停表（行保持最后已知状态）', async () => {
    stubFetch(() => jsonResponse({ detail: 'db locked' }, 500))
    const store = useLibraryStore()
    store.items = [makeFile({ id: 1, md_status: 'pending' })]
    store.syncMdPolling()
    await vi.advanceTimersByTimeAsync(MD_POLL_INTERVAL_MS * 3)
    expect(callsTo('/api/files/1', 'GET')).toHaveLength(3)
    await vi.advanceTimersByTimeAsync(MD_POLL_INTERVAL_MS * 2)
    expect(callsTo('/api/files/1', 'GET')).toHaveLength(3)
    expect(store.items?.[0].md_status).toBe('pending')
  })

  it('syncMdPolling：非 pending 行重复调用不会叠加定时器', async () => {
    stubFetch(() => jsonResponse(makeFile({ id: 1, md_status: 'pending' })))
    const store = useLibraryStore()
    store.items = [makeFile({ id: 1, md_status: 'pending' })]
    store.syncMdPolling()
    store.syncMdPolling()
    await vi.advanceTimersByTimeAsync(MD_POLL_INTERVAL_MS)
    expect(callsTo('/api/files/1', 'GET')).toHaveLength(1)
  })

  it('reparse：POST 后原位更新；返回 pending 时接续轮询', async () => {
    stubFetch((url, method) => {
      if (method === 'POST' && url.endsWith('/api/files/1/reparse')) {
        return jsonResponse(makeFile({ id: 1, md_status: 'pending', parse_status: 'pending' }))
      }
      if (method === 'GET' && url.endsWith('/api/files/1')) {
        return jsonResponse(makeFile({ id: 1, md_status: 'done' }))
      }
      return jsonResponse({ detail: 'unexpected' }, 404)
    })

    const store = useLibraryStore()
    store.items = [makeFile({ id: 1, md_status: 'failed' })]
    const row = await store.reparse(1)
    expect(row?.md_status).toBe('pending')
    expect(callsTo('/api/files/1/reparse', 'POST')).toHaveLength(1)
    expect(store.items?.[0].md_status).toBe('pending')

    // reparse 后自动进入轮询：一个间隔后拉到 done 并写回
    await vi.advanceTimersByTimeAsync(MD_POLL_INTERVAL_MS)
    expect(callsTo('/api/files/1', 'GET')).toHaveLength(1)
    expect(store.items?.[0].md_status).toBe('done')
  })

  it('reparse：同步重建完成（none/done）时不启动轮询', async () => {
    stubFetch(() => jsonResponse(makeFile({ id: 1, md_status: 'none' })))
    const store = useLibraryStore()
    store.items = [makeFile({ id: 1, md_status: 'failed' })]
    await store.reparse(1)
    await vi.advanceTimersByTimeAsync(MD_POLL_INTERVAL_MS * 2)
    expect(callsTo('/api/files/1', 'GET')).toHaveLength(0)
  })

  it('reparse：422 解析失败时 actionError 带 detail，列表不变', async () => {
    stubFetch(() => jsonResponse({ detail: '文件已损坏，无法解析' }, 422))
    const store = useLibraryStore()
    store.items = [makeFile({ id: 1, md_status: 'failed' })]
    const row = await store.reparse(1)
    expect(row).toBeNull()
    expect(store.actionError).toContain('文件已损坏，无法解析')
    expect(store.items?.[0].md_status).toBe('failed')
    await vi.advanceTimersByTimeAsync(MD_POLL_INTERVAL_MS)
    expect(calls).toHaveLength(1) // 只有 reparse 本身，没有轮询
  })

  it('remove：软删除后停止该文件的轮询', async () => {
    stubFetch(() => jsonResponse({ detail: 'db locked' }, 500))
    const store = useLibraryStore()
    store.items = [makeFile({ id: 1, md_status: 'pending' })]
    store.syncMdPolling()
    await store.remove(1)
    await vi.advanceTimersByTimeAsync(MD_POLL_INTERVAL_MS * 2)
    // 只有 remove 自己的 DELETE，没有任何轮询 GET
    expect(calls.filter((c) => c.method === 'GET')).toHaveLength(0)
    expect(calls).toHaveLength(1)
  })
})
