/**
 * 日程域 REST 封装（/api/schedule/*）。类型以生成契约 rest.d.ts 为准（2026-09-05 契约批次全 typed）：
 * - GET /api/schedule/events/expand?start&end → ExpandedEventOut[]（后端负责 RRULE 展开，
 *   含单双周；一条 RRULE 事件在同一周可能展开出多条，按 event_id+date 区分落点）
 * - GET /api/schedule/day?date → DayViewOut（items 含 kind:'event' 的已展开课程，
 *   也可能含任务排程条目）
 *
 * 注意：GET /api/schedule/range 是「任务排程负载视图」（每日任务明细 + 预估时长），
 * 不含课程 events —— 周视图必须走 /events/expand（实测 2026-09-07 周 range 返回全空而
 * expand 返回 5 节课，已记入联调报告）。
 */
/**
 * 契约批次（2026-09-05 #021 + B1-B6）后：schedule 端点全部 typed。
 * - range —— M3 时间轴的「任务负载视图」数据源，直接收敛到生成类型；
 * - day 视图 → DayViewOut/DayItemOut（#021 typed），本次收敛别名；
 * - re #B5：entries 三端点（列表/创建/更新 → ScheduleEntryOut）+ month → MonthDayOut[]
 *   补齐 typed——前端暂无消费方（周/日/月视图均走 events/expand），先落类型别名作收敛点；
 * - EventOccurrence 派生自生成 ExpandedEventOut 并保留可空时间并收窄地点/类别字段（见其注释，
 *   长期设计而非还债项）；EventDetail 已收敛到 EventDetailOut（`87cc99b`）。
 */
import type { components } from './contracts/rest'
import { http } from './http'

type schemas = components['schemas']

/** range 任务负载视图（生成类型，#021 批次收敛）。 */
export type RangeDayLoad = schemas['RangeDayLoad']
export type RangeTaskItem = schemas['RangeTaskItem']

/**
 * re #B5（2026-09-05）：entries 三端点与 month 端点 typed。
 * 别名导出作为前端消费收敛点；调用函数待 entries 视图接入时再补。
 */
export type ScheduleEntry = schemas['ScheduleEntryOut']
export type ScheduleEntryCreate = schemas['ScheduleEntryCreate']
export type ScheduleEntryUpdate = schemas['ScheduleEntryUpdate']
export type MonthDay = schemas['MonthDayOut']

/** 展开日程保留真实的可空时间；全天与时间未定事项不能伪造为课程时段。
 * 地点、类别由领域服务始终返回字符串，空值用空字符串表达。 */
export interface EventOccurrence extends Omit<schemas['ExpandedEventOut'], 'start_time' | 'end_time' | 'location' | 'category'> {
  start_time: string | null
  end_time: string | null
  location: string
  category: string
}

/** 统一日视图 = 生成 DayViewOut / DayItemOut（#021 typed）。 */
export type DayView = schemas['DayViewOut']
export type DayItem = schemas['DayItemOut']

/**
 * 事件详情 = 生成 EventDetailOut（2026-09-05 `87cc99b` 起该端点 typed，re #033 批次；
 * repeat_note 正式透出——详情卡仍优先用点击处 occurrence 的 hint，回包透出作兜底，
 * 见 CalendarView / EventDetailCard）。location/category/notes 生成面非空（后端落 ""）。
 */
export type EventDetail = schemas['EventDetailOut']

export function expandEvents(start: string, end: string): Promise<EventOccurrence[]> {
  return http.get<EventOccurrence[]>('/api/schedule/events/expand', { start, end })
}

/**
 * 任务负载视图（GET /api/schedule/range?start&end）——「日期键 → 当日排期任务明细 + 预估总时长」。
 * 端点语义（FRONTEND_HANDBOOK §3 日程视图选型）：不含独立日程，供负载/时间轴界面使用，
 * 不能拿它画周日历（那是 events/expand 的事）。返回 Record<date, RangeDayLoad>（生成类型）。
 */
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

/**
 * 冲突与空闲（M2 验收缺口「冲突与空闲展示」，2026-09-05 typed 契约收敛）：
 * - GET /api/schedule/conflicts?start&end → ConflictOut[]：每天一条 {date, items}，
 *   无冲突的日期 items 为空；ConflictItemOut 是 event 展开条目与任务排期条目的
 *   字段并集（event_id/entry_id/task_id 按存在字段判别；start_time/end_time 等
 *   生成面可空，渲染方需兜底——title 恒非空）。
 * - GET /api/schedule/free-slots?date&min_minutes → FreeSlotOut[]：工作时段内的
 *   整段空档（探针实测空闲日返回 [{"start":"09:00","end":"18:00","minutes":540}]）。
 */
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
