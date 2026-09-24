// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { nextTick, type App, createApp } from 'vue'
import LibraryView from './LibraryView.vue'
import { MD_POLL_INTERVAL_MS } from '../stores/library'
import type { LibraryFile } from '../api/files'

function jsonResponse(payload: unknown, status = 200): Response {
  const text = payload === undefined ? '' : JSON.stringify(payload)
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => text,
    json: async () => (text ? JSON.parse(text) : undefined),
  } as unknown as Response
}

function makeFile(partial: Partial<LibraryFile>): LibraryFile {
  return {
    id: 1,
    original_name: '讲义.pdf',
    storage_path: 'attachments\\讲义.pdf',
    size: 4096,
    mime_type: 'application/pdf',
    notes: '',
    source_url: null,
    resource_type: 'file',
    parse_status: 'parsed',
    md_status: 'none',
    uploaded_at: '2026-09-21T10:00:00',
    ...partial,
  }
}

/** 列表固件：none 无角标、pending 轮询、failed 可重解析、done 有「已转 Markdown」。 */
const FIXTURE: LibraryFile[] = [
  makeFile({ id: 1, md_status: 'none' }),
  makeFile({ id: 2, original_name: '扫描件A.pdf', md_status: 'pending' }),
  makeFile({ id: 3, original_name: '扫描件B.pdf', md_status: 'failed' }),
  makeFile({ id: 4, original_name: '笔记.docx', md_status: 'done' }),
]

interface Recorded { url: string; method: string; body: unknown }
let calls: Recorded[]
/** 轮询 GET /api/files/2 的回包状态 */
let pollStatus: string

function stubBackend(): void {
  calls = []
  pollStatus = 'pending'
  vi.stubGlobal('fetch', vi.fn(async (input: unknown, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    calls.push({ url, method, body: init?.body })
    if (method === 'GET' && /\/api\/files\/2$/.test(url)) return jsonResponse(makeFile({ id: 2, md_status: pollStatus }))
    if (method === 'POST' && /\/api\/files\/3\/reparse$/.test(url)) {
      return jsonResponse(makeFile({ id: 3, md_status: 'pending', parse_status: 'pending' }))
    }
    if (method === 'GET' && /\/api\/files\/3$/.test(url)) return jsonResponse(makeFile({ id: 3, md_status: 'done' }))
    if (method === 'GET' && /\/api\/files$/.test(url)) return jsonResponse(FIXTURE)
    if (method === 'GET' && url.includes('/api/settings/ocr')) {
      return jsonResponse({ base_url: '', model: '', has_api_key: false })
    }
    return jsonResponse({ detail: 'unexpected' }, 404)
  }))
}

function methodCalls(method: string, urlPart: string): Recorded[] {
  return calls.filter((w) => w.method === method && w.url.includes(urlPart))
}

const flush = async (): Promise<void> => {
  await vi.advanceTimersByTimeAsync(0)
  await nextTick()
}

let router: Router
let app: App | null = null

async function mountView(): Promise<HTMLElement> {
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/library', component: LibraryView },
      { path: '/settings', component: { template: '<div data-settings-stub />' } },
    ],
  })
  await router.push('/library')
  await router.isReady()
  const host = document.createElement('div')
  document.body.innerHTML = ''
  // Teleport 目标（真实壳层由 App.vue 提供）；缺失会让 Teleport defer 的补丁报 null vnode
  const headActions = document.createElement('div')
  headActions.id = 'head-actions'
  document.body.appendChild(headActions)
  document.body.appendChild(host)
  app = createApp(LibraryView)
  app.use(createPinia())
  app.use(router)
  app.mount(host)
  await flush()
  return host
}

describe('LibraryView（jsdom）：md_status 角标 / 轮询 / 重新解析', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    stubBackend()
  })

  afterEach(async () => {
    app?.unmount()
    app = null
    document.body.innerHTML = ''
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('按 md_status 渲染角标：none 不显示、pending/failed/done 各有文案', async () => {
    const root = await mountView()
    const badges = Array.from(root.querySelectorAll<HTMLSpanElement>('.row-parse[data-s^="md-"]'))
    expect(badges.map((b) => b.getAttribute('data-s'))).toEqual(['md-pending', 'md-failed', 'md-done'])
    expect(badges.map((b) => b.textContent?.trim())).toEqual(['OCR 识别中', '识别失败', '已转 Markdown'])
    // 普通 parse 角标仍在
    expect(root.querySelectorAll('.row-parse[data-s="parsed"]').length).toBe(4)
  })

  it('OCR 未配置：failed 行出现「OCR 未配置」引导链接，指向设置页', async () => {
    const root = await mountView()
    const link = root.querySelector<HTMLAnchorElement>('a.md-setup')
    expect(link).not.toBeNull()
    expect(link!.getAttribute('href')).toBe('/settings?section=ocr')
    expect(link!.textContent).toContain('OCR 未配置')
    // 只有 failed 行有引导
    expect(root.querySelectorAll('a.md-setup').length).toBe(1)
  })

  it('failed 行「重新解析」：POST reparse 后行原位变 pending，随后轮询到 done', async () => {
    const root = await mountView()
    const btn = Array.from(root.querySelectorAll<HTMLButtonElement>('.md-actions .mini'))
      .find((b) => b.textContent?.includes('重新解析'))
    expect(btn).toBeDefined()
    btn!.click()
    await flush()

    expect(methodCalls('POST', '/reparse')).toHaveLength(1)
    // 行原位更新为 pending 角标
    const failedBadge = root.querySelector('.row-parse[data-s="md-pending"]')
    expect(failedBadge).not.toBeNull()

    // reparse 返回 pending 自动接续轮询：3s 后拉到 done 并写回
    await vi.advanceTimersByTimeAsync(MD_POLL_INTERVAL_MS)
    await nextTick()
    expect(methodCalls('GET', '/api/files/3')).toHaveLength(1)
    expect(root.querySelector('.row-parse[data-s="md-done"]')?.textContent?.trim()).toBe('已转 Markdown')
  })

  it('pending 行按 3s 轮询单文件详情，进入 done 停止', async () => {
    const root = await mountView()
    // 第一次 tick：回 pending，继续轮询
    await vi.advanceTimersByTimeAsync(MD_POLL_INTERVAL_MS)
    await nextTick()
    expect(methodCalls('GET', '/api/files/2')).toHaveLength(1)
    expect(root.querySelector('.row-parse[data-s="md-pending"]')).not.toBeNull()
    // 第二次 tick：后端转 done → 写回角标并停表
    pollStatus = 'done'
    await vi.advanceTimersByTimeAsync(MD_POLL_INTERVAL_MS)
    await nextTick()
    expect(root.querySelectorAll('.row-parse[data-s="md-pending"]').length).toBe(0)
    expect(root.textContent).toContain('已转 Markdown')
    const count = methodCalls('GET', '/api/files/2').length
    await vi.advanceTimersByTimeAsync(MD_POLL_INTERVAL_MS * 3)
    expect(methodCalls('GET', '/api/files/2')).toHaveLength(count)
  })

  it('视图卸载后停止全部轮询', async () => {
    await mountView()
    await vi.advanceTimersByTimeAsync(MD_POLL_INTERVAL_MS)
    expect(methodCalls('GET', '/api/files/2')).toHaveLength(1)
    const count = calls.length
    app?.unmount()
    app = null
    await vi.advanceTimersByTimeAsync(MD_POLL_INTERVAL_MS * 3)
    expect(calls).toHaveLength(count)
  })
})
