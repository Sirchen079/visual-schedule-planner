/**
 * 日程 store：今日视图（/api/schedule/day）+ 周视图 / 日视图 / 月视图（/api/schedule/events/expand）
 * + 冲突检测（/api/schedule/conflicts）与今日空闲（/api/schedule/free-slots）。
 *
 * - 后端负责 RRULE 展开（含单双周），前端只按日期分组渲染；月视图与日视图同样走 expand
 *   （/api/schedule/month 实测只含任务负载 task_count，不含 events —— 契约漂移已记录）。
 * - refreshAll 供「run done 后自动刷新」调用：AI 写操作落库后，各视图无需手动
 *   刷新即可看到新日程（App.vue 监听 run.phase → completed 即调用）。
 * - 冲突/空闲是今日页的伴生数据：由 loadToday 连带刷新（今日页是默认落地页，
 *   refreshAll → loadToday 即覆盖，run done 后冲突警示带/空闲条随之更新）。
 * - 分组/统计/审批幽灵块映射抽成纯函数导出，便于单测。
 */
import { defineStore } from 'pinia'
import type { ConflictDay, ConflictItem, DayItem, EventOccurrence, FreeSlot } from '../api/schedule'
import { expandEvents, getConflicts, getDayView, getFreeSlots } from '../api/schedule'
import { repeatRuleText } from '../utils/recurrence'
import { addDays, addMonths, firstOfMonth, mondayOf, monthGridBounds, toIsoDate, weekDates } from '../utils/date'

/** 审批幽灵块（与对话内审批卡互为镜像，语言见 final-calendar.html .ghost）。 */
export interface GhostBlock {
  date: string
  title: string
  start: string
  end: string
  location: string | null
}

/** 投影到纸面上的幽灵块：带审批状态与图章文案。 */
export interface GhostProject extends GhostBlock {
  actionId: number
  outcome: 'approved' | 'denied' | 'expired' | null
  /** 待批准（未决）/ 已批准（等待落库实体化） */
  stamp: string
  /** 重复规则文案（审批 args 带 recur_rrule 时经 repeatRuleText 生成；无则 null 不显示） */
  repeatText: string | null
}

/** 审批账目条目的结构形状（与 run store 的 PendingApproval 结构兼容，避免跨 store 类型耦合）。 */
export interface LedgerEntryLike {
  actionId: number
  tool: string
  args: Record<string, unknown>
  outcome: 'approved' | 'denied' | 'expired' | null
}

export function groupOccurrencesByDate(list: EventOccurrence[]): Record<string, EventOccurrence[]> {
  const by: Record<string, EventOccurrence[]> = {}
  for (const o of list) {
    ;(by[o.date] ??= []).push(o)
  }
  for (const k of Object.keys(by)) by[k].sort((a, b) => (a.start_time ?? '').localeCompare(b.start_time ?? ''))
  return by
}

export interface WeekSummary {
  /** 本周展开后的日程条数 */
  count: number
  /** 有日程的天数（0–7） */
  days: number
}

export function weekSummary(dates: string[], grouped: Record<string, EventOccurrence[]>): WeekSummary {
  let count = 0
  let days = 0
  for (const d of dates) {
    const n = grouped[d]?.length ?? 0
    count += n
    if (n > 0) days += 1
  }
  return { count, days }
}

/**
 * 审批待决的 create_event → 幽灵块。args 键以后端工具实测为准（d0f5474，2026-09-05）：
 * - 工具名实测为裸名 create_event（历史录制里也出现过 api__schedule__create_event 形态，
 *   M2 写死的 'schedule.create_event' 等值匹配在真实流上永不命中 —— 幽灵块只在注入探针下
 *   显示过，属 M2 遗留缺陷，本次以 /create_event$/ 后缀匹配修复）；
 * - 日期参数是 day（REST 的 POST /api/schedule/events 才叫 date）；
 * - 时间参数兼容 start/end 别名。工具不符或缺关键字段时返回 null。
 */
