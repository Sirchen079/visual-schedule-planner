import { describe, expect, it } from 'vitest'
import { fitsCalendarAxis, occurrenceTime, occurrenceKey, occurrenceLanes } from './eventPlacement'
import { groupOccurrencesByDate } from '../stores/schedule'
import type { EventOccurrence } from '../api/schedule'

const base = { event_id: 1, title: '会议', date: '2032-01-16', location: '', category: 'general' }
const make = (start_time: string | null, end_time: string | null): EventOccurrence => ({ ...base, start_time, end_time })
describe('general calendar occurrences', () => {
  it('separates event, schedule and deadline IDs and labels deadline times', () => {
    const event = make('09:00', '10:00')
    const task = { ...event, event_id: null, task_id: 1, entry_id: 1, kind: 'task' }
    const due = { ...task, entry_id: null, kind: 'task_due', end_time: null }
    expect(new Set([event, task, due].map(occurrenceKey)).size).toBe(3)
    expect(occurrenceTime(due)).toBe('09:00 截止')
    expect(fitsCalendarAxis(due)).toBe(false)
  })
  it('lays overlapping tasks and events side by side, reusing space after the group', () => {
    const first = make('09:00', '10:00')
    const second = { ...make('09:30', '10:30'), event_id: null, task_id: 1, entry_id: 1, kind: 'task' }
    const third = { ...make('10:30', '11:00'), event_id: 3 }
    const nextDay = { ...first, date: '2032-01-17' }
    const lanes = occurrenceLanes([nextDay, third, second, first])
    expect(lanes[occurrenceKey(first)].width).toContain('50%')
    expect(lanes[occurrenceKey(second)].left).toContain('50%')
    expect(lanes[occurrenceKey(third)].width).toContain('100%')
    expect(lanes[occurrenceKey(nextDay)].width).toContain('100%')
  })
  it('keeps all-day items out of positioned blocks without inventing times', () => {
    expect(fitsCalendarAxis(make(null, null))).toBe(false)
    expect(occurrenceTime(make(null, null))).toBe('全天')
  })
  it('places start-only items as bounded markers on the axis', () => {
    expect(fitsCalendarAxis(make('15:00', null))).toBe(true)
    expect(occurrenceTime(make('15:00', null))).toContain('结束未定')
    // 标注块覆盖开始点起 45 分钟：与 15:30 开始的日程重叠，双列并排
    const open = make('15:00', null)
    const lanes = occurrenceLanes([make('15:30', '16:30'), open])
    expect(lanes[occurrenceKey(open)].left).toContain('0%')
    expect(lanes[occurrenceKey(open)].width).toContain('50%')
  })
  it('keeps early, late and overlapping-axis appointments visible in the additional list', () => {
    for (const pair of [['06:00', '07:00'], ['22:00', '23:00'], ['07:00', '09:00']]) expect(fitsCalendarAxis(make(pair[0], pair[1]))).toBe(false)
    expect(fitsCalendarAxis(make('08:00', '21:00'))).toBe(true)
    // 仅开始的日程同样受轴范围约束
    expect(fitsCalendarAxis(make('07:30', null))).toBe(false)
    expect(fitsCalendarAxis(make('23:00', null))).toBe(false)
  })
  it('sorts mixed all-day and timed events without dropping any', () => {
    const grouped = groupOccurrencesByDate([make('15:00', '16:00'), make(null, null), make('06:00', '07:00')])
    expect(grouped[base.date].map(event => event.start_time)).toEqual([null, '06:00', '15:00'])
  })
})
