import type { EventOccurrence } from '../api/schedule'
import { AXIS_END_MIN, AXIS_START_MIN, minutesToHm, OPEN_END_MARKER_MINUTES } from './date'

const HM_PATTERN = /^([01]\d|2[0-3]):[0-5]\d$/

const toMinute = (clock: string) => Number(clock.slice(0, 2)) * 60 + Number(clock.slice(3))

/** 已定位到时间轴的条目：开始时间必有；结束时间可能缺（仅开始标注）。 */
export type PlacedOccurrence = EventOccurrence & { start_time: string }

export interface AxisInterval {
  start: string
  end: string
  /** true = 只有开始时间，end 是视觉标注（开始 + 45 分钟），不是真实结束 */
  openEnd: boolean
}

/**
 * 时间轴区间判定（日/周视图共用的单一规则）：
 * - 截止/开始类任务标记不上轴（保持「其他时段」列表展示，见 unified_range）。
 * - 有开始时间：8:00–21:00 轴内即上轴；无结束时间按「仅开始」标注（openEnd）。
 * - 有结束时间：须为合法 HH:MM、晚于开始且不超出轴，否则退回列表（不伪造位置）。
 * 返回 null = 不上时间轴，留在「全天、截止与其他时段」。
 */
export function axisInterval(event: EventOccurrence): AxisInterval | null {
  if (event.kind === 'task_due' || event.kind === 'task_start') return null
  const start = event.start_time
  if (!start || !HM_PATTERN.test(start)) return null
  const startMin = toMinute(start)
  if (startMin < AXIS_START_MIN || startMin >= AXIS_END_MIN) return null
  const end = event.end_time
  if (end) {
    if (!HM_PATTERN.test(end)) return null
    const endMin = toMinute(end)
    if (endMin <= startMin || endMin > AXIS_END_MIN) return null
    return { start, end, openEnd: false }
  }
  const markerEnd = Math.min(startMin + OPEN_END_MARKER_MINUTES, AXIS_END_MIN)
  return { start, end: minutesToHm(markerEnd), openEnd: true }
}

/** Only fully placed intervals belong on the daytime axis; all other events keep a visible list entry. */
export function fitsCalendarAxis(event: EventOccurrence): event is PlacedOccurrence {
  return axisInterval(event) !== null
}

/** 块内/列表 meta 文案：有结束时间显示区间；仅开始时明确「结束未定」，不暗示时长。 */
export function occurrenceRange(event: Pick<EventOccurrence, 'start_time' | 'end_time'>): string {
  if (!event.start_time) return '全天'
  return event.end_time ? `${event.start_time}–${event.end_time}` : `${event.start_time} · 结束未定`
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

/** 同一天重叠的安排并排显示，防止任务块遮住日程块；仅开始标注按其标注时长参与占道。 */
export function occurrenceLanes(items: EventOccurrence[]): Record<string, Record<string, string>> {
  const styles: Record<string, Record<string, string>> = {}
  const days = new Map<string, Array<{ item: EventOccurrence; interval: AxisInterval }>>()
  for (const item of items) {
    const interval = axisInterval(item)
    if (!interval) continue
    const day = days.get(item.date) ?? []
    day.push({ item, interval })
    days.set(item.date, day)
  }
  for (const day of days.values()) {
    day.sort((a, b) => a.interval.start.localeCompare(b.interval.start)
      || a.interval.end.localeCompare(b.interval.end))
    let group: Array<{ item: EventOccurrence; lane: number }> = []
    let ends: string[] = []
    const flush = () => {
      for (const { item, lane } of group) styles[occurrenceKey(item)] = {
        left: `calc(${100 * lane / ends.length}% + 4px)`,
        width: `calc(${100 / ends.length}% - 8px)`, right: 'auto',
      }
      group = []; ends = []
    }
    for (const { item, interval } of day) {
      if (ends.length && ends.every(end => end <= interval.start)) flush()
      let lane = ends.findIndex(end => end <= interval.start)
      if (lane < 0) lane = ends.length
      ends[lane] = interval.end
      group.push({ item, lane })
    }
    flush()
  }
  return styles
}