export function ghostFromApproval(a: { tool: string; args: Record<string, unknown> } | null): GhostBlock | null {
  if (!a || !/create_event$/.test(String(a.tool))) return null
  const args = a.args
  const str = (v: unknown): string | null => (typeof v === 'string' && v.trim() ? v.trim() : null)
  const date = str(args['date']) ?? str(args['day'])
  const start = str(args['start_time']) ?? str(args['start'])
  const end = str(args['end_time']) ?? str(args['end'])
  if (!date || !start || !end) return null
  return {
    date,
    title: str(args['title']) ?? '新日程',
    start,
    end,
    location: str(args['location']),
  }
}

/**
 * 幽灵块投影：把审批账目（本 run 内请求过的全部 create_event 审批）画到纸面上。
 *
 * - 拒绝/过期 → 立即从纸面消失；
 * - 已批准但后端数据尚未刷新到前端（run 未到 done / refresh 未完成）→ 仍以虚线块存在，
 *   图章「已批准」，直到 expand 数据里出现同日同时刻的实体条目才算「转实体块」（自动隐去）；
 * - 待批准 → 图章「待批准」；多个待决/落地中事件可同时在纸面上并存投影。
 * - visibleDates 限定可见范围（当前周/当日/月网格）；传 null 表示不限。
 */
export function projectGhosts(
  ledger: LedgerEntryLike[] | null | undefined,
  byDate: Record<string, EventOccurrence[]>,
  visibleDates: string[] | null,
): GhostProject[] {
  const out: GhostProject[] = []
  for (const a of ledger ?? []) {
    if (a.outcome === 'denied' || a.outcome === 'expired') continue
    const g = ghostFromApproval(a)
    if (!g) continue
    if (visibleDates && !visibleDates.includes(g.date)) continue
    const materialized = (byDate[g.date] ?? []).some((o) => o.start_time === g.start && o.end_time === g.end)
    if (materialized) continue
    // 幽灵块的重复规则文案：审批 args 里的 recur_rrule → repeatRuleText（repeat_note
    // 优先、rrule 回退；args 无 repeat_note，AI create_event 不写该列——rrule 缺省则不显示）
    const rrule = typeof a.args['recur_rrule'] === 'string' ? (a.args['recur_rrule'] as string) : null
    out.push({
      ...g,
      actionId: a.actionId,
      outcome: a.outcome,
      stamp: a.outcome === 'approved' ? '已批准' : '待批准',
      repeatText: rrule ? repeatRuleText(null, rrule) : null,
    })
  }
  return out.sort((x, y) => x.date.localeCompare(y.date) || x.start.localeCompare(y.start))
}

