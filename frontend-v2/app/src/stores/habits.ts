/**
 * 习惯 store：习惯卡 + 今日打卡 + 连续天数 + 近 14 天打卡带（/habits 视图）。
 *
 * - 打卡/撤销走 API：check-in 后端返回当日累计 count；撤销 uncheck 显式带 date
 *   （后 date 可省略=今天，这里仍显式传以明确语义）。两者都乐观更新
 *   status（done_today/today_count/streak）+ 失败回滚。
 * - logs 按习惯懒加载（进入视图后逐卡拉取近 14 天），纯函数 logsToCountMap 供打卡带渲染。
 * - refreshAll 供 run done 自动刷新（AI 工具 check_in_habit 等）。
 */
import { defineStore } from 'pinia'
import type { Habit, HabitLog } from '../api/habits'
import { checkIn, createHabit, deleteHabit, listHabits, listHabitLogs, normalizeHabit, uncheckHabit } from '../api/habits'
import { addDays, toIsoDate } from '../utils/date'

/**
 * logs → {date: count} 映射（打卡带渲染直接查表）。
 */
export function logsToCountMap(logs: HabitLog[]): Record<string, number> {
  const map: Record<string, number> = {}
  for (const l of logs) map[l.date] = l.count
  return map
}

/** 近 N 天（含今天）的 ISO 日期序列，升序。 */
export function recentDays(todayIso: string, days: number): string[] {
  return Array.from({ length: days }, (_, i) => addDays(todayIso, i - (days - 1)))
}

export const useHabitsStore = defineStore('habits', {
  state: () => ({
    items: null as Habit[] | null,
    loading: false,
    /** 打卡/撤销进行中的习惯 id（视图禁用按钮） */
    pendingIds: [] as number[],
    /** 各习惯近 14 天打卡带（habitId → {date: count}） */
    logsByHabit: {} as Record<number, Record<string, number>>,
    error: null as string | null,
    actionError: null as string | null,
    lastRefreshedAt: null as number | null,
  }),

  actions: {
    async load(): Promise<void> {
      this.loading = true
      this.error = null
      try {
        this.items = await listHabits()
        this.lastRefreshedAt = Date.now()
      } catch (e) {
        this.error = e instanceof Error ? e.message : '习惯加载失败'
      } finally {
        this.loading = false
      }
    },

    /** 拉取某习惯近 14 天打卡记录（幂等，可重复刷新）。 */
    async loadLogs(habitId: number): Promise<void> {
      try {
        const logs = await listHabitLogs(habitId, 14)
        this.logsByHabit = { ...this.logsByHabit, [habitId]: logsToCountMap(logs) }
      } catch {
        // 打卡带是增强信息，失败不打断卡片主体；留空即视为「无记录」
      }
    },

    /** run done 后由壳层调用：只刷已加载过的数据（logs 已拉过的习惯一并刷新）。 */
    async refreshAll(): Promise<void> {
      if (this.items === null) return
      await this.load()
      const withLogs = Object.keys(this.logsByHabit).map(Number)
      await Promise.all(withLogs.map((id) => this.loadLogs(id)))
    },

    async create(input: Parameters<typeof createHabit>[0]): Promise<Habit | null> {
      this.actionError = null
      try {
        // 创建响应可能缺少 status，补充初始状态以满足视图要求。
        const habit = normalizeHabit(await createHabit(input))
        this.items = [...(this.items ?? []), habit]
        return habit
      } catch (e) {
        this.actionError = e instanceof Error ? e.message : '习惯创建失败'
        return null
      }
    },

    async remove(habitId: number): Promise<boolean> {
      const items = this.items
      const idx = items?.findIndex((h) => h.id === habitId) ?? -1
      if (!items || idx < 0) return true
      const removed = items.splice(idx, 1)[0]
      const { [habitId]: _removedLogs, ...restLogs } = this.logsByHabit
      this.logsByHabit = restLogs
      this.actionError = null
      try {
        await deleteHabit(habitId)
        return true
      } catch (e) {
        items.splice(idx, 0, removed)
        this.logsByHabit = { ...this.logsByHabit, [habitId]: _removedLogs }
        this.actionError = e instanceof Error ? e.message : '习惯删除失败'
        return false
      }
    },

    /**
     * 今日打卡：乐观 status.done_today=true / today_count+1；后端 count 为准回填；
     * 失败回滚并落 actionError。
     */
    async checkInToday(habitId: number): Promise<boolean> {
      const habit = this.items?.find((h) => h.id === habitId)
      if (!habit || habit.status.done_today) return true
      const prevToday = habit.status.today_count
      habit.status.done_today = true
      habit.status.today_count = prevToday + 1
      habit.status.streak = habit.status.streak + 1
      this.pendingIds.push(habitId)
      this.actionError = null
      try {
        await checkIn(habitId)
        const todayIso = toIsoDate(new Date())
        const logs = this.logsByHabit[habitId]
        if (logs) this.logsByHabit = { ...this.logsByHabit, [habitId]: { ...logs, [todayIso]: (logs[todayIso] ?? 0) + 1 } }
        return true
      } catch (e) {
        habit.status.done_today = false // 回滚
        habit.status.today_count = prevToday
        habit.status.streak = Math.max(0, habit.status.streak - 1)
        this.actionError = e instanceof Error ? `「${habit.name}」打卡未保存：${e.message}` : '打卡失败'
        return false
      } finally {
        this.pendingIds = this.pendingIds.filter((id) => id !== habitId)
      }
    },

    /** 撤销今日打卡：显式带 date（后可省略，这里显式传）。乐观回退 + 失败回滚。 */
    async uncheckToday(habitId: number): Promise<boolean> {
      const habit = this.items?.find((h) => h.id === habitId)
      if (!habit || !habit.status.done_today) return true
      const todayIso = toIsoDate(new Date())
      const prevToday = habit.status.today_count
      const prevStreak = habit.status.streak
      habit.status.done_today = false
      habit.status.today_count = Math.max(0, prevToday - 1)
      habit.status.streak = Math.max(0, prevStreak - 1)
      this.pendingIds.push(habitId)
      this.actionError = null
      try {
        await uncheckHabit(habitId, todayIso)
        const logs = this.logsByHabit[habitId]
        if (logs && logs[todayIso]) {
          const next = { ...logs, [todayIso]: logs[todayIso] - 1 }
          if (next[todayIso] <= 0) delete next[todayIso]
          this.logsByHabit = { ...this.logsByHabit, [habitId]: next }
        }
        return true
      } catch (e) {
        habit.status.done_today = true // 回滚
        habit.status.today_count = prevToday
        habit.status.streak = prevStreak
        this.actionError = e instanceof Error ? `「${habit.name}」撤销未保存：${e.message}` : '撤销失败'
        return false
      } finally {
        this.pendingIds = this.pendingIds.filter((id) => id !== habitId)
      }
    },
  },
})
