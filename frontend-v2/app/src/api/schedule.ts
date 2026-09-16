/**
 * 日程 REST 接口及生成类型别名。
 * /events/expand 返回按 RRULE 展开的日程，按 event_id 与日期区分实例。
 * /range 返回任务排期负载；日历使用 /agenda 合并日程、任务排期及日期节点。
 */

import type { components } from './contracts/rest'
import { http } from './http'

type schemas = components['schemas']

/** range 任务负载视图（生成类型）。 */
export type RangeDayLoad = schemas['RangeDayLoad']
export type RangeTaskItem = schemas['RangeTaskItem']

/** 任务排期与月份汇总的生成类型别名。 */
export type ScheduleEntry = schemas['ScheduleEntryOut']
export type ScheduleEntryCreate = schemas['ScheduleEntryCreate']
export type ScheduleEntryUpdate = schemas['ScheduleEntryUpdate']
export type MonthDay = schemas['MonthDayOut']

export function getTaskEntries(taskId: number): Promise<ScheduleEntry[]> {
  return http.get<ScheduleEntry[]>(`/api/schedule/tasks/${taskId}/entries`)
}

/** 展开日程保留真实的可空时间；全天与时间未定事项不能伪造为课程时段。
 * 地点、类别由领域服务始终返回字符串，空值用空字符串表达。 */
export interface EventOccurrence extends Omit<schemas['ExpandedEventOut'], 'event_id' | 'start_time' | 'end_time' | 'location' | 'category'> {
  event_id: number | null
  kind?: string
  task_id?: number | null
  entry_id?: number | null
  task_status?: string | null
  subtasks?: schemas['ScheduledSubtaskOut'][]
  start_time: string | null
  end_time: string | null
  location: string
  category: string
}

/** 统一日视图 = 生成 DayViewOut / DayItemOut。 */
export type DayView = schemas['DayViewOut']
export type DayItem = schemas['DayItemOut']

/** 事件详情类型。repeat_note 提供重复规则说明，文本字段以空字符串表示未填写。 */
export type EventDetail = schemas['EventDetailOut']

export function expandEvents(start: string, end: string): Promise<EventOccurrence[]> {
  return http.get<EventOccurrence[]>('/api/schedule/events/expand', { start, end })
}

/** 日历与今日共用的数据源，保留来源 ID 供点击时打开对应任务或日程。 */
export async function getAgenda(start: string, end: string): Promise<EventOccurrence[]> {
  const items = await http.get<DayItem[]>('/api/schedule/agenda', { start, end })
  return items.map(item => ({ ...item, date: item.date!, event_id: item.event_id ?? null,
    start_time: item.start_time ?? null, end_time: item.end_time ?? null,
    location: item.location ?? '', category: item.category ?? '' }))
}

/** 任务负载视图：日期映射到排期明细与预估时长，不包含独立日程。 */
export function getRangeView(start: string, end: string): Promise<Record<string, RangeDayLoad>> {
  return http.get<Record<string, RangeDayLoad>>('/api/schedule/range', { start, end })
}

export function updateEvent(eventId: number, patch: schemas['EventUpdate']): Promise<EventDetail> {
  return http.patch<EventDetail>(`/api/schedule/events/${eventId}`, patch)
}

export function getEvent(eventId: number): Promise<EventDetail> {
  return http.get<EventDetail>(`/api/schedule/events/${eventId}`)
}

export function getDayView(date: string): Promise<DayView> {
  return http.get<DayView>('/api/schedule/day', { date })
}

export function deleteEvent(eventId: number): Promise<void> {
  return http.del(`/api/schedule/events/${eventId}`)
}

/** 冲突与空闲时段接口。冲突项包含事件或任务排期，空闲时段受工作时间设置约束。 */
export type ConflictDay = schemas['ConflictOut']
export type ConflictItem = schemas['ConflictItemOut']
export type FreeSlot = schemas['FreeSlotOut']

/** 冲突检测：[start, end] 闭区间逐日聚合（含无冲突日）。 */
export function getConflicts(start: string, end: string): Promise<ConflictDay[]> {
  return http.get<ConflictDay[]>('/api/schedule/conflicts', { start, end })
}

/** 空闲时段：某日工作时段内 ≥minMinutes 的整段空档（缺省 30 分钟）。 */
export function getFreeSlots(date: string, minMinutes = 30): Promise<FreeSlot[]> {
  return http.get<FreeSlot[]>('/api/schedule/free-slots', { date, min_minutes: minMinutes })
}