export const useScheduleStore = defineStore('schedule', {
  state: () => ({
    /** 今日视图条目（/api/schedule/day） */
    today: null as DayItem[] | null,
    todayDate: '' as string,
    /** 周视图：当前锚点（周一 ISO）与该周展开出的日程 */
    weekAnchor: '' as string,
    occurrences: [] as EventOccurrence[],
    /** 日视图：聚焦的单日（ISO）与该日展开出的日程（expand，start=end=当日） */
    dayDate: '' as string,
    dayOccurrences: [] as EventOccurrence[],
    /** 月视图：锚点（当月 1 号 ISO）与 6 周网格展开出的日程 */
    monthAnchor: '' as string,
    monthOccurrences: [] as EventOccurrence[],
    /** 冲突检测（今日起 7 日窗，每天一条含无冲突日；null=尚未加载） */
    conflicts: null as ConflictDay[] | null,
    loadingConflicts: false,
    conflictsError: null as string | null,
    /** 今日空闲时段（工作时段内 ≥30 分钟整段空档；null=尚未加载） */
    freeSlots: null as FreeSlot[] | null,
    loadingFreeSlots: false,
    freeSlotsError: null as string | null,
    loadingToday: false,
    loadingWeek: false,
    loadingDayView: false,
    loadingMonth: false,
    error: null as string | null,
    /** 最近一次成功刷新的时间戳（自动刷新的可见证据） */
    lastRefreshedAt: null as number | null,
  }),

  getters: {
    /** 当前加载周的 7 天（周一 → 周日） */
    weekDates(state): string[] {
      return state.weekAnchor ? weekDates(state.weekAnchor) : []
    },
    byDate(state): Record<string, EventOccurrence[]> {
      return groupOccurrencesByDate(state.occurrences)
    },
    weekSummary(): WeekSummary {
      return weekSummary(this.weekDates, this.byDate)
    },
    /** 日视图条目（日内按开始时间排序） */
    dayItems(state): EventOccurrence[] {
      return [...state.dayOccurrences].sort((a, b) => (a.start_time ?? '').localeCompare(b.start_time ?? ''))
    },
    /** 月视图按日分组（键为 6 周网格内的 ISO 日期） */
    monthByDate(state): Record<string, EventOccurrence[]> {
      return groupOccurrencesByDate(state.monthOccurrences)
    },
    /** 今日冲突项（今日页警示带数据源；conflicts 逐日聚合，取今日那条的 items）。 */
    todayConflicts(state): ConflictItem[] {
      const today = toIsoDate(new Date())
      return state.conflicts?.find((c) => c.date === today)?.items ?? []
    },
    /** 近 7 日窗内今日之后的冲突日（只含有 items 的，按日期升序）。 */
    upcomingConflictDays(state): ConflictDay[] {
      const today = toIsoDate(new Date())
      return (state.conflicts ?? [])
        .filter((c) => c.date > today && c.items.length > 0)
        .sort((a, b) => a.date.localeCompare(b.date))
    },
    loading(state): boolean {
      return (
        state.loadingToday ||
        state.loadingWeek ||
        state.loadingDayView ||
        state.loadingMonth ||
        state.loadingConflicts ||
        state.loadingFreeSlots
      )
    },
  },

  actions: {
    async loadToday(): Promise<void> {
      this.loadingToday = true
      this.error = null
      const date = toIsoDate(new Date())
      // 冲突/空闲与今日视图同源刷新：今日页是默认落地页，且 run done → refreshAll →
      // loadToday，AI 写操作落库后冲突警示带/空闲条随最新日程更新（不重复发第二遍）。
      const extras = Promise.all([this.loadConflicts(), this.loadFreeSlots()])
      try {
        const view = await getDayView(date)
        if (date !== toIsoDate(new Date())) return // 请求期间跨天：丢弃过期结果
        this.today = view.items
        this.todayDate = view.date
        this.lastRefreshedAt = Date.now()
      } catch (e) {
        this.error = e instanceof Error ? e.message : '今日日程加载失败'
      } finally {
        this.loadingToday = false
        await extras // 跨天早退路径也等到冲突/空闲落定，避免 loading 与断言竞态
      }
    },

    /** 冲突检测（今日起 7 日窗；今日页警示带 + 「近 7 日」展开区，逐日聚合、空 items 日自然过滤）。 */
    async loadConflicts(): Promise<void> {
      this.loadingConflicts = true
      this.conflictsError = null
      const start = toIsoDate(new Date())
      const end = addDays(start, 6)
      try {
        const days = await getConflicts(start, end)
        this.conflicts = [...days].sort((a, b) => a.date.localeCompare(b.date))
        this.lastRefreshedAt = Date.now()
      } catch (e) {
        this.conflictsError = e instanceof Error ? e.message : '冲突检测加载失败'
      } finally {
        this.loadingConflicts = false
      }
    },

    /** 今日空闲时段（工作时段内 ≥30 分钟整段空档；今日页「今日空闲」展示）。 */
    async loadFreeSlots(): Promise<void> {
      this.loadingFreeSlots = true
      this.freeSlotsError = null
      const date = toIsoDate(new Date())
      try {
        const slots = await getFreeSlots(date, 30)
        if (date !== toIsoDate(new Date())) return // 请求期间跨天：丢弃过期结果
        this.freeSlots = slots
        this.lastRefreshedAt = Date.now()
      } catch (e) {
        this.freeSlotsError = e instanceof Error ? e.message : '空闲时段加载失败'
      } finally {
        this.loadingFreeSlots = false
      }
    },

    /** 加载某一周（锚点为该周周一 ISO）；缺省 = 今天所在周。 */
    async loadWeek(anchor?: string): Promise<void> {
      this.loadingWeek = true
      this.error = null
      const monday = anchor ?? mondayOf(toIsoDate(new Date()))
      try {
        const list = await expandEvents(monday, weekDates(monday)[6])
        this.weekAnchor = monday
        this.occurrences = [...list].sort(
          (a, b) => a.date.localeCompare(b.date) || (a.start_time ?? '').localeCompare(b.start_time ?? ''),
        )
        this.lastRefreshedAt = Date.now()
      } catch (e) {
        this.error = e instanceof Error ? e.message : '周课表加载失败'
      } finally {
        this.loadingWeek = false
      }
    },

    /** run 到达 done（写操作落库）后由壳层调用：今日 + 已加载过的视图一次拉齐
     *  （已批准的幽灵块在数据到达后自动转实体块；loadToday 连带刷新冲突/空闲）。 */
    async refreshAll(): Promise<void> {
      const tasks: Promise<void>[] = [this.loadToday(), this.loadWeek(this.weekAnchor || undefined)]
      if (this.dayDate) tasks.push(this.loadSingleDay(this.dayDate))
      if (this.monthAnchor) tasks.push(this.loadMonth(this.monthAnchor))
      await Promise.all(tasks)
    },

    /** 本地换周（prev/next/本周）。换周即拉取。 */
    async shiftWeek(dir: 0 | -1 | 1): Promise<void> {
      const base = this.weekAnchor || mondayOf(toIsoDate(new Date()))
      await this.loadWeek(dir === 0 ? mondayOf(toIsoDate(new Date())) : addDays(base, dir * 7))
    },

    /** 加载单日（expand：start=end=date）；缺省 = 已聚焦日或今天。
     *  锚点先行落位：视图组件挂载守卫据此避免重复拉取，日标签即刻可见（等待不沉默）。 */
    async loadSingleDay(date?: string): Promise<void> {
      const d = date ?? (this.dayDate || toIsoDate(new Date()))
      this.dayDate = d
      this.loadingDayView = true
      this.error = null
      try {
        const list = await expandEvents(d, d)
        this.dayOccurrences = [...list].sort((a, b) => (a.start_time ?? '').localeCompare(b.start_time ?? ''))
        this.lastRefreshedAt = Date.now()
      } catch (e) {
        this.error = e instanceof Error ? e.message : '单日日程加载失败'
      } finally {
        this.loadingDayView = false
      }
    },

    /** 日视图平移（prev/next/今天）。 */
    async shiftDay(dir: 0 | -1 | 1): Promise<void> {
      const base = this.dayDate || toIsoDate(new Date())
      await this.loadSingleDay(dir === 0 ? toIsoDate(new Date()) : addDays(base, dir))
    },

    /** 加载月视图（expand 覆盖 6 周网格首末）；缺省 = 已锚定月或当月。锚点先行落位（同上）。 */
    async loadMonth(anchor?: string): Promise<void> {
      const first = anchor ?? (this.monthAnchor || firstOfMonth(toIsoDate(new Date())))
      this.monthAnchor = first
      this.loadingMonth = true
      this.error = null
      try {
        const { start, end } = monthGridBounds(first)
        const list = await expandEvents(start, end)
        this.monthOccurrences = [...list].sort(
          (a, b) => a.date.localeCompare(b.date) || (a.start_time ?? '').localeCompare(b.start_time ?? ''),
        )
        this.lastRefreshedAt = Date.now()
      } catch (e) {
        this.error = e instanceof Error ? e.message : '月历加载失败'
      } finally {
        this.loadingMonth = false
      }
    },

    /** 月视图平移（prev/next/本月）。 */
    async shiftMonth(dir: 0 | -1 | 1): Promise<void> {
      const base = this.monthAnchor || firstOfMonth(toIsoDate(new Date()))
      await this.loadMonth(dir === 0 ? firstOfMonth(toIsoDate(new Date())) : addMonths(base, dir))
    },
  },
})
