import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import {
  ghostFromApproval,
  groupOccurrencesByDate,
  projectGhosts,
  useScheduleStore,
  weekSummary,
} from './schedule'
import type { EventOccurrence } from '../api/schedule'
import { addDays, toIsoDate } from '../utils/date'

/** http.ts 走全局 fetch（同源相对路径），node 测试环境下用 stub 模拟后端响应。 */
function jsonResponse(payload: unknown, status = 200): Response {
  const text = JSON.stringify(payload)
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => text,
    json: async () => JSON.parse(text),
  } as unknown as Response
}

/** 按一周日期排列的合成课程样本。 */
const WEEK: EventOccurrence[] = [
  { event_id: 1, title: '示例课程B', date: '2026-09-07', start_time: '08:55', end_time: '10:45', location: '示例教室C', category: 'course' },
  { event_id: 13, title: '示例课程C', date: '2026-09-07', start_time: '16:00', end_time: '17:40', location: '示例教室D', category: 'course' },
  { event_id: 3, title: '示例课程A', date: '2026-09-08', start_time: '08:55', end_time: '10:45', location: '示例教室A', category: 'course' },
  { event_id: 9, title: '示例课程C', date: '2026-09-09', start_time: '14:00', end_time: '15:40', location: '待定', category: 'course' },
  { event_id: 5, title: '示例课程A', date: '2026-09-10', start_time: '08:55', end_time: '10:45', location: '示例教室A', category: 'course' },
]

describe('schedule 纯函数', () => {
  it('groupOccurrencesByDate：按日分组且日内按开始时间排序', () => {
    const grouped = groupOccurrencesByDate([...WEEK].reverse())
    expect(Object.keys(grouped).sort()).toEqual(['2026-09-07', '2026-09-08', '2026-09-09', '2026-09-10'])
    expect(grouped['2026-09-07'].map((o) => o.start_time)).toEqual(['08:55', '16:00'])
  })

  it('weekSummary：开学周 5 节课、4 天有课', () => {
    const dates = ['2026-09-07', '2026-09-08', '2026-09-09', '2026-09-10', '2026-09-11', '2026-09-12', '2026-09-13']
    expect(weekSummary(dates, groupOccurrencesByDate(WEEK))).toEqual({ count: 5, days: 4 })
  })

  it('ghostFromApproval：仅 schedule.create_event 且字段齐全才产出幽灵块', () => {
    expect(
      ghostFromApproval({
        tool: 'schedule.create_event',
        args: { title: '羽毛球', date: '2026-09-11', start_time: '14:00', end_time: '16:00', location: '体育馆' },
      }),
    ).toEqual({ date: '2026-09-11', title: '羽毛球', start: '14:00', end: '16:00', location: '体育馆' })
    // 工具参数使用 day，工具名为 create_event。
    // 历史录制另有 api__ 前缀形态 —— 一律按 /create_event$/ 后缀识别
    expect(
      ghostFromApproval({
        tool: 'create_event',
        args: { title: '晨跑', day: '2026-09-05', start_time: '09:00', end_time: '10:00' },
      }),
    ).toEqual({ date: '2026-09-05', title: '晨跑', start: '09:00', end: '10:00', location: null })
    expect(
      ghostFromApproval({
        tool: 'api__schedule__create_event',
        args: { title: 'x', day: '2026-09-05', start_time: '09:00', end_time: '10:00' },
      }),
    ).not.toBeNull()
    expect(
      ghostFromApproval({
        tool: 'schedule.create_event_not',
        args: { title: 'x', day: '2026-09-05', start_time: '09:00', end_time: '10:00' },
      }),
    ).toBeNull()
    // date 优先于 day（两者都有时不误判）
    expect(
      ghostFromApproval({
        tool: 'schedule.create_event',
        args: { day: '2026-09-05', date: '2026-09-06', start: '08:00', end: '09:00' },
      })?.date,
    ).toBe('2026-09-06')
    expect(ghostFromApproval({ tool: 'tasks.create', args: { title: 'x', date: '2026-09-11', start_time: '1', end_time: '2' } })).toBeNull()
    expect(ghostFromApproval({ tool: 'schedule.create_event', args: { title: '缺时间' } })).toBeNull()
    expect(ghostFromApproval(null)).toBeNull()
  })
})

