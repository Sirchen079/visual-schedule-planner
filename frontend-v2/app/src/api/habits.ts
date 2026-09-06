/**
 * 习惯域 REST 封装（/api/habits/*）。类型已收敛到生成契约 rest.d.ts
 * （2026-09-05 契约批次 B1-B6 后全 typed，re #B3）：
 * - GET /api/habits → HabitOut[]（status 实时状态仅列表端点携带）
 * - POST /api/habits {HabitCreate} → 201 HabitOut（**实测不携带 status**，2026-09-05 探针确认）
 * - DELETE /api/habits/{id} → 204（软删除）
 * - POST /api/habits/{id}/check-in {} → CheckInOut（body 可空）
 * - POST /api/habits/{id}/uncheck {date?} → UncheckOut；date 可省略（缺省=今天，re #B3——
 *   旧「空 body 实测 422」坑后端已修复并与 openapi schema 对齐）
 * - GET /api/habits/{id}/logs?days=N → HabitLogOut[]
 */
import type { components } from './contracts/rest'
import { http } from './http'

type schemas = components['schemas']

/** 打卡周期（update_habit 文档：daily/weekly；生成面为 string）。 */
export type HabitPeriod = 'daily' | 'weekly'

/** 实时状态 = 生成 HabitStatusOut（逐字段一致）。 */
export type HabitStatus = schemas['HabitStatusOut']

/** 习惯生成面（原始 HabitOut）：非列表端点（如 create）不携带 status。 */
export type HabitOut = schemas['HabitOut']

/**
 * 习惯（列表端点消费面）= 生成 HabitOut 的收窄：
 * - period 窄化为后端枚举 daily/weekly；
 * - status 生成面为 `HabitStatusOut | null`（仅列表端点携带），列表实测恒非空——
 *   【谨慎项保留收窄】HabitsView 直接读 h.status.done_today、store 乐观更新均依赖非空。
 */
export type Habit = Omit<HabitOut, 'period' | 'status'> & {
  period: HabitPeriod
  status: HabitStatus
}

/** status 缺省（非列表端点回包）→ 零值实时状态，入列表前归一化（store.create 使用）。 */
export function normalizeHabit(h: HabitOut): Habit {
  return {
    ...h,
    period: h.period as HabitPeriod,
    status: h.status ?? { today_count: 0, period_count: 0, streak: 0, done_today: false },
  }
}

/** 创建入参 = 生成 HabitCreate；默认值字段（notes/period/target_count/color）保持可选。 */
export type HabitCreateInput = Partial<Omit<schemas['HabitCreate'], 'name' | 'period'>> & {
  name: string
  period?: HabitPeriod
}

/** 打卡结果 = 生成 CheckInOut（逐字段一致）。 */
export type HabitCheckInResult = schemas['CheckInOut']

/** 打卡记录 = 生成 HabitLogOut（逐字段一致）。 */
export type HabitLog = schemas['HabitLogOut']

export async function listHabits(): Promise<Habit[]> {
  const list = await http.get<HabitOut[]>('/api/habits')
  return list.map(normalizeHabit)
}

export function createHabit(input: HabitCreateInput): Promise<HabitOut> {
  return http.post<HabitOut>('/api/habits', input)
}

export function deleteHabit(habitId: number): Promise<void> {
  return http.del(`/api/habits/${habitId}`)
}

export function checkIn(habitId: number): Promise<HabitCheckInResult> {
  return http.post<HabitCheckInResult>(`/api/habits/${habitId}/check-in`, {})
}

/** 撤销某天打卡：date 可选（re #B3：缺省=今天）。 */
export function uncheckHabit(habitId: number, date?: string): Promise<schemas['UncheckOut']> {
  return http.post<schemas['UncheckOut']>(`/api/habits/${habitId}/uncheck`, { date: date ?? null })
}

export function listHabitLogs(habitId: number, days = 14): Promise<HabitLog[]> {
  return http.get<HabitLog[]>(`/api/habits/${habitId}/logs`, { days })
}
