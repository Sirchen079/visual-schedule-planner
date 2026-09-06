/** 习惯及打卡 REST 接口。列表包含实时 status；创建响应可能不包含 status。 */
import type { components } from './contracts/rest'
import { http } from './http'

type schemas = components['schemas']

/** 打卡周期（update_habit 文档：daily/weekly；生成面为 string）。 */
export type HabitPeriod = 'daily' | 'weekly'

/** 实时状态 = 生成 HabitStatusOut（逐字段一致）。 */
export type HabitStatus = schemas['HabitStatusOut']

/** 习惯生成面（原始 HabitOut）：非列表端点（如 create）不携带 status。 */
export type HabitOut = schemas['HabitOut']

/** 视图使用的习惯类型。列表中的 status 非空，创建响应由 store 补充初始状态。 */
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

/** 撤销某天打卡：date 可选（缺省=今天）。 */
export function uncheckHabit(habitId: number, date?: string): Promise<schemas['UncheckOut']> {
  return http.post<schemas['UncheckOut']>(`/api/habits/${habitId}/uncheck`, { date: date ?? null })
}

export function listHabitLogs(habitId: number, days = 14): Promise<HabitLog[]> {
  return http.get<HabitLog[]>(`/api/habits/${habitId}/logs`, { days })
}