describe('projectGhosts（审批账目 → 幽灵块投影，支持多个并存）', () => {
  const entry = (actionId: number, overrides: Record<string, unknown> = {}) => ({
    actionId,
    tool: 'schedule.create_event',
    outcome: null,
    args: { title: `事项${actionId}`, date: '2026-09-11', start_time: '14:00', end_time: '15:00', ...overrides },
  })

  it('多个待决事件并存投影；按日期+开始时间排序；图章「待批准」', () => {
    const ghosts = projectGhosts(
      [
        entry(2, { date: '2026-09-12', start_time: '09:00', end_time: '10:00' }),
        entry(1, { title: '羽毛球', start_time: '14:00', end_time: '16:00' }),
      ],
      {},
      null,
    )
    expect(ghosts).toHaveLength(2)
    expect(ghosts.map((g) => g.actionId)).toEqual([1, 2]) // 09-11 在 09-12 前
    expect(ghosts[0].stamp).toBe('待批准')
    expect(ghosts[0].outcome).toBeNull()
  })

  it('拒绝/过期的审批不再投影', () => {
    const ghosts = projectGhosts(
      [entry(1), { ...entry(2), outcome: 'denied' as const }, { ...entry(3, { start_time: '16:00', end_time: '17:00' }), outcome: 'expired' as const }],
      {},
      null,
    )
    expect(ghosts).toHaveLength(1)
    expect(ghosts[0].actionId).toBe(1)
  })

  it('已批准但数据未实体化 → 仍投影，图章「已批准」；同日同时刻实体出现后自动隐去', () => {
    const approved = { ...entry(1), outcome: 'approved' as const }
    const before = projectGhosts([approved], {}, null)
    expect(before).toHaveLength(1)
    expect(before[0].stamp).toBe('已批准')

    // expand 数据到了：同 date+start_time+end_time 的实体块出现 → 幽灵块转实体、虚线块隐去
    const byDate = groupOccurrencesByDate([
      { event_id: 99, title: '事项1', date: '2026-09-11', start_time: '14:00', end_time: '15:00', location: '体育馆', category: 'general' },
    ])
    expect(projectGhosts([approved], byDate, null)).toHaveLength(0)
  })

  it('visibleDates 限定可见范围；非 create_event 审批不投影', () => {
    const ghosts = projectGhosts(
      [entry(1), entry(2, { date: '2026-09-20', start_time: '10:00', end_time: '11:00' }), { ...entry(3), tool: 'tasks.create' }],
      {},
      ['2026-09-11'],
    )
    expect(ghosts).toHaveLength(1)
    expect(ghosts[0].actionId).toBe(1)
    expect(projectGhosts(null, {}, null)).toEqual([])
  })
})

