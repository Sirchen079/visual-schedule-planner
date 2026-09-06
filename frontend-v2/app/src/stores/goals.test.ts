import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { GOAL_STATUS_LABELS, goalPercent, krPercent, useGoalsStore } from './goals'
import type { Goal, KeyResult } from '../api/goals'

function jsonResponse(payload: unknown, status = 200): Response {
  const text = JSON.stringify(payload)
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => text,
    json: async () => JSON.parse(text),
  } as unknown as Response
}

/** 真实形状（2026-09-05 于 d0f5474 POST /api/goals 与 /key-results 实测）。 */
function makeKr(partial: Partial<KeyResult>): KeyResult {
  return {
    id: 1,
    goal_id: 1,
    title: 'KR：专业课均分85',
    kind: 'manual',
    target_value: 85,
    current_value: 0,
    unit: '分',
    link: '',
    ...partial,
  }
}

function makeGoal(partial: Partial<Goal>): Goal {
  return {
    id: 1,
    title: 'M3测试目标',
    notes: '',
    status: 'active',
    start_date: '2026-09-01',
    end_date: '2027-01-31',
    key_results: [],
    ...partial,
  }
}

describe('goals 纯函数', () => {
  it('krPercent：current/target 百分比并钳制 0–100，target<=0 防除零', () => {
    expect(krPercent(makeKr({ current_value: 78, target_value: 85 }))).toBe(92) // 与实测 /progress 端点一致
    expect(krPercent(makeKr({ current_value: 200, target_value: 100 }))).toBe(100)
    expect(krPercent(makeKr({ current_value: -5, target_value: 100 }))).toBe(0)
    expect(krPercent(makeKr({ current_value: 10, target_value: 0 }))).toBe(0)
  })

  it('goalPercent：KR 均值；无 KR 为 null（视图显示「未设 KR」）', () => {
    expect(goalPercent(makeGoal({ key_results: [] }))).toBeNull()
    expect(
      goalPercent(
        makeGoal({
          key_results: [
            makeKr({ id: 1, current_value: 85, target_value: 85 }), // 100%
            makeKr({ id: 2, current_value: 0, target_value: 100 }), // 0%
          ],
        }),
      ),
    ).toBe(50)
  })

  it('GOAL_STATUS_LABELS：后端四态全覆盖', () => {
    expect(Object.keys(GOAL_STATUS_LABELS).sort()).toEqual(['active', 'archived', 'done', 'paused'])
  })
})

describe('goals store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('updateKrProgress 成功：乐观更新以后端回包落定', async () => {
    const store = useGoalsStore()
    const kr = makeKr({ id: 9, current_value: 0 })
    store.items = [makeGoal({ key_results: [kr] })]
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ ...kr, current_value: 60 })))
    const ok = await store.updateKrProgress(9, 60)
    expect(ok).toBe(true)
    expect(store.items?.[0].key_results[0].current_value).toBe(60)
    expect(store.actionError).toBeNull()
    vi.unstubAllGlobals()
  })

  it('updateKrProgress 失败：回滚 current_value 且 actionError 可见（约束①）', async () => {
    const store = useGoalsStore()
    const kr = makeKr({ id: 9, current_value: 20 })
    store.items = [makeGoal({ key_results: [kr] })]
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: 'KR 不存在' }, 404)))
    const ok = await store.updateKrProgress(9, 99)
    expect(ok).toBe(false)
    expect(store.items?.[0].key_results[0].current_value).toBe(20) // 回滚
    expect(store.actionError).toContain('进度未保存')
    vi.unstubAllGlobals()
  })

  it('addKeyResult：新 KR 内嵌进目标', async () => {
    const store = useGoalsStore()
    store.items = [makeGoal({ key_results: [] })]
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(makeKr({ id: 12, goal_id: 1, title: '新KR' }))),
    )
    const added = await store.addKeyResult(1, { title: '新KR', target_value: 10 })
    expect(added?.title).toBe('新KR')
    expect(store.items?.[0].key_results).toHaveLength(1)
    vi.unstubAllGlobals()
  })

  it('refreshAll：未加载过不白发请求', async () => {
    const store = useGoalsStore()
    const spy = vi.fn(async () => jsonResponse([]))
    vi.stubGlobal('fetch', spy)
    await store.refreshAll()
    expect(spy).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })
})
