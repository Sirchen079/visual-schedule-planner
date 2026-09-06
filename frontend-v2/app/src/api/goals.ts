/** 目标与关键结果 REST 接口。支持软删除、恢复和永久删除。 */
import type { components } from './contracts/rest'
import { http } from './http'

type schemas = components['schemas']

/** 目标状态（update_goal 文档：active/paused/done/archived）。 */
export type GoalStatus = 'active' | 'paused' | 'done' | 'archived'

/** 关键结果 = 生成 KeyResultOut（逐字段一致）。 */
export type KeyResult = schemas['KeyResultOut']

/** 目标 = 生成 GoalOut（含回收站字段 deleted_at；start/end_date 生成面可选）。 */
export type Goal = schemas['GoalOut']

/** 创建入参 = 生成 GoalCreate；notes 后端有缺省 → 保持可选。 */
export type GoalCreateInput = Partial<Omit<schemas['GoalCreate'], 'title'>> & { title: string }

/**
 * 更新入参：PATCH /api/goals/{id} 请求体在 openapi 仍为内联 object（未 typed）——
 * 手写面维持（update_goal 文档：title/notes/status/start_date/end_date 部分更新）。
 */
export interface GoalUpdateInput {
  title?: string
  notes?: string
  status?: GoalStatus
  start_date?: string | null
  end_date?: string | null
}

/** KR 创建入参 = 生成 KeyResultCreate；默认值字段保持可选。 */
export type KeyResultCreateInput = Partial<Omit<schemas['KeyResultCreate'], 'title'>> & { title: string }

/** progress 端点条目 = 生成 GoalProgressItemOut（0–100 整数进度）。 */
export type GoalProgressItem = schemas['GoalProgressItemOut']

/** 列表（改名 include_deleted；后端对旧名 include_archived 兼容保留）。 */
export function listGoals(includeDeleted = false): Promise<Goal[]> {
  return http.get<Goal[]>('/api/goals', { include_deleted: includeDeleted || undefined })
}

export function getGoal(goalId: number): Promise<Goal> {
  return http.get<Goal>(`/api/goals/${goalId}`)
}

export function createGoal(input: GoalCreateInput): Promise<Goal> {
  return http.post<Goal>('/api/goals', input)
}

export function updateGoal(goalId: number, patch: GoalUpdateInput): Promise<Goal> {
  return http.patch<Goal>(`/api/goals/${goalId}`, patch)
}

export function deleteGoal(goalId: number): Promise<void> {
  return http.del(`/api/goals/${goalId}`)
}

export function createKeyResult(goalId: number, input: KeyResultCreateInput): Promise<KeyResult> {
  return http.post<KeyResult>(`/api/goals/${goalId}/key-results`, input)
}

export function updateKeyResult(
  krId: number,
  patch: { title?: string; current_value?: number; target_value?: number; unit?: string },
): Promise<KeyResult> {
  return http.patch<KeyResult>(`/api/goals/key-results/${krId}`, patch)
}

export function deleteKeyResult(krId: number): Promise<void> {
  return http.del(`/api/goals/key-results/${krId}`)
}

export function getGoalProgress(goalId: number): Promise<GoalProgressItem[]> {
  return http.get<GoalProgressItem[]>(`/api/goals/${goalId}/progress`)
}
