// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import OcrSettings from './OcrSettings.vue'
import type { OcrConfig } from '../../api/settings'

function jsonResponse(payload: unknown, status = 200): Response {
  const text = payload === undefined ? '' : JSON.stringify(payload)
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => text,
    json: async () => (text ? JSON.parse(text) : undefined),
  } as unknown as Response
}

interface Recorded { url: string; method: string; body: Record<string, unknown> }
let writes: Recorded[]
/** PUT /api/settings/ocr 的回包 has_api_key（默认保存后即已配置） */
let putHasApiKey: boolean

function stubBackend(getPayload: OcrConfig): void {
  writes = []
  vi.stubGlobal('fetch', vi.fn(async (input: unknown, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null
    if (method !== 'GET') writes.push({ url, method, body: body ?? {} })
    if (url.includes('/api/settings/ocr')) {
      if (method === 'PUT') {
        const { api_key, ...rest } = body ?? {}
        return jsonResponse({ ...rest, has_api_key: putHasApiKey || api_key !== undefined })
      }
      return jsonResponse(getPayload)
    }
    return jsonResponse({ detail: 'unexpected' }, 404)
  }))
}

const CONFIGURED: OcrConfig = {
  base_url: 'https://api.siliconflow.cn/v1',
  model: 'deepseek-ai/DeepSeek-OCR',
  has_api_key: true,
}

const flush = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0))

async function mountComponent(): Promise<HTMLElement> {
  const { createApp } = await import('vue')
  const host = document.createElement('div')
  document.body.innerHTML = ''
  document.body.appendChild(host)
  createApp(OcrSettings).mount(host)
  await flush()
  await flush()
  return host
}

function input(root: HTMLElement, id: string): HTMLInputElement {
  const found = root.querySelector<HTMLInputElement>(`#${id}`)
  if (!found) throw new Error(`找不到输入框：${id}`)
  return found
}

function setInput(el: HTMLInputElement, value: string): void {
  el.value = value
  el.dispatchEvent(new Event('input'))
}

function button(root: HTMLElement, label: string): HTMLButtonElement {
  const found = Array.from(root.querySelectorAll('button')).find((b) => b.textContent?.trim() === label)
  if (!found) throw new Error(`找不到按钮：${label}`)
  return found
}

describe('OcrSettings 组件（jsdom）：key 保留语义', () => {
  beforeEach(() => {
    putHasApiKey = true
    stubBackend({ ...CONFIGURED })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('加载回填 base_url/model，key 永不回填，已配置时显示「已保存」', async () => {
    const root = await mountComponent()
    expect(root.querySelector('#settings-ocr')).not.toBeNull()
    expect(input(root, 'ocr-base-url').value).toBe('https://api.siliconflow.cn/v1')
    expect(input(root, 'ocr-model').value).toBe('deepseek-ai/DeepSeek-OCR')
    const key = input(root, 'ocr-api-key')
    expect(key.value).toBe('')
    expect(key.getAttribute('type')).toBe('password')
    expect(key.getAttribute('placeholder')).toBe('留空则保留已保存的密钥')
    expect(root.textContent).toContain('已保存')
    expect(writes).toHaveLength(0)
  })

  it('key 留空保存：PUT 不带 api_key 字段（后端保留现有密钥），回包回填 base_url/model', async () => {
    const root = await mountComponent()
    const baseUrl = input(root, 'ocr-base-url')
    setInput(baseUrl, 'https://api.siliconflow.cn/v1 ')
    setInput(input(root, 'ocr-model'), 'deepseek-ai/DeepSeek-OCR')
    expect(input(root, 'ocr-api-key').value).toBe('')
    button(root, '保存').click()
    await flush()
    await nextTick()
    expect(writes).toEqual([{
      url: expect.stringContaining('/api/settings/ocr'),
      method: 'PUT',
      // 留空 = 不发 api_key 字段（undefined 被 JSON 序列化丢弃）
      body: { base_url: 'https://api.siliconflow.cn/v1', model: 'deepseek-ai/DeepSeek-OCR' },
    }])
    expect(Object.prototype.hasOwnProperty.call(writes[0].body, 'api_key')).toBe(false)
    expect(root.textContent).toContain('扫描件 OCR 设置已保存')
    expect(input(root, 'ocr-api-key').value).toBe('')
  })

  it('key 填写保存：PUT 带新 api_key，保存后输入框清空', async () => {
    const root = await mountComponent()
    setInput(input(root, 'ocr-api-key'), '  sk-new-key  ')
    button(root, '保存').click()
    await flush()
    await nextTick()
    expect(writes).toEqual([{
      url: expect.stringContaining('/api/settings/ocr'),
      method: 'PUT',
      body: { base_url: 'https://api.siliconflow.cn/v1', model: 'deepseek-ai/DeepSeek-OCR', api_key: 'sk-new-key' },
    }])
    expect(input(root, 'ocr-api-key').value).toBe('')
  })

  it('未配置（has_api_key=false）：徽标「未配置」、占位提示，保存后仍未配置给出引导文案', async () => {
    stubBackend({ base_url: '', model: '', has_api_key: false })
    putHasApiKey = false
    const root = await mountComponent()
    expect(root.textContent).toContain('未配置')
    expect(input(root, 'ocr-api-key').getAttribute('placeholder')).toBe('sk-…')
    setInput(input(root, 'ocr-base-url'), 'https://api.siliconflow.cn/v1')
    setInput(input(root, 'ocr-model'), 'deepseek-ai/DeepSeek-OCR')
    button(root, '保存').click()
    await flush()
    await nextTick()
    expect(root.textContent).toContain('尚未配置 API Key，扫描页暂时无法识别')
  })

  it('加载失败：DomainState 错误态 + 重试', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: '读取失败' }, 500)))
    const root = await mountComponent()
    expect(root.textContent).toContain('读取失败')
    expect(root.querySelector('#ocr-save')).toBeNull()
  })
})
