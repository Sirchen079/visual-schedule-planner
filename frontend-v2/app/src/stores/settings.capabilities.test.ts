import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useSettingsStore } from './settings'

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => vi.unstubAllGlobals())
describe('AI config editing requests', () => {
  it('PUTs the full body and reloads authoritative rows without changing enablement', async () => {
    const store = useSettingsStore()
    const body = { name: '更新配置', model: 'm', api_key: null, context_window: 32000, max_output_tokens: 4000, input_modalities: ['text' as const], request_limit: 42, price_input: 2, price_output: 3 }
    const row = { ...body, api_key: undefined, id: 7, enabled: true, provider_kind: 'openai_compat', has_api_key: true }
    const fetch = vi.fn(async (_url: unknown, init?: RequestInit) => {
      if (init?.method === 'PUT') { expect(store.savingConfig).toBe(true); return new Response(JSON.stringify(row)) }
      return new Response(JSON.stringify([row]))
    })
    vi.stubGlobal('fetch', fetch)
    expect(await store.saveConfig(7, body)).toBe(true)
    expect(fetch.mock.calls[0]?.[0]).toBe('/ai/configs/7')
    expect(JSON.parse(String(fetch.mock.calls[0]?.[1]?.body))).toEqual(body)
    expect(fetch.mock.calls[1]?.[0]).toBe('/ai/configs')
    expect(store.configs?.[0]?.enabled).toBe(true); expect(store.configs?.[0]?.has_api_key).toBe(true)
    expect(store.savingConfig).toBe(false)
  })
  it('leaves rows unchanged after rejected edit and exposes the error', async () => {
    const store = useSettingsStore()
    store.configs = [{ id: 7, name: 'original', model: 'm', provider_kind: 'anthropic', enabled: true }]
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: '最大输出须小于上下文窗口' }), { status: 422 })))
    expect(await store.saveConfig(7, { name: 'changed', model: 'm' })).toBe(false)
    expect(store.configs[0]?.name).toBe('original'); expect(store.actionError).toContain('保存失败'); expect(store.savingConfig).toBe(false)
  })
})
