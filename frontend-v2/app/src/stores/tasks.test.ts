import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import {
  bucketOf,
  buildTaskTimeline,
  datePart,
  groupByDate,
  groupByStatus,
  taskStats,
  useTasksStore,
} from './tasks'
import type { Task } from '../api/tasks'

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

/** 真实形状（2026-09-05 于 d0f5474 POST /api/tasks 实测；subtasks 为 re #B4 内嵌面）。 */
function makeTask(partial: Partial<Task>): Task {
  return {
    id: 1,
    title: 'M3测试任务',
    notes: '',
    due_date: null,
    due_time: null,
    remind_offsets: [],
    priority: 'medium',
    status: 'todo',
    progress: 0,
    start_date: null,
    recur_rule: 'none',
    recur_interval: 1,
    recur_rrule: null,
    estimated_minutes: null,
    tags: [],
    created_at: '2026-09-05T10:00:00',
    updated_at: '2026-09-05T10:00:00',
    completed_at: null,
    subtasks: [],
    ...partial,
  }
}

const TODAY = '2026-09-05' // 周六

describe('tasks 纯函数', () => {
  it('datePart：实测回包 2026-09-07T00:00:00 → 2026-09-07', () => {
    expect(datePart('2026-09-07T00:00:00')).toBe('2026-09-07')
    expect(datePart(null)).toBeNull()
    expect(datePart('垃圾')).toBeNull()
  })

  it('bucketOf：逾期/今天/明天/七天内/以后/无日期', () => {
    expect(bucketOf(makeTask({ due_date: '2026-09-01T00:00:00' }), TODAY)).toBe('overdue')
    expect(bucketOf(makeTask({ due_date: '2026-09-05T00:00:00' }), TODAY)).toBe('today')
    expect(bucketOf(makeTask({ due_date: '2026-09-06T00:00:00' }), TODAY)).toBe('tomorrow')
    expect(bucketOf(makeTask({ due_date: '2026-09-11T00:00:00' }), TODAY)).toBe('thisweek')
    expect(bucketOf(makeTask({ due_date: '2026-09-12T00:00:00' }), TODAY)).toBe('later')
    expect(bucketOf(makeTask({ due_date: null }), TODAY)).toBe('nodate')
  })

  it('groupByStatus：三列分组，截止升序无日期垫底', () => {
    const items = [
      makeTask({ id: 1, status: 'done' }),
      makeTask({ id: 2, status: 'doing', due_date: '2026-09-08T00:00:00' }),
      makeTask({ id: 3, due_date: '2026-09-06T00:00:00' }),
      makeTask({ id: 4, due_date: null }),
    ]
    const by = groupByStatus(items)
    expect(by.todo.map((t) => t.id)).toEqual([3, 4])
    expect(by.doing.map((t) => t.id)).toEqual([2])
    expect(by.done.map((t) => t.id)).toEqual([1])
    // 无日期（id 4）排在没有日期任务的最后
    expect(by.todo[by.todo.length - 1].id).toBe(4)
  })

  it('groupByDate：六桶互斥且齐全', () => {
    const items = [
      makeTask({ id: 1, due_date: '2026-09-01T00:00:00' }),
      makeTask({ id: 2, due_date: `${TODAY}T00:00:00` }),
      makeTask({ id: 3, due_date: '2026-09-06T00:00:00' }),
      makeTask({ id: 4, due_date: '2026-09-09T00:00:00' }),
      makeTask({ id: 5, due_date: '2026-10-01T00:00:00' }),
      makeTask({ id: 6 }),
    ]
    const by = groupByDate(items, TODAY)
    expect(by.overdue.map((t) => t.id)).toEqual([1])
    expect(by.today.map((t) => t.id)).toEqual([2])
    expect(by.tomorrow.map((t) => t.id)).toEqual([3])
    expect(by.thisweek.map((t) => t.id)).toEqual([4])
    expect(by.later.map((t) => t.id)).toEqual([5])
    expect(by.nodate.map((t) => t.id)).toEqual([6])
  })

  it('taskStats：done 不计逾期/今日到期', () => {
    const items = [
      makeTask({ id: 1, status: 'todo', due_date: '2026-09-01T00:00:00' }),
      makeTask({ id: 2, status: 'done', due_date: '2026-09-01T00:00:00' }),
      makeTask({ id: 3, status: 'doing', due_date: `${TODAY}T00:00:00` }),
    ]
    expect(taskStats(items, TODAY)).toEqual({ total: 3, todo: 1, doing: 1, done: 1, overdue: 1, dueToday: 1 })
  })

  it('buildTaskTimeline：截止任务与 range 负载按日合并（生成类型 RangeDayLoad 形状）', () => {
    const dates = ['2026-09-05', '2026-09-06']
    const tasks = [
      makeTask({ id: 1, title: 'A', due_date: '2026-09-06T00:00:00', due_time: '18:00' }),
      makeTask({ id: 2, title: 'B', due_date: null }),
    ]
    const range = {
      '2026-09-05': {
        items: [
          { task_id: 2, title: '复习', start_time: '14:00', end_time: '15:00', estimated_minutes: 60 },
        ],
        estimated_minutes: 60,
      },
    }
    const tl = buildTaskTimeline(dates, tasks, range)
    expect(tl).toHaveLength(2)
    expect(tl[0].scheduled[0].title).toBe('复习')
    expect(tl[0].estimatedMinutes).toBe(60)
    expect(tl[0].dueTasks).toHaveLength(0)
    expect(tl[1].dueTasks.map((t) => t.title)).toEqual(['A'])
    // 无截止任务不落在任何一天
    expect(tl.every((d) => d.dueTasks.every((t) => t.id !== 2))).toBe(true)
  })
})

