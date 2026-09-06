import type { EventOccurrence } from '../api/schedule'
import { AXIS_END_MIN, AXIS_START_MIN } from './date'

type TimedOccurrence = EventOccurrence & { start_time: string; end_time: string }
/** Only fully placed intervals belong on the daytime axis; all other events keep a visible list entry. */
export function fitsCalendarAxis(event: EventOccurrence): event is TimedOccurrence {
  const start = event.start_time, end = event.end_time
  if (!start || !end || !/^([01]\d|2[0-3]):[0-5]\d$/.test(start) || !/^([01]\d|2[0-3]):[0-5]\d$/.test(end)) return false
  const minute = (clock: string) => Number(clock.slice(0, 2)) * 60 + Number(clock.slice(3))
  return minute(start) >= AXIS_START_MIN && minute(end) <= AXIS_END_MIN && minute(end) > minute(start)
}

export function occurrenceTime(event: EventOccurrence): string {
  if (!event.start_time && !event.end_time) return '全天'
  return `${event.start_time || '开始未定'}–${event.end_time || '结束未定'}`
}
