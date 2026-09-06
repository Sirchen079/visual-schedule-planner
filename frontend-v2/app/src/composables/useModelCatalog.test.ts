import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import { useModelCatalog } from './useModelCatalog'

afterEach(() => vi.unstubAllGlobals())
function setup() {
  const scope = effectScope(), url = ref('https://models.example/v1'), key = ref('temporary-test-key'), protocol = ref('openai_responses')
  const catalog = scope.run(() => useModelCatalog(url, key, protocol))!
  return { scope, url, key, protocol, catalog }
}
describe('model list discovery', () => {
  it('reuses a saved key via config_id and discards results when the config getter changes', async () => {
    const scope = effectScope(), id = ref<number | null>(7)
    const catalog = scope.run(() => useModelCatalog(ref('https://models.example/v1'), ref(''), ref('openai_compat'), () => id.value))!
    let finish!: (response: Response) => void
    const fetch = vi.fn((_url: unknown, _opts?: RequestInit) => new Promise<Response>(resolve => { finish = resolve }))
    vi.stubGlobal('fetch', fetch)
    const pending = catalog.discover()
    expect(JSON.parse(String(fetch.mock.calls[0]?.[1]?.body))).toEqual({ base_url: 'https://models.example/v1', api_key: '', provider_kind: 'openai_compat', config_id: 7 })
    id.value = 8
    expect(fetch.mock.calls[0]?.[1]?.signal?.aborted).toBe(true)
    finish(new Response(JSON.stringify({ models: [{ id: 'stale', name: 'stale' }], truncated: false })))
    await pending
    expect(catalog.models.value).toEqual([]); expect(catalog.loaded.value).toBe(false)
    scope.stop()
  })
  it('accepts a config Ref and omits config_id for a new configuration', async () => {
    const scope = effectScope(), id = ref<number | null>(7)
    const catalog = scope.run(() => useModelCatalog(ref('https://models.example/v1'), ref(''), ref('anthropic'), id))!
    const fetch = vi.fn(async (_url: unknown, _opts?: RequestInit) => new Response(JSON.stringify({ models: [], truncated: false })))
    vi.stubGlobal('fetch', fetch)
    await catalog.discover(); expect(JSON.parse(String(fetch.mock.calls[0]?.[1]?.body)).config_id).toBe(7)
    id.value = null; expect(catalog.loaded.value).toBe(false)
    await catalog.discover(); expect(JSON.parse(String(fetch.mock.calls[1]?.[1]?.body))).not.toHaveProperty('config_id')
    scope.stop()
  })
  it('posts entered credentials without saving a configuration', async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ models: [{id:'m',name:'Model'}],truncated:false }), {status:200}))
    vi.stubGlobal('fetch',fetch)
    const t=setup(); await t.catalog.discover()
    expect(fetch.mock.calls).toHaveLength(1)
    const [url, opts] = (fetch.mock.calls as unknown[][])[0]!
    expect(url).toBe('/ai/configs/models')
    expect(JSON.parse((opts as RequestInit).body as string).api_key).toBe('temporary-test-key')
    expect(t.catalog.models.value[0]?.id).toBe('m');expect(t.key.value).toBe('temporary-test-key')
    t.scope.stop()
  })
  it('discards results if the address or credentials changed during a request', async () => {
    let finish!: (response: Response) => void
    vi.stubGlobal('fetch',vi.fn(() => new Promise<Response>(resolve => {finish=resolve})))
    const t=setup(), pending=t.catalog.discover()
    t.url.value='https://new.example/v1'
    finish(new Response(JSON.stringify({models:[{id:'stale',name:'stale'}],truncated:false}),{status:200}))
    await pending
    expect(t.catalog.models.value).toEqual([]);expect(t.catalog.loading.value).toBe(false)
    t.scope.stop()
  })
  it('keeps form fields on failure and exposes an empty successful list', async () => {
    vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify({detail:'认证失败'}),{status:400})))
    const t=setup();await t.catalog.discover()
    expect(t.catalog.error.value).toBe('认证失败');expect(t.key.value).toBe('temporary-test-key')
    vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify({models:[],truncated:false}),{status:200})))
    await t.catalog.discover();expect(t.catalog.loaded.value).toBe(true);expect(t.catalog.error.value).toBe('')
    t.scope.stop()
  })
})
