import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { effectScope, type Ref } from 'vue'
import SettingsView from './SettingsView.vue'
import { useSettingsStore } from '../stores/settings'
import type { AiConfigInfo } from '../api/settings'

vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }) }))
vi.mock('vue', async importOriginal => ({
  ...await importOriginal<typeof import('vue')>(),
  useSSRContext: () => ({ modules: new Set<string>() }),
}))

interface Form {
  configFormOpen: Ref<boolean>; configName: Ref<string>; configModel: Ref<string>
  configBaseUrl: Ref<string>; configApiKey: Ref<string>; configProtocol: Ref<string>
  configContextWindow: Ref<string | number>; configMaxOutputTokens: Ref<string | number>
  configReasoningEffort: Ref<string>; configInputModalities: Ref<string[]>; configFormError: Ref<string | null>; catalogError: Ref<string>
  openConfigCreate(): void; openConfigEdit(c: AiConfigInfo): void; closeConfigForm(): void
  submitConfigForm(): Promise<void>; discoverModels(): Promise<void>
}
const scopes: ReturnType<typeof effectScope>[] = []
function form(): Form {
  const scope = effectScope(); scopes.push(scope)
  // Exercise the actual SFC setup and its store requests without a browser environment.
  return scope.run(() => (SettingsView as unknown as { setup: (props: object, context: object) => Form }).setup({}, { expose: () => {} }))!
}
const existing: AiConfigInfo = {
  id: 7, name: '研究模型', model: 'unclassified-model', provider_kind: 'openai_compat',
  base_url: 'https://models.example/v1', enabled: true, has_api_key: true,
  context_window: 128000, max_output_tokens: 8192, input_modalities: ['text', 'image'],
  request_limit: 42, price_input: 2.5, price_output: 8,
}
beforeEach(() => {
  setActivePinia(createPinia())
  vi.stubGlobal('document', { getElementById: () => null })
  // Lifecycle registration is intentionally outside a mounted renderer in this setup-level test.
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})
afterEach(() => { scopes.splice(0).forEach(scope => scope.stop()); vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('AI model settings form', () => {
  it('loads, changes and clears thinking effort while retaining rejected drafts', async () => {
    const save = vi.spyOn(useSettingsStore(), 'saveConfig').mockResolvedValue(false)
    const f = form(); f.openConfigEdit({ ...existing, reasoning_effort: 'high' })
    expect(f.configReasoningEffort.value).toBe('high')
    f.configReasoningEffort.value = 'low'; await f.submitConfigForm()
    expect(save).toHaveBeenLastCalledWith(7, expect.objectContaining({ reasoning_effort: 'low' }))
    expect(f.configReasoningEffort.value).toBe('low'); expect(f.configFormOpen.value).toBe(true)
    f.configReasoningEffort.value = ''; await f.submitConfigForm()
    expect(save).toHaveBeenLastCalledWith(7, expect.objectContaining({ reasoning_effort: null }))
  })
  it('requires a compatible effort after changing to Anthropic without discarding the draft', async () => {
    const save = vi.spyOn(useSettingsStore(), 'saveConfig').mockResolvedValue(true)
    const f = form(); f.openConfigEdit({ ...existing, reasoning_effort: 'minimal' })
    f.configProtocol.value = 'anthropic'; await f.submitConfigForm()
    expect(save).not.toHaveBeenCalled(); expect(f.configFormError.value).toContain('思考程度')
    expect(f.configReasoningEffort.value).toBe('minimal')
    f.configReasoningEffort.value = 'high'; await f.submitConfigForm()
    expect(save).toHaveBeenCalledWith(7, expect.objectContaining({ provider_kind: 'anthropic', reasoning_effort: 'high' }))
  })
  it('creates text-only with null token limits without inferring from the model name', async () => {
    const s = useSettingsStore(), save = vi.spyOn(s, 'addConfig').mockResolvedValue(true)
    const f = form(); f.openConfigCreate(); f.configName.value = '新模型'; f.configModel.value = 'vision-audio-video-pro'
    await f.submitConfigForm()
    expect(save).toHaveBeenCalledWith({ name: '新模型', model: 'vision-audio-video-pro', provider_kind: 'openai_compat', base_url: null, api_key: null, context_window: null, max_output_tokens: null, input_modalities: ['text'], reasoning_effort: null })
    expect(f.configFormOpen.value).toBe(false)
  })
  it('edits all capabilities and preserves existing prices / request limit without echoing a secret', async () => {
    const s = useSettingsStore(), save = vi.spyOn(s, 'saveConfig').mockResolvedValue(true)
    const f = form(); f.openConfigEdit(existing)
    expect(f.configApiKey.value).toBe('')
    expect(f.configContextWindow.value).toBe(128000)
    f.configContextWindow.value = ''; f.configMaxOutputTokens.value = ''; f.configInputModalities.value = ['text', 'audio', 'video']
    await f.submitConfigForm()
    expect(save).toHaveBeenCalledWith(7, {
      name: existing.name, model: existing.model, provider_kind: existing.provider_kind, base_url: existing.base_url,
      api_key: null, context_window: null, max_output_tokens: null, input_modalities: ['text', 'audio', 'video'], reasoning_effort: null,
      price_input: 2.5, price_output: 8, request_limit: 42,
    })
    expect(existing.input_modalities).toEqual(['text', 'image'])
  })
  it.each([
    [1023, '', '上下文窗口'], [10000001, '', '上下文窗口'], [1024.5, '', '上下文窗口'],
    ['', 0, '最大输出'], ['', 1000001, '最大输出'], ['', 1.5, '最大输出'],
    [1024, 1024, '须小于'], [1024, 1025, '须小于'],
  ])('rejects invalid limits context=%s / output=%s', async (context, output, error) => {
    const save = vi.spyOn(useSettingsStore(), 'saveConfig')
    const f = form(); f.openConfigEdit(existing); f.configContextWindow.value = context; f.configMaxOutputTokens.value = output
    await f.submitConfigForm(); expect(save).not.toHaveBeenCalled(); expect(f.configFormError.value).toContain(error)
  })
  it('requires text input and retains all draft fields on a failed save', async () => {
    const save = vi.spyOn(useSettingsStore(), 'saveConfig').mockResolvedValue(false)
    const f = form(); f.openConfigEdit(existing); f.configInputModalities.value = []
    await f.submitConfigForm(); expect(save).not.toHaveBeenCalled(); expect(f.configFormError.value).toContain('必须保留文本')
    f.configInputModalities.value = ['image', 'audio', 'video']
    await f.submitConfigForm(); expect(save).not.toHaveBeenCalled(); expect(f.configFormError.value).toContain('必须保留文本')
    f.configInputModalities.value = ['text']; f.configApiKey.value = 'replacement-key'
    await f.submitConfigForm(); expect(f.configFormOpen.value).toBe(true); expect(f.configApiKey.value).toBe('replacement-key')
    expect(save.mock.calls[0]?.[1].api_key).toBe('replacement-key')
    f.closeConfigForm(); f.openConfigCreate()
    expect(f.configApiKey.value).toBe(''); expect(f.configInputModalities.value).toEqual(['text']); expect(f.configContextWindow.value).toBe('')
  })
  it('uses conservative legacy defaults and accepts exact valid bounds', async () => {
    const save = vi.spyOn(useSettingsStore(), 'saveConfig').mockResolvedValue(true)
    const f = form(); f.openConfigEdit({ id: 1, name: 'old', model: 'vision', provider_kind: 'openai_compat', enabled: false })
    expect(f.configInputModalities.value).toEqual(['text']); expect(f.configContextWindow.value).toBe(''); expect(f.configMaxOutputTokens.value).toBe('')
    f.configContextWindow.value = 10000000; f.configMaxOutputTokens.value = 1000000
    await f.submitConfigForm(); expect(save).toHaveBeenCalled()
  })
  it('blocks saved-key discovery after URL or provider change, permits an explicit key', async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ models: [], truncated: false })))
    vi.stubGlobal('fetch', fetch)
    const f = form(); f.openConfigEdit(existing); f.configBaseUrl.value = 'https://different.example/v1'
    await f.discoverModels(); expect(fetch).not.toHaveBeenCalled(); expect(f.catalogError.value).toContain('请填写')
    f.configBaseUrl.value = existing.base_url!; f.configProtocol.value = 'anthropic'
    await f.discoverModels(); expect(fetch).not.toHaveBeenCalled()
    f.configApiKey.value = 'explicit-key'; await f.discoverModels(); expect(fetch).toHaveBeenCalledOnce()
  })
})
