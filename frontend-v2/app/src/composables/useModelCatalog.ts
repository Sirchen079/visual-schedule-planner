import { onScopeDispose, ref, toValue, watch, type MaybeRefOrGetter, type Ref } from 'vue'
import { request } from '../api/http'
import type { components } from '../api/contracts/rest'

export type CatalogModel = components['schemas']['CatalogModel']
type CatalogResult = components['schemas']['ModelCatalogResponse']

export function useModelCatalog(baseUrl: Ref<string>, apiKey: Ref<string>, protocol: Ref<string>, configId?: MaybeRefOrGetter<number | null | undefined>) {
  const models = ref<CatalogModel[]>([]), loading = ref(false), error = ref(''), loaded = ref(false), truncated = ref(false)
  let controller: AbortController | null = null
  let revision = 0
  function clear() {
    revision++; controller?.abort(); controller = null
    models.value = []; loading.value = false; error.value = ''; loaded.value = false; truncated.value = false
  }
  watch([baseUrl, apiKey, protocol, () => toValue(configId)], clear, { flush: 'sync' })
  async function discover() {
    clear()
    if (!baseUrl.value.trim()) { error.value = '请先填写 Base URL。'; return }
    const current = revision
    controller = new AbortController()
    loading.value = true
    try {
      const id = toValue(configId)
      const result = await request<CatalogResult>('/ai/configs/models', { method: 'POST', signal: controller.signal,
        body: { base_url: baseUrl.value.trim(), api_key: apiKey.value, provider_kind: protocol.value,
          ...(id == null ? {} : { config_id: id }) } })
      if (current !== revision) return
      models.value = result.models; truncated.value = result.truncated ?? false; loaded.value = true
    } catch (e) {
      if (current === revision) error.value = e instanceof Error ? e.message : '模型列表获取失败，请重试或手动填写。'
    } finally { if (current === revision) loading.value = false }
  }
  onScopeDispose(clear)
  return { models, loading, error, loaded, truncated, discover, clear }
}
