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
  if (event.kind === 'task_due') return event.start_time ? `${event.start_time} 截止` : '当天截止'
  if (event.kind === 'task_start') return '开始'
  if (!event.start_time && !event.end_time) return '全天'
  return `${event.start_time || '开始未定'}–${event.end_time || '结束未定'}`
}

export function occurrenceKey(item: Pick<EventOccurrence, 'kind' | 'event_id' | 'task_id' | 'entry_id' | 'date'>): string {
  return `${item.kind ?? 'event'}-${item.entry_id ?? item.event_id ?? item.task_id}-${item.date}`
}

export function occurrenceTitle(item: EventOccurrence): string {
  const label = item.kind === 'task_due' ? '截止' : item.kind === 'task_start' ? '开始' : item.task_id != null ? '任务' : ''
  return `${label ? `${label} · ` : ''}${item.title}${item.task_status === 'done' ? '（已完成）' : ''}`
}

export function subtaskSummary(item: Pick<EventOccurrence, 'subtasks'>): string {
  return (item.subtasks ?? []).map(s => `${s.done ? '✓' : '○'} ${s.title}`).join('；')
}

/** 同一天重叠的安排并排显示，防止任务块遮住日程块。 */
export function occurrenceLanes(items: EventOccurrence[]): Record<string, Record<string, string>> {
  const styles: Record<string, Record<string, string>> = {}
  const days = new Map<string, TimedOccurrence[]>()
  for (const item of items.filter(fitsCalendarAxis)) {
    const day = days.get(item.date) ?? []
    day.push(item)
    days.set(item.date, day)
  }
  for (const day of days.values()) {
    day.sort((a, b) => a.start_time.localeCompare(b.start_time) || a.end_time.localeCompare(b.end_time))
    let group: Array<{ item: TimedOccurrence; lane: number }> = []
    let ends: string[] = []
    const flush = () => {
      for (const { item, lane } of group) styles[occurrenceKey(item)] = {
        left: `calc(${100 * lane / ends.length}% + 4px)`,
        width: `calc(${100 / ends.length}% - 8px)`, right: 'auto',
      }
      group = []; ends = []
    }
    for (const item of day) {
      if (ends.length && ends.every(end => end <= item.start_time)) flush()
      let lane = ends.findIndex(end => end <= item.start_time)
      if (lane < 0) lane = ends.length
      ends[lane] = item.end_time
      group.push({ item, lane })
    }
    flush()
  }
  return styles
}
