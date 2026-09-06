import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { logsToCountMap, recentDays, useHabitsStore } from './habits'
import type { Habit } from '../api/habits'

function jsonResponse(payload: unknown, status = 200): Response {
  const text = JSON.stringify(payload)
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => text,
    json: async () => JSON.parse(text),
  } as unknown as Response
}

/** 真实形状（2026-09-05 于 d0f5474 GET /api/habits 实测，含内嵌 status）。 */
function makeHabit(partial: Partial<Habit>): Habit {
  return {
    id: 1,
    name: 'M3测试习惯',
    notes: '',
    period: 'daily',
    target_count: 1,
    color: '#e4a366',
    status: { today_count: 0, period_count: 0, streak: 0, done_today: false },
    ...partial,
  }
}

describe('habits 纯函数', () => {
  it('logsToCountMap：[{date,count}] → 查表', () => {
    expect(logsToCountMap([{ date: '2026-09-05', count: 2 }, { date: '2026-09-04', count: 1 }])).toEqual({
      '2026-09-05': 2,
      '2026-09-04': 1,
    })
  })

  it('recentDays：含今天、升序、天数正确', () => {
    const days = recentDays('2026-09-05', 14)
    expect(days).toHaveLength(14)
    expect(days[13]).toBe('2026-09-05')
    expect(days[0]).toBe('2026-08-23')
    expect([...days].sort()).toEqual(days) // 升序
  })
})

describe('habits store（打卡乐观更新 + 回滚）', () => {
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 8, 5, 12))
    setActivePinia(createPinia())
  })

  it('checkInToday 成功：done_today/today_count/streak 乐观推进', async () => {
    const store = useHabitsStore()
    store.items = [makeHabit({ status: { today_count: 0, period_count: 0, streak: 3, done_today: false } })]
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ id: 5, habit_id: 1, date: '2026-09-05', count: 1 })),
    )
    const ok = await store.checkInToday(1)
    expect(ok).toBe(true)
    expect(store.items?.[0].status.done_today).toBe(true)
    expect(store.items?.[0].status.today_count).toBe(1)
    expect(store.items?.[0].status.streak).toBe(4)
    vi.unstubAllGlobals()
  })

  it('checkInToday 失败：三字段全部回滚且 actionError 可见（约束①）', async () => {
    const store = useHabitsStore()
    store.items = [makeHabit({ status: { today_count: 0, period_count: 0, streak: 3, done_today: false } })]
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: '习惯不存在' }, 404)))
    const ok = await store.checkInToday(1)
    expect(ok).toBe(false)
    const s = store.items![0].status
    expect(s.done_today).toBe(false)
    expect(s.today_count).toBe(0)
    expect(s.streak).toBe(3)
    expect(store.actionError).toContain('打卡未保存')
    vi.unstubAllGlobals()
  })

  it('uncheckToday：撤销带 date（实测空 body 422 的坑）且失败回滚', async () => {
    const store = useHabitsStore()
    store.items = [makeHabit({ status: { today_count: 1, period_count: 1, streak: 2, done_today: true } })]
    const spy = vi.fn(async (url: string | URL | Request, init?: { body?: string }) => {
      void init // 仅在下方断言 fetch 调用参数时读取
      const u = String(url)
      if (u.includes('/uncheck')) {
        // 断言请求体带 date
        return jsonResponse({ ok: true })
      }
      return jsonResponse({ ok: true })
    })
    vi.stubGlobal('fetch', spy)
    const ok = await store.uncheckToday(1)
    expect(ok).toBe(true)
    const s = store.items![0].status
    expect(s.done_today).toBe(false)
    expect(s.today_count).toBe(0)
    // 请求体确实带了 date（通过 fetch 调用参数检查）
    const call = spy.mock.calls.find((c) => String(c[0]).includes('/uncheck'))
    expect(call).toBeTruthy()
    const body = JSON.parse(String(call?.[1]?.body ?? '{}'))
    expect(body.date).toBe('2026-09-05')
    vi.unstubAllGlobals()
  })

  it('remove：软删除移除卡片与打卡带，失败回滚', async () => {
    const store = useHabitsStore()
    store.items = [makeHabit({ id: 3 })]
    store.logsByHabit = { 3: { '2026-09-05': 1 } }
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: 'nope' }, 500)))
    const ok = await store.remove(3)
    expect(ok).toBe(false)
    expect(store.items?.map((h) => h.id)).toEqual([3]) // 回滚
    expect(store.logsByHabit[3]).toEqual({ '2026-09-05': 1 })
    vi.unstubAllGlobals()
  })
})