describe('schedule store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string | URL | Request) => {
        const u = String(url)
        if (u.startsWith('/api/schedule/events/expand')) {
          // 模拟后端 expand 的区间语义：返回 [start, end] 内的展开条目
          const sp = new URLSearchParams(u.split('?')[1] ?? '')
          const start = sp.get('start') ?? ''
          const end = sp.get('end') ?? ''
          return jsonResponse(WEEK.filter((o) => o.date >= start && o.date <= end))
        }
        if (u.startsWith('/api/schedule/conflicts')) {
          return jsonResponse([]) // 缺省：窗口内无冲突日
        }
        if (u.startsWith('/api/schedule/free-slots')) {
          return jsonResponse([]) // 缺省：无 ≥30 分钟整段空闲
        }
        if (u.startsWith('/api/schedule/day')) {
          return jsonResponse({
            date: '2026-09-07',
            items: [
              { kind: 'event', event_id: 1, title: '示例课程B', date: '2026-09-07', start_time: '08:55', end_time: '10:45', location: '示例教室C', category: 'course' },
            ],
          })
        }
        return jsonResponse({ detail: 'unexpected ' + u }, 404)
      }),
    )
  })

  it('loadWeek 拉取并排序展开结果；getter 分组/统计可用', async () => {
    const s = useScheduleStore()
    await s.loadWeek('2026-09-07')
    expect(s.weekAnchor).toBe('2026-09-07')
    expect(String(vi.mocked(globalThis.fetch).mock.calls[0][0])).toContain('start=2026-09-07&end=2026-09-13')
    expect(s.occurrences).toHaveLength(5)
    expect(s.weekDates).toHaveLength(7)
    expect(s.weekDates[0]).toBe('2026-09-07')
    expect(s.byDate['2026-09-07']).toHaveLength(2)
    expect(s.weekSummary).toEqual({ count: 5, days: 4 })
    expect(s.lastRefreshedAt).not.toBeNull()
    expect(s.error).toBeNull()
  })

  it('loadToday 拉当日视图；refreshAll 同时刷新今日与当前周', async () => {
    const s = useScheduleStore()
    await s.loadWeek('2026-09-07')
    await s.loadToday()
    expect(s.todayDate).toBe('2026-09-07')
    expect(s.today).toHaveLength(1)
    // 换成另一周再 refreshAll：仍应拉当前锚点周（而非跳回本周）
    const fetchMock = vi.mocked(globalThis.fetch)
    await s.loadWeek('2026-09-14')
    await s.refreshAll()
    const expandCalls = fetchMock.mock.calls.map((c) => String(c[0])).filter((u) => u.includes('expand'))
    expect(expandCalls[expandCalls.length - 1]).toContain('start=2026-09-14')
    expect(s.loading).toBe(false)
  })

  it('shiftWeek：0 回本周、±1 平移一周', async () => {
    const s = useScheduleStore()
    await s.loadWeek('2026-09-07')
    await s.shiftWeek(1)
    expect(s.weekAnchor).toBe('2026-09-14')
    await s.shiftWeek(-1)
    expect(s.weekAnchor).toBe('2026-09-07')
    await s.shiftWeek(0)
    // 使用实际时钟，仅验证换周完成且状态正常。
    expect(s.weekAnchor).not.toBe('')
    expect(s.error).toBeNull()
  })

  it('loadSingleDay / shiftDay：expand 取单日（start=end），日条目排序', async () => {
    const s = useScheduleStore()
    await s.loadSingleDay('2026-09-07')
    const calls = vi.mocked(globalThis.fetch).mock.calls.map((c) => String(c[0]))
    expect(calls[calls.length - 1]).toContain('start=2026-09-07&end=2026-09-07')
    expect(s.dayDate).toBe('2026-09-07')
    expect(s.dayItems.map((o) => o.start_time)).toEqual(['08:55', '16:00'])
    // 平移一天
    await s.shiftDay(1)
    expect(s.dayDate).toBe('2026-09-08')
    await s.shiftDay(-1)
    expect(s.dayDate).toBe('2026-09-07')
    expect(s.error).toBeNull()
    expect(s.loading).toBe(false)
  })

  it('锚点先行落位：loadSingleDay/loadMonth 未等响应就更新锚点（防视图挂载守卫竞态重复拉取）', () => {
    const s = useScheduleStore()
    const dayPromise = s.loadSingleDay('2026-09-07')
    expect(s.dayDate).toBe('2026-09-07') // 同步可见，PaperDayView 挂载守卫据此跳过默认加载
    const monthPromise = s.loadMonth('2026-09-15')
    expect(s.monthAnchor).toBe('2026-09-15')
    return Promise.all([dayPromise, monthPromise])
  })

  it('loadMonth / shiftMonth：expand 覆盖 6 周网格首末；月网格分组可用', async () => {
    const s = useScheduleStore()
    await s.loadMonth('2026-09-15')
    const calls = vi.mocked(globalThis.fetch).mock.calls.map((c) => String(c[0]))
    expect(calls[calls.length - 1]).toContain('start=2026-08-31&end=2026-10-11')
    expect(s.monthAnchor).toBe('2026-09-15')
    expect(s.monthByDate['2026-09-07']).toHaveLength(2)
    // 平移一个月：锚点落在目标月 1 号
    await s.shiftMonth(-1)
    expect(s.monthAnchor).toBe('2026-08-01')
    await s.shiftMonth(1)
    await s.shiftMonth(1)
    expect(s.monthAnchor).toBe('2026-10-01')
    expect(s.error).toBeNull()
  })

  it('refreshAll：已加载过日/月视图时一并刷新（done 后幽灵块实体化的数据来源）', async () => {
    const s = useScheduleStore()
    await s.loadWeek('2026-09-07')
    await s.loadSingleDay('2026-09-07')
    await s.loadMonth('2026-09-15')
    const fetchMock = vi.mocked(globalThis.fetch)
    fetchMock.mockClear()
    await s.refreshAll()
    const urls = fetchMock.mock.calls.map((c) => String(c[0]))
    expect(urls.some((u) => u.includes('expand?start=2026-09-07&end=2026-09-13'))).toBe(true) // 周
    expect(urls.some((u) => u.includes('expand?start=2026-09-07&end=2026-09-07'))).toBe(true) // 日
    expect(urls.some((u) => u.includes('expand?start=2026-08-31&end=2026-10-11'))).toBe(true) // 月
  })

  it('接口失败：error 落消息，loading 复位', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ detail: '后端炸了' }, 500)),
    )
    const s = useScheduleStore()
    await s.loadWeek('2026-09-07')
    expect(s.error).toContain('后端炸了')
    expect(s.loadingWeek).toBe(false)
  })
})

