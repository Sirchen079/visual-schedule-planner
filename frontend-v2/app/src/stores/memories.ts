/**
 * 长期记忆 store：列表/开关 + 手动增改删。
 * - 设置页挂载时 load() 一次：列表与开关并行拉取；失败落 error，可重试。
 * - 增/改/删成功后就地更新 items（不整表重拉闪烁）；操作失败落 actionError（与列表 error 分开）。
 * - 开关默认开：后端「缺失视为开」，加载完成前 enabled 为 null（UI 显示加载态而非误判关闭）。
 */
import { defineStore } from 'pinia'
import {
  createMemory,
  deleteMemory,
  getMemoryEnabled,
  listMemories,
  setMemoryEnabled,
  updateMemory,
  type MemoryCreateBody,
  type MemoryItem,
  type MemoryUpdateBody,
} from '../api/memories'

interface MemoriesState {
  items: MemoryItem[] | null
  /** null = 尚未加载完成（后端默认开，不预设 false） */
  enabled: boolean | null
  loading: boolean
  error: string | null
  /** 增改删等操作级错误（与列表加载 error 分开，语义不互染） */
  actionError: string | null
  /** 正在写入的条目 id（行内按钮转圈/防重复提交）；开关保存用 savingEnabled */
  busyIds: number[]
  adding: boolean
  savingEnabled: boolean
}

export const useMemoriesStore = defineStore('memories', {
  state: (): MemoriesState => ({
    items: null,
    enabled: null,
    loading: false,
    error: null,
    actionError: null,
    busyIds: [],
    adding: false,
    savingEnabled: false,
  }),

  getters: {
    /** 按 kind 分组（保持 kind 固定顺序，空组不出现），供设置页分区渲染 */
    groupedByKind(state): { kind: string; items: MemoryItem[] }[] {
      const order = ['profile', 'preference', 'decision', 'fact', 'project']
      const map = new Map<string, MemoryItem[]>()
      for (const item of state.items ?? []) {
        const list = map.get(item.kind) ?? []
        list.push(item)
        map.set(item.kind, list)
      }
      return order.filter((kind) => map.has(kind)).map((kind) => ({ kind, items: map.get(kind)! }))
    },
  },

  actions: {
    /** 拉列表 + 开关（并行）；失败落 error 可重试。 */
    async load(): Promise<void> {
      this.loading = true
      this.error = null
      try {
        const [items, flag] = await Promise.all([listMemories(), getMemoryEnabled()])
        this.items = items
        this.enabled = flag.enabled
      } catch (e) {
        this.error = e instanceof Error ? e.message : '记忆加载失败'
      } finally {
        this.loading = false
      }
    },

    /** 手动新增（source='user' 由后端落定）；成功后就地插入列表头部。 */
    async add(body: MemoryCreateBody): Promise<boolean> {
      if (this.adding) return false
      this.adding = true
      this.actionError = null
      try {
        const item = await createMemory(body)
        this.items = [item, ...(this.items ?? [])]
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? e.message : '记忆保存失败'
        return false
      } finally {
        this.adding = false
      }
    },

    /** 行内编辑：PATCH 只发改过的字段，成功后就地替换该条。 */
    async edit(id: number, body: MemoryUpdateBody): Promise<boolean> {
      if (this.busyIds.includes(id)) return false
      this.busyIds = [...this.busyIds, id]
      this.actionError = null
      try {
        const updated = await updateMemory(id, body)
        this.items = (this.items ?? []).map((item) => (item.id === id ? updated : item))
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? e.message : '记忆更新失败'
        return false
      } finally {
        this.busyIds = this.busyIds.filter((x) => x !== id)
      }
    },

    /** 删除：成功后就地移除。 */
    async remove(id: number): Promise<boolean> {
      if (this.busyIds.includes(id)) return false
      this.busyIds = [...this.busyIds, id]
      this.actionError = null
      try {
        await deleteMemory(id)
        this.items = (this.items ?? []).filter((item) => item.id !== id)
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? e.message : '记忆删除失败'
        return false
      } finally {
        this.busyIds = this.busyIds.filter((x) => x !== id)
      }
    },

    /** 开关：关闭后 AI 记忆工具与注入全部消失（说明文案在设置页）。 */
    async toggle(enabled: boolean): Promise<boolean> {
      if (this.savingEnabled) return false
      this.savingEnabled = true
      this.actionError = null
      try {
        const flag = await setMemoryEnabled(enabled)
        this.enabled = flag.enabled
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? e.message : '开关保存失败'
        return false
      } finally {
        this.savingEnabled = false
      }
    },
  },
})
