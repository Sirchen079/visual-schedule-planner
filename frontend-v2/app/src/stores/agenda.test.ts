import { afterEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useScheduleStore } from './schedule'
import { occurrenceKey } from '../utils/eventPlacement'

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

it('loads task schedules, deadlines and subtasks into every view and refreshes moved/deleted items', async () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date(2032, 0, 16, 12))
  setActivePinia(createPinia())
  let records = [
    { kind: 'event', event_id: 1, date: '2032-01-16', title: '例会', start_time: '09:00', end_time: '10:00' },
    { kind: 'task', task_id: 1, entry_id: 1, date: '2032-01-16', title: '复习', start_time: null, end_time: null,
      subtasks: [{ id: 1, title: '练习题', done: false }] },
    { kind: 'task_due', task_id: 1, date: '2032-01-16', title: '复习', start_time: '18:00', end_time: null },
  ]
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const request = new URL(url, 'http://localhost')
    const query = request.searchParams
    const day = query.get('date')
    const filtered = records.filter(r => r.date >= (query.get('start') ?? day ?? '') && r.date <= (query.get('end') ?? day ?? ''))
    return new Response(JSON.stringify(request.pathname.endsWith('/agenda') ? filtered
      : request.pathname.endsWith('/day') ? { date: day, items: filtered } : []))
  }))
  const store = useScheduleStore()
  await store.loadSingleDay('2032-01-16')
  await store.loadMonth('2032-01-01')
  await store.refreshAll()
  for (const list of [store.occurrences, store.dayOccurrences, store.monthOccurrences]) {
    expect(list).toHaveLength(3)
    expect(new Set(list.map(occurrenceKey)).size).toBe(3)
    expect(list.find(r => r.kind === 'task')?.subtasks?.[0].title).toBe('练习题')
  }
  expect(store.today).toHaveLength(3)
  records = records.filter(r => r.kind !== 'event').map(r => ({ ...r, date: '2032-01-17' }))
  await store.refreshAll()
  expect(store.today).toEqual([])
  expect(store.dayOccurrences).toEqual([])
  expect(store.monthByDate['2032-01-16']).toBeUndefined()
  expect(store.monthByDate['2032-01-17']).toHaveLength(2)
})
