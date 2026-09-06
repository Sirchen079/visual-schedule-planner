/** 任务、子任务及任务统计 REST 接口。请求和响应类型来自生成的 rest.d.ts。 */
import type { components, operations } from './contracts/rest'
import { http } from './http'

type schemas = components['schemas']

/** 任务状态枚举，与统计接口使用的状态一致。 */
export type TaskStatus = 'todo' | 'doing' | 'done'
export type TaskPriority = 'high' | 'medium' | 'low'

/**
 * 任务 = 生成 TaskRead（内嵌 subtasks）。
 * status/priority 收窄为后端枚举——【谨慎项保留】BoardView 以窄键索引
 * PRIORITY_LABEL: Record<TaskPriority, string>，看板状态列同依赖枚举键。
 */
export type Task = Omit<schemas['TaskRead'], 'status' | 'priority'> & {
  status: TaskStatus
  priority: TaskPriority
}

/** 子任务 = 生成 SubtaskRead（内嵌读取面）。 */
export type Subtask = schemas['SubtaskRead']

/** 子任务写端点（create/update）回包 = 生成 SubtaskWriteOut（SubtaskRead + task_id，typed）。 */
export type SubtaskWrite = schemas['SubtaskWriteOut']

/**
 * 创建入参 = 生成 TaskCreate 的前端面：后端有缺省的字段（notes/priority/status/recur_*）
 * 保持可选；priority/status 窄化为枚举。
 */
export type TaskCreateInput = Partial<Omit<schemas['TaskCreate'], 'priority' | 'status'>> & {
  priority?: TaskPriority
  status?: TaskStatus
}

/** 更新入参 = 生成 TaskUpdate（全字段可选，PATCH 语义）。 */
export type TaskUpdateInput = schemas['TaskUpdate']

/** 列表查询 = 生成 list_tasks 端点 query 面（随契约自动更新）。 */
export type ListTasksQuery = NonNullable<operations['list_tasks_api_tasks_get']['parameters']>['query']

export function listTasks(query: ListTasksQuery = {}): Promise<Task[]> {
  return http.get<Task[]>('/api/tasks', { ...query })
}

export function getTask(taskId: number): Promise<Task> {
  return http.get<Task>(`/api/tasks/${taskId}`)
}

export function createTask(input: TaskCreateInput): Promise<Task> {
  return http.post<Task>('/api/tasks', input)
}

export function updateTask(taskId: number, patch: TaskUpdateInput): Promise<Task> {
  return http.patch<Task>(`/api/tasks/${taskId}`, patch)
}

/** 软删除（入回收站）。 */
export function deleteTask(taskId: number): Promise<void> {
  return http.del(`/api/tasks/${taskId}`)
}

export function restoreTask(taskId: number): Promise<Task> {
  return http.post<Task>(`/api/tasks/${taskId}/restore`)
}

/** 物理删除（不可恢复）。 */
export function purgeTask(taskId: number): Promise<void> {
  return http.del(`/api/tasks/${taskId}/purge`)
}

export function listTrashTasks(): Promise<Task[]> {
  return http.get<Task[]>('/api/tasks/trash')
}

export function createSubtask(taskId: number, title: string): Promise<SubtaskWrite> {
  return http.post<SubtaskWrite>(`/api/tasks/${taskId}/subtasks`, { title })
}

export function updateSubtask(
  taskId: number,
  subtaskId: number,
  patch: { title?: string; done?: boolean; estimated_minutes?: number | null },
): Promise<SubtaskWrite> {
  return http.patch<SubtaskWrite>(`/api/tasks/${taskId}/subtasks/${subtaskId}`, patch)
}

export function deleteSubtask(taskId: number, subtaskId: number): Promise<void> {
  return http.del(`/api/tasks/${taskId}/subtasks/${subtaskId}`)
}

export function listTags(): Promise<string[]> {
  return http.get<string[]>('/api/tasks/tags')
}
