import { describe, expect, it } from 'vitest'
import { fitsCalendarAxis, occurrenceTime } from './eventPlacement'
import { groupOccurrencesByDate } from '../stores/schedule'
import type { EventOccurrence } from '../api/schedule'

const base = { event_id: 1, title: '会议', date: '2032-01-16', location: '', category: 'general' }
const make = (start_time: string | null, end_time: string | null): EventOccurrence => ({ ...base, start_time, end_time })
describe('general calendar occurrences', () => {
  it('keeps all-day and incomplete intervals out of positioned blocks without inventing times', () => {
    expect(fitsCalendarAxis(make(null, null))).toBe(false)
    expect(occurrenceTime(make(null, null))).toBe('全天')
    expect(fitsCalendarAxis(make('15:00', null))).toBe(false)
    expect(occurrenceTime(make('15:00', null))).toContain('结束未定')
  })
  it('keeps early, late and overlapping-axis appointments visible in the additional list', () => {
    for (const pair of [['06:00', '07:00'], ['22:00', '23:00'], ['07:00', '09:00']]) expect(fitsCalendarAxis(make(pair[0], pair[1]))).toBe(false)
    expect(fitsCalendarAxis(make('08:00', '21:00'))).toBe(true)
  })
  it('sorts mixed all-day and timed events without dropping any', () => {
    const grouped = groupOccurrencesByDate([make('15:00', '16:00'), make(null, null), make('06:00', '07:00')])
    expect(grouped[base.date].map(event => event.start_time)).toEqual([null, '06:00', '15:00'])
  })
})
