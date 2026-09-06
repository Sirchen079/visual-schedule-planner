/**
 * 通知客户端。
 * 契约：/api/notifications 系列响应已 typed（NotificationOut/UnreadOut/EnableOut），
 * 全部派生自 contracts 生成类型，不再手写字段。已核实行为：
 * - 列表：GET /api/notifications?limit= → 数组，read_at 为 null 即未读
 * - 未读数：GET /api/notifications/unread → {"count": n}
 * - 单条已读：POST /api/notifications/{id}/read → EnableOut（这里只用 ok）
 * - 全部已读：POST /api/notifications/read-all → EnableOut
 * - 无创建端点、无 SSE 推送 → 前端对未读数做 30s 轮询（页面可见时）
 */
import type { components } from './contracts/rest'
import { http } from './http'

/** 通知实形 = 生成 NotificationOut。task_id/read_at 可空；read_at 为 null 即未读。 */
export type Notification = components['schemas']['NotificationOut']

/** 未读数 = 生成 UnreadOut（前端 30s 轮询依据）。 */
export type UnreadOut = components['schemas']['UnreadOut']

/** 已读标记回包 = 生成 EnableOut（启用/切换类统一回包；这里只用 ok）。 */
export type NotificationReadResult = components['schemas']['EnableOut']

export function listNotifications(limit = 50): Promise<Notification[]> {
  return http.get('/api/notifications', { limit })
}

export function getUnreadCount(): Promise<UnreadOut> {
  return http.get('/api/notifications/unread')
}

export function markNotificationRead(id: number): Promise<NotificationReadResult> {
  return http.post(`/api/notifications/${id}/read`)
}

export function markAllNotificationsRead(): Promise<NotificationReadResult> {
  return http.post('/api/notifications/read-all')
}