describe('conflicts / freeSlots（冲突与空闲展示）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('loadConflicts：今日冲突项进 todayConflicts，7 日窗内未来冲突日进 upcomingConflictDays', async () => {
    const today = toIsoDate(new Date())
    const tomorrow = addDays(today, 1)
    const urls: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string | URL | Request) => {
        const u = String(url)
        urls.push(u)
        if (u.startsWith('/api/schedule/conflicts')) {
          return jsonResponse([
            {
              date: tomorrow,
              items: [{ task_id: 7, title: '写综述', date: tomorrow, start_time: '09:00', end_time: '11:00', estimated_minutes: 120 }],
            },
            { date: addDays(today, 3), items: [] }, // 无冲突日 items 为空（接口逐日聚合）
            {
              date: today,
              items: [
                { event_id: 1, title: '示例课程A', date: today, start_time: '08:55', end_time: '10:45', location: '示例教室A' },
                { task_id: 9, title: '组会汇报', date: today, start_time: '09:30', end_time: '11:00' },
              ],
            },
          ])
        }
        return jsonResponse({ detail: 'unexpected ' + u }, 404)
      }),
    )
    const s = useScheduleStore()
    await s.loadConflicts()
    expect(urls[0]).toContain(`start=${today}&end=${addDays(today, 6)}`) // 今日起 7 日窗
    expect(s.conflicts).toHaveLength(3)
    expect(s.todayConflicts.map((i) => i.title)).toEqual(['示例课程A', '组会汇报'])
    expect(s.upcomingConflictDays.map((d) => d.date)).toEqual([tomorrow]) // 空 items 日被过滤
    expect(s.conflictsError).toBeNull()
    expect(s.loadingConflicts).toBe(false)
  })

  it('loadConflicts 失败：conflictsError 落消息（与今日视图 error 互不串扰），loading 复位', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ detail: '冲突接口炸了' }, 500)),
    )
    const s = useScheduleStore()
    await s.loadConflicts()
    expect(s.conflictsError).toContain('冲突接口炸了')
    expect(s.loadingConflicts).toBe(false)
    expect(s.conflicts).toBeNull()
    expect(s.error).toBeNull()
  })

  it('loadFreeSlots：空档段落定（工作时段内整段空闲）；URL 带 date 与 min_minutes=30', async () => {
    const today = toIsoDate(new Date())
    const urls: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string | URL | Request) => {
        const u = String(url)
        urls.push(u)
        if (u.startsWith('/api/schedule/free-slots')) {
          // 探针实形：空闲日返回工作时段内的整段空档（如 09:00–18:00 · 540 分钟）
          return jsonResponse([
            { start: '09:00', end: '12:00', minutes: 180 },
            { start: '14:00', end: '15:30', minutes: 90 },
          ])
        }
        return jsonResponse({ detail: 'unexpected ' + u }, 404)
      }),
    )
    const s = useScheduleStore()
    await s.loadFreeSlots()
    expect(
      urls.some((u) => u.startsWith('/api/schedule/free-slots') && u.includes(`date=${today}`) && u.includes('min_minutes=30')),
    ).toBe(true)
    expect(s.freeSlots).toEqual([
      { start: '09:00', end: '12:00', minutes: 180 },
      { start: '14:00', end: '15:30', minutes: 90 },
    ])
    expect(s.freeSlotsError).toBeNull()
    expect(s.loadingFreeSlots).toBe(false)
  })

  it('loadFreeSlots 空数组：freeSlots 落为 []（空态可判定），而非 null', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse([])))
    const s = useScheduleStore()
    await s.loadFreeSlots()
    expect(s.freeSlots).toEqual([])
    expect(s.freeSlotsError).toBeNull()
  })

  it('loadToday 连带刷新冲突与空闲；refreshAll 亦随之更新（run done 后警示带不滞后）', async () => {
    const today = toIsoDate(new Date())
    const urls: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string | URL | Request) => {
        const u = String(url)
        urls.push(u)
        if (u.startsWith('/api/schedule/conflicts')) {
          return jsonResponse([
            {
              date: today,
              items: [
                { event_id: 1, title: '冲突A', date: today, start_time: '09:00', end_time: '10:00' },
                { task_id: 2, title: '冲突B', date: today, start_time: '09:00', end_time: '10:00' },
              ],
            },
          ])
        }
        if (u.startsWith('/api/schedule/free-slots')) {
          return jsonResponse([{ start: '13:00', end: '14:00', minutes: 60 }])
        }
        if (u.startsWith('/api/schedule/day')) {
          return jsonResponse({ date: today, items: [] })
        }
        if (u.startsWith('/api/schedule/events/expand')) {
          return jsonResponse([])
        }
        return jsonResponse({ detail: 'unexpected ' + u }, 404)
      }),
    )
    const s = useScheduleStore()
    await s.loadToday()
    expect(s.todayConflicts).toHaveLength(2)
    expect(s.freeSlots).toEqual([{ start: '13:00', end: '14:00', minutes: 60 }])
    urls.length = 0
    await s.refreshAll()
    expect(urls.some((u) => u.startsWith('/api/schedule/conflicts'))).toBe(true)
    expect(urls.some((u) => u.startsWith('/api/schedule/free-slots'))).toBe(true)
    expect(s.loading).toBe(false)
  })
})

describe('projectGhosts 重复规则文案（审批 args 带 recur_rrule 时给出 repeat 行）', () => {
  it('args 带 recur_rrule → repeatText 经 repeatRuleText 生成（rrule 回退路径）', () => {
    const ghosts = projectGhosts(
      [
        {
          actionId: 9,
          tool: 'schedule.create_event',
          outcome: null,
          args: {
            title: '晚自习',
            day: '2026-09-08',
            start_time: '18:00',
            end_time: '20:00',
            recur_rrule: 'FREQ=WEEKLY;INTERVAL=2;BYDAY=TU',
          },
        },
      ],
      {},
      null,
    )
    expect(ghosts).toHaveLength(1)
    expect(ghosts[0].repeatText).toBe('隔周的周二（单双周轮换）')
  })

  it('args 无 recur_rrule → repeatText 为 null（不渲染 repeat 行）', () => {
    const ghosts = projectGhosts(
      [
        {
          actionId: 10,
          tool: 'create_event',
          outcome: null,
          args: { title: '晨跑', day: '2026-09-05', start_time: '09:00', end_time: '10:00' },
        },
      ],
      {},
      null,
    )
    expect(ghosts[0].repeatText).toBeNull()
  })
})
