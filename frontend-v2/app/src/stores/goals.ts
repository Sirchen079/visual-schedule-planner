/** 目标及关键结果状态。进度由内嵌 key_results 计算，编辑时乐观更新并在失败时回滚。 */
import { defineStore } from 'pinia'
import type { Goal, KeyResult } from '../api/goals'
import { createGoal, createKeyResult, deleteGoal, deleteKeyResult, listGoals, updateGoal, updateKeyResult } from '../api/goals'

/** KR 进度百分比（0–100，钳制；target<=0 时返回 0 防除零）。 */
export function krPercent(kr: Pick<KeyResult, 'current_value' | 'target_value'>): number {
  const target = Number(kr.target_value)
  if (!Number.isFinite(target) || target <= 0) return 0
  const pct = (Number(kr.current_value) / target) * 100
  if (!Number.isFinite(pct)) return 0
  return Math.min(100, Math.max(0, Math.round(pct)))
}

/** 目标整体进度 = KR 进度的算术平均（无 KR 时 null，视图显示「未设关键结果」）。 */
export function goalPercent(goal: Goal): number | null {
  const krs = goal.key_results ?? []
  if (krs.length === 0) return null
  return Math.round(krs.reduce((sum, kr) => sum + krPercent(kr), 0) / krs.length)
}

export const GOAL_STATUS_LABELS: Record<string, string> = {
  active: '进行中',
  paused: '暂停',
  done: '已达成',
  archived: '已归档',
}

export const useGoalsStore = defineStore('goals', {
  state: () => ({
    items: null as Goal[] | null,
    loading: false,
    /** 进行中的 KR 更新（krId 集合），视图据此禁用输入 */
    pendingKrs: [] as number[],
    error: null as string | null,
    actionError: null as string | null,
    lastRefreshedAt: null as number | null,
  }),

  actions: {
    async load(): Promise<void> {
      this.loading = true
      this.error = null
      try {
        this.items = await listGoals()
        this.lastRefreshedAt = Date.now()
      } catch (e) {
        this.error = e instanceof Error ? e.message : '目标加载失败'
      } finally {
        this.loading = false
      }
    },

    /** run done 后由壳层调用：只刷已加载过的数据。 */
    async refreshAll(): Promise<void> {
      if (this.items === null) return
      await this.load()
    },

    async create(input: Parameters<typeof createGoal>[0]): Promise<Goal | null> {
      this.actionError = null
      try {
        const goal = await createGoal(input)
        this.items = [...(this.items ?? []), goal]
        return goal
      } catch (e) {
        this.actionError = e instanceof Error ? e.message : '目标创建失败'
        return null
      }
    },

    async remove(goalId: number): Promise<boolean> {
      const items = this.items
      const idx = items?.findIndex((g) => g.id === goalId) ?? -1
      if (!items || idx < 0) return true
      const removed = items.splice(idx, 1)[0]
      this.actionError = null
      try {
        await deleteGoal(goalId)
        return true
      } catch (e) {
        items.splice(idx, 0, removed)
        this.actionError = e instanceof Error ? e.message : '目标删除失败'
        return false
      }
    },

    /** 归档（软移出默认列表；include_archived 时仍可见）。 */
    async archive(goalId: number): Promise<boolean> {
      this.actionError = null
      try {
        await updateGoal(goalId, { status: 'archived' })
        this.items = (this.items ?? []).filter((g) => g.id !== goalId)
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? e.message : '归档失败'
        return false
      }
    },

    async addKeyResult(goalId: number, input: Parameters<typeof createKeyResult>[1]): Promise<KeyResult | null> {
      this.actionError = null
      try {
        const kr = await createKeyResult(goalId, input)
        const goal = this.items?.find((g) => g.id === goalId)
        if (goal) goal.key_results = [...goal.key_results, kr]
        return kr
      } catch (e) {
        this.actionError = e instanceof Error ? e.message : '关键结果添加失败'
        return null
      }
    },

    /** KR 进度更新：乐观更新本地 current_value，PATCH 失败回滚。 */
    async updateKrProgress(krId: number, currentValue: number): Promise<boolean> {
      const goal = this.items?.find((g) => g.key_results.some((k) => k.id === krId))
      const kr = goal?.key_results.find((k) => k.id === krId)
      if (!kr) return true
      const prev = kr.current_value
      kr.current_value = currentValue
      this.pendingKrs.push(krId)
      this.actionError = null
      try {
        const updated = await updateKeyResult(krId, { current_value: currentValue })
        Object.assign(kr, updated)
        return true
      } catch (e) {
        kr.current_value = prev // 回滚
        this.actionError = e instanceof Error ? `「${kr.title}」进度未保存：${e.message}` : '进度保存失败'
        return false
      } finally {
        this.pendingKrs = this.pendingKrs.filter((id) => id !== krId)
      }
    },

    async removeKeyResult(krId: number): Promise<boolean> {
      const goal = this.items?.find((g) => g.key_results.some((k) => k.id === krId))
      if (!goal) return true
      const idx = goal.key_results.findIndex((k) => k.id === krId)
      const removed = goal.key_results.splice(idx, 1)[0]
      this.actionError = null
      try {
        await deleteKeyResult(krId)
        return true
      } catch (e) {
        goal.key_results.splice(idx, 0, removed)
        this.actionError = e instanceof Error ? e.message : '关键结果删除失败'
        return false
      }
    },
  },
})