describe('tasks store（乐观更新 + 回滚）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('setStatus 成功：乐观更新后以后端回包落定', async () => {
    const store = useTasksStore()
    const task = makeTask({ id: 7, status: 'todo' })
    store.items = [task]
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ ...task, status: 'done', completed_at: '2026-09-05T11:00:00' })),
    )
    const ok = await store.setStatus(7, 'done')
    expect(ok).toBe(true)
    expect(store.items?.[0].status).toBe('done')
    expect(store.items?.[0].completed_at).toBe('2026-09-05T11:00:00')
    expect(store.actionError).toBeNull()
    expect(store.pendingIds).toHaveLength(0)
    vi.unstubAllGlobals()
  })

  it('setStatus 失败：回滚到原状态且 actionError 可见（约束①）', async () => {
    const store = useTasksStore()
    store.items = [makeTask({ id: 7, status: 'todo' })]
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ detail: '任务不存在' }, 404)),
    )
    const ok = await store.setStatus(7, 'done')
    expect(ok).toBe(false)
    expect(store.items?.[0].status).toBe('todo') // 回滚
    expect(store.actionError).toContain('未保存')
    expect(store.actionError).toContain('任务不存在')
    expect(store.pendingIds).toHaveLength(0)
    vi.unstubAllGlobals()
  })

  it('toggleDone：done ↔ todo', async () => {
    const store = useTasksStore()
    store.items = [makeTask({ id: 7, status: 'todo' })]
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ ...store.items![0], status: 'done' })))
    await store.toggleDone(7)
    expect(store.items?.[0].status).toBe('done')
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ ...store.items![0], status: 'todo', completed_at: null })))
    await store.toggleDone(7)
    expect(store.items?.[0].status).toBe('todo')
    vi.unstubAllGlobals()
  })

  it('toggleSubtask 成功：以回包落定子任务，并局部对齐被驱动的父任务状态', async () => {
    const store = useTasksStore()
    const sub = { id: 3, title: '读第一章', done: false, estimated_minutes: 20, completed_at: null }
    const task = makeTask({ id: 7, status: 'doing', progress: 40, subtasks: [sub] })
    store.items = [task]
    // 子任务全完成会驱动父任务 done+progress 100（后端行为，见 api/tasks.ts 头注释）：
    // PATCH 子任务 → SubtaskWriteOut，随后 GET 父任务对齐
    const spy = vi.fn(async (url: string | URL, init?: RequestInit) => {
      const u = String(url)
      if (init?.method === 'PATCH' && u === '/api/tasks/7/subtasks/3') {
        return jsonResponse({ id: 3, title: '读第一章', done: true, estimated_minutes: 20, completed_at: '2026-09-05T12:00:00', task_id: 7 })
      }
      if (u === '/api/tasks/7') {
        return jsonResponse({
          ...task,
          status: 'done',
          progress: 100,
          subtasks: [{ id: 3, title: '读第一章', done: true, estimated_minutes: 20, completed_at: '2026-09-05T12:00:00' }],
        })
      }
      return jsonResponse({ detail: `unexpected fetch ${init?.method ?? 'GET'} ${u}` }, 500)
    })
    vi.stubGlobal('fetch', spy)
    const ok = await store.toggleSubtask(7, 3)
    expect(ok).toBe(true)
    expect(store.items?.[0].subtasks?.[0].done).toBe(true)
    expect(store.items?.[0].subtasks?.[0].completed_at).toBe('2026-09-05T12:00:00')
    expect(store.items?.[0].status).toBe('done') // 父任务局部对齐
    expect(store.actionError).toBeNull()
    expect(store.pendingSubIds).toHaveLength(0)
    vi.unstubAllGlobals()
  })

  it('toggleSubtask 失败：回滚 done 且 actionError 可见，不触发父任务重取（约束①）', async () => {
    const store = useTasksStore()
    store.items = [
      makeTask({
        id: 7,
        subtasks: [{ id: 3, title: '读第一章', done: false, estimated_minutes: null, completed_at: null }],
      }),
    ]
    const spy = vi.fn(async () => jsonResponse({ detail: '子任务不存在' }, 404))
    vi.stubGlobal('fetch', spy)
    const ok = await store.toggleSubtask(7, 3)
    expect(ok).toBe(false)
    expect(store.items?.[0].subtasks?.[0].done).toBe(false) // 回滚
    expect(store.actionError).toContain('未保存')
    expect(store.actionError).toContain('子任务不存在')
    expect(store.pendingSubIds).toHaveLength(0)
    expect(spy).toHaveBeenCalledTimes(1) // 只有 PATCH，父任务重取不发生
    vi.unstubAllGlobals()
  })

  it('remove 失败：条目回滚回原位', async () => {
    const store = useTasksStore()
    store.items = [makeTask({ id: 1 }), makeTask({ id: 2 })]
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: 'db locked' }, 500)))
    const ok = await store.remove(1)
    expect(ok).toBe(false)
    expect(store.items?.map((t) => t.id)).toEqual([1, 2])
    expect(store.actionError).toContain('db locked')
    vi.unstubAllGlobals()
  })

  it('refreshAll：未加载过不白发请求', async () => {
    const store = useTasksStore()
    const spy = vi.fn(async () => jsonResponse([]))
    vi.stubGlobal('fetch', spy)
    await store.refreshAll()
    expect(spy).not.toHaveBeenCalled()
    await store.load()
    expect(spy).toHaveBeenCalled()
    vi.unstubAllGlobals()
  })
})
