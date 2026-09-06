/**
 * 任务域 REST 封装（/api/tasks/*）。类型已收敛到生成契约 rest.d.ts（2026-09-05 契约批次
 * B1-B6 后全 typed，re #B2/#B4）：
 * - GET /api/tasks?q&status&priority&tag&due_before&due_after → TaskRead[]
 * - POST /api/tasks {TaskCreate} → 201 TaskRead；PATCH /api/tasks/{id} {TaskUpdate} → TaskRead
 * - DELETE /api/tasks/{id} → 204（软删入回收站）；POST /{id}/restore → TaskRead；
 *   DELETE /{id}/purge → 204（物理删除）；GET /api/tasks/trash → TaskRead[]（re #B2）
 * - 子任务（re #B4/#033）：TaskRead 内嵌 subtasks: SubtaskRead[]，REST 可渲染子任务清单；
 *   create/update 子任务端点响应 = SubtaskWriteOut（SubtaskRead + task_id，写返回历来带
 *   归属；多出的 task_id 前端无消费方）
 *
 * 实测契约坑（维持记录）：
 * 1. due_date 入参接受 'YYYY-MM-DD'，回包是 'YYYY-MM-DDT00:00:00'（datetime）——展示取日期部分；
 * 2. 子任务生命周期会驱动父任务状态（创建子任务 → 父任务 doing；全部完成 → 父任务 done+progress 100）。
 */
import type { components, operations } from './contracts/rest'
import { http } from './http'

type schemas = components['schemas']

/** 任务状态（后端实测枚举；stats/summary 亦用 todo/doing/done 计数）。 */
export type TaskStatus = 'todo' | 'doing' | 'done'
export type TaskPriority = 'high' | 'medium' | 'low'

/**
 * 任务 = 生成 TaskRead（re #B4：内嵌 subtasks）。
 * status/priority 收窄为后端枚举——【谨慎项保留】BoardView 以窄键索引
 * PRIORITY_LABEL: Record<TaskPriority, string>，看板状态列同依赖枚举键。
 */
export type Task = Omit<schemas['TaskRead'], 'status' | 'priority'> & {
  status: TaskStatus
  priority: TaskPriority
}

/** 子任务 = 生成 SubtaskRead（re #B4 内嵌读取面）。 */
export type Subtask = schemas['SubtaskRead']

/** 子任务写端点（create/update）回包 = 生成 SubtaskWriteOut（SubtaskRead + task_id，re #033 typed）。 */
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
