// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import MemorySettings from './MemorySettings.vue'
import { useMemoriesStore } from '../../stores/memories'
import type { MemoryItem } from '../../api/memories'

function jsonResponse(payload: unknown, status = 200): Response {
  const text = payload === undefined ? '' : JSON.stringify(payload)
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => text,
    json: async () => (text ? JSON.parse(text) : undefined),
  } as unknown as Response
}

const FIXTURE: MemoryItem[] = [
  { id: 1, kind: 'preference', content: '用户偏好喝美式咖啡', keywords: '咖啡', source: 'ai',
    source_conversation_id: null, created_at: '2026-09-20T08:00:00', updated_at: '2026-09-21T09:30:00' },
  { id: 2, kind: 'preference', content: '回复要简短', keywords: '', source: 'user',
    source_conversation_id: null, created_at: '2026-09-20T08:00:00', updated_at: '2026-09-22T10:00:00' },
  { id: 3, kind: 'fact', content: '用户在上海读研', keywords: '', source: 'ai',
    source_conversation_id: null, created_at: '2026-09-19T08:00:00', updated_at: '2026-09-19T08:00:00' },
]

interface Recorded { url: string; method: string; body: unknown }
let writes: Recorded[]

function stubBackend(): void {
  writes = []
  vi.stubGlobal('fetch', vi.fn(async (input: unknown, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    const body = init?.body ? JSON.parse(String(init.body)) : null
    if (method !== 'GET') writes.push({ url, method, body })
    if (url.includes('/api/memories/enabled')) {
      if (method === 'PUT') return jsonResponse({ enabled: body.enabled })
      return jsonResponse({ enabled: true })
    }
    if (method === 'POST') return jsonResponse({ ...FIXTURE[0], id: 9, content: body.content, source: 'user' }, 201)
    if (method === 'DELETE') return jsonResponse({ ok: true })
    return jsonResponse(FIXTURE)
  }))
}

const flush = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0))

async function mountComponent(): Promise<HTMLElement> {
  const { createApp } = await import('vue')
  const host = document.createElement('div')
  document.body.innerHTML = ''
  document.body.appendChild(host)
  createApp(MemorySettings).use(createPinia()).mount(host)
  await flush()
  await flush()
  return host
}

function button(root: HTMLElement, label: string): HTMLButtonElement {
  const found = Array.from(root.querySelectorAll('button')).find((b) => b.textContent?.trim() === label)
  if (!found) throw new Error(`找不到按钮：${label}`)
  return found
}

describe('MemorySettings 组件（jsdom）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    stubBackend()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('按 kind 分组渲染：内容/来源徽标/更新时间，同组同区', async () => {
    const root = await mountComponent()
    expect(root.querySelector('#settings-memory')).not.toBeNull()
    expect(root.textContent).toContain('用户偏好喝美式咖啡')
    expect(root.textContent).toContain('AI 记下')
    expect(root.textContent).toContain('手动添加')
    expect(root.textContent).toContain('更新于 2026-09-21')
    // 分组标题出现且「偏好」组在「事实」组前
    const titles = Array.from(root.querySelectorAll('.group-title')).map((el) => el.textContent)
    expect(titles.findIndex((t) => t?.includes('偏好'))).toBeLessThan(titles.findIndex((t) => t?.includes('事实')))
  })

  it('开关：点击发 PUT 并翻转；关闭后出现后果说明文案', async () => {
    const root = await mountComponent()
    const store = useMemoriesStore()
    const sw = root.querySelector<HTMLButtonElement>('#memory-enabled-switch')
    expect(sw?.getAttribute('aria-checked')).toBe('true')
    sw!.click()
    await flush()
    await nextTick()
    expect(writes).toEqual([{ url: expect.stringContaining('/api/memories/enabled'), method: 'PUT', body: { enabled: false } }])
    expect(store.enabled).toBe(false)
    expect(sw!.getAttribute('aria-checked')).toBe('false')
    expect(root.textContent).toContain('不再读取或写入任何记忆')
  })

  it('手动添加：填表提交 POST source 走后端，新条目立即出现', async () => {
    const root = await mountComponent()
    button(root, '手动添加').click()
    await nextTick()
    const content = root.querySelector<HTMLTextAreaElement>('#memory-add-content')!
    content.value = '用户不吃香菜'
    content.dispatchEvent(new Event('input'))
    await nextTick()
    button(root, '添加').click()
    await flush()
    await nextTick()
    expect(writes).toEqual([expect.objectContaining({ method: 'POST', body: { kind: 'fact', content: '用户不吃香菜', keywords: '' } })])
    expect(root.textContent).toContain('用户不吃香菜')
  })

  it('删除两段确认：第一次变「确认删除？」，再次点击才发 DELETE', async () => {
    const root = await mountComponent()
    button(root, '删除').click()
    await nextTick()
    expect(writes).toEqual([])
    expect(root.textContent).toContain('确认删除？')
    button(root, '确认删除？').click()
    await flush()
    await nextTick()
    expect(writes).toEqual([expect.objectContaining({ method: 'DELETE' })])
    expect(document.body.textContent).not.toContain('用户偏好喝美式咖啡')
  })

  it('空列表：显示留白引导而非报错', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse([])))
    const root = await mountComponent()
    expect(root.textContent).toContain('还没有记忆')
    expect(root.textContent).toContain('手动添加')
  })
})
