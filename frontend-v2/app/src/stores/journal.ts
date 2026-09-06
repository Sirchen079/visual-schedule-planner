/**
 * 日记 store：当日编辑器 + 历史列表（/journal 视图）。
 *
 * - 保存走 PUT upsert（幂等）：本地先落 pending 态，成功后同步列表与当前条目；
 *   失败不沉默（actionError 行内展示）。
 * - refreshAll 供 run done 自动刷新（AI 工具 write_journal 落库在 done 前）。
 */
import { defineStore } from 'pinia'
import type { JournalEntry } from '../api/journal'
import { deleteJournalDay, getJournalDay, listJournal, upsertJournalDay } from '../api/journal'
import { toIsoDate } from '../utils/date'

export const MOOD_PRESETS: Array<{ key: string; label: string }> = [
  { key: 'calm', label: '平静' },
  { key: 'focused', label: '专注' },
  { key: 'happy', label: '愉快' },
  { key: 'tired', label: '疲惫' },
  { key: 'anxious', label: '焦虑' },
]

export function moodLabel(mood: string | null | undefined): string {
  if (!mood) return ''
  return MOOD_PRESETS.find((m) => m.key === mood)?.label ?? mood
}

export const useJournalStore = defineStore('journal', {
  state: () => ({
    /** 历史列表（按日期倒序，实测） */
    entries: null as JournalEntry[] | null,
    loading: false,
    /** 当前编辑中的日期（ISO）与该日条目 */
    activeDay: '' as string,
    activeEntry: null as JournalEntry | null,
    loadingDay: false,
    saving: false,
    error: null as string | null,
    actionError: null as string | null,
    lastRefreshedAt: null as number | null,
  }),

  actions: {
    async load(): Promise<void> {
      this.loading = true
      this.error = null
      try {
        this.entries = await listJournal()
        this.lastRefreshedAt = Date.now()
      } catch (e) {
        this.error = e instanceof Error ? e.message : '日记列表加载失败'
      } finally {
        this.loading = false
      }
    },

    /** 选中某日（编辑器载入该日条目；无条目 = 空白可写）。 */
    async openDay(day?: string): Promise<void> {
      const d = day ?? (this.activeDay || toIsoDate(new Date()))
      this.activeDay = d
      this.loadingDay = true
      this.actionError = null
      const blank: JournalEntry = { id: 0, date: d, content: '', mood: null, created_at: '', updated_at: '' }
      try {
        // 契约与实测：当日无条目 → 200 + null（旧注释「空形状条目」已过时）——落空白可写条目
        this.activeEntry = (await getJournalDay(d)) ?? blank
      } catch (e) {
        // 请求失败同样给空白可写条目而非报错卡死编辑器
        this.activeEntry = blank
        if (e instanceof Error) this.actionError = `当日日记读取失败：${e.message}`
      } finally {
        this.loadingDay = false
      }
    },

    /** 保存（upsert）。成功后同步历史列表（无则头部插入，有则原位更新）。 */
    async save(day: string, content: string, mood: string | null): Promise<boolean> {
      this.saving = true
      this.actionError = null
      try {
        const entry = await upsertJournalDay(day, { content, mood })
        this.activeEntry = entry
        const list = this.entries ?? []
        const idx = list.findIndex((e) => e.date === day)
        if (idx >= 0) list.splice(idx, 1, entry)
        else list.unshift(entry)
        this.entries = [...list]
        this.lastRefreshedAt = Date.now()
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? e.message : '日记保存失败'
        return false
      } finally {
        this.saving = false
      }
    },

    async remove(day: string): Promise<boolean> {
      this.actionError = null
      try {
        await deleteJournalDay(day)
        this.entries = (this.entries ?? []).filter((e) => e.date !== day)
        if (this.activeDay === day) this.activeEntry = null
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? e.message : '日记删除失败'
        return false
      }
    },

    /** run done 后由壳层调用：只刷已加载过的数据。 */
    async refreshAll(): Promise<void> {
      if (this.entries === null && !this.activeDay) return
      const tasks: Promise<void>[] = []
      if (this.entries !== null) tasks.push(this.load())
      if (this.activeDay) tasks.push(this.openDay(this.activeDay))
      await Promise.all(tasks)
    },
  },
})
