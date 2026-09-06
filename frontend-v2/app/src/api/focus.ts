/**
 * 番茄钟（专注计时）客户端。
 * 契约：/api/focus 系列响应已 typed（TimeLogOut/FocusStatsOut/FocusStopMissOut），
 * 日志/统计/停钟未命中均派生自 contracts 生成类型，不再手写字段。已核实行为：
 * - 开始：POST /api/focus/start（201），body TimerStart{task_id?, task_title='', kind='focus'|'break'} → log
 * - 结束：POST /api/focus/stop，body {log_id?}（缺省停当前）→ log；无进行中 → {"ok": false, "stopped": null}
 * - 当前：GET /api/focus/current → log | null（再 start 会顶替 current 指向最新一条）
 * - 历史：GET /api/focus/logs?days=7&task_id= → log[]
 * - 删除：DELETE /api/focus/logs/{log_id} → 204；409 = 该条仍在进行中不可删
 * - 统计：GET /api/focus/stats?days=7 → {by_day:[{date,minutes}], by_task:[{task_title,minutes}], total_minutes}
 * started_at/ended_at 为本地 naive ISO 字符串（无时区后缀），new Date 按本地时区解析即与后端一致。
 */
import type { components } from './contracts/rest'
import { http } from './http'

export type FocusKind = 'focus' | 'break'

/** 计时记录 = 生成 TimeLogOut。kind 后端为自由串，实际取值 focus|break。 */
export type FocusLog = components['schemas']['TimeLogOut']

/** 统计 = 生成 FocusStatsOut（by_day/by_task 项见 ByDayItem/ByTaskItem）。 */
export type FocusStats = components['schemas']['FocusStatsOut']

/** POST /stop 时无进行中计时的回包 = 生成 FocusStopMissOut（有则直接返回结账后的 FocusLog）。 */
export type FocusStopMiss = components['schemas']['FocusStopMissOut']

export interface FocusStartBody {
  task_id?: number | null
  task_title?: string
  kind?: FocusKind
}

export function startFocus(body: FocusStartBody): Promise<FocusLog> {
  return http.post('/api/focus/start', body)
}

export function stopFocus(logId?: number): Promise<FocusLog | FocusStopMiss> {
  return http.post('/api/focus/stop', logId === undefined ? {} : { log_id: logId })
}

export function getCurrentFocus(): Promise<FocusLog | null> {
  return http.get('/api/focus/current')
}

export function listFocusLogs(days = 7, taskId?: number): Promise<FocusLog[]> {
  return http.get('/api/focus/logs', { days, task_id: taskId })
}

/** 删除一条计时记录（204）；该条仍在进行中时后端 409（按 http 层惯例抛 HttpError，交给 store 捕获）。 */
export function deleteFocusLog(logId: number): Promise<void> {
  return http.del(`/api/focus/logs/${logId}`)
}

export function getFocusStats(days = 7): Promise<FocusStats> {
  return http.get('/api/focus/stats', { days })
}
