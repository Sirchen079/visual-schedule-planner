/**
 * 任务 store：看板视图（/board）+ 时间轴视图（/timeline）共用。
 *
 * - 看板：按状态三列（待办/进行中/已完成）或按截止日期分组切换；完成态切换走 PATCH
 *   （乐观更新 + 失败回滚，约束①失败可见不沉默）。
 * - 时间轴：任务（due_date）+ 任务排程负载（/api/schedule/range，端点语义见 api/schedule.ts
 *   文件头 —— 它是「任务负载视图」不是事件视图）合并成按日纵览，纯函数 buildTaskTimeline 可单测。
 * - refreshAll 供「run done 后自动刷新」调用：AI 写操作（create_task/update_task/
 *   delete_task 等）落库发生在 done 之前，只刷新已加载过的部分，未进过的视图不白发请求。
 * - 分组/归桶/合并逻辑抽成纯函数导出，便于单测（沿用 schedule store 范式）。
 */
import { defineStore } from 'pinia'
import type { Task, TaskStatus } from '../api/tasks'
import { createTask, deleteTask, getTask, listTasks, restoreTask, updateSubtask, updateTask } from '../api/tasks'
import type { RangeDayLoad } from '../api/schedule'
import { getRangeView } from '../api/schedule'
import { addDays, parseIsoDate, toIsoDate } from '../utils/date'

/** 状态列（看板「按状态」模式）。 */
export const STATUS_COLUMNS: Array<{ key: TaskStatus; label: string }> = [
  { key: 'todo', label: '待办' },
  { key: 'doing', label: '进行中' },
  { key: 'done', label: '已完成' },
]

/** 截止日期归桶（看板「按日期」模式；今天由调用方传入保证纯函数确定性）。 */
export type DateBucket = 'overdue' | 'today' | 'tomorrow' | 'thisweek' | 'later' | 'nodate'

export const DATE_BUCKETS: Array<{ key: DateBucket; label: string }> = [
  { key: 'overdue', label: '已逾期' },
  { key: 'today', label: '今天' },
  { key: 'tomorrow', label: '明天' },
  { key: 'thisweek', label: '七天内' },
  { key: 'later', label: '以后' },
  { key: 'nodate', label: '无日期' },
]

/** '2026-09-07T00:00:00' → '2026-09-07'；null/非法原样返回 null。 */
export function datePart(iso: string | null): string | null {
  if (!iso) return null
  const m = /^(\d{4}-\d{2}-\d{2})/.exec(iso.trim())
  return m ? m[1] : null
}

/** 任务截止日相对 today 的归桶（无截止 → nodate；done 也参与归桶，由视图决定是否强调）。 */
export function bucketOf(task: Task, todayIso: string): DateBucket {
  const due = datePart(task.due_date)
  if (!due) return 'nodate'
  if (due < todayIso) return 'overdue'
  if (due === todayIso) return 'today'
  const d = parseIsoDate(due)
  const t = parseIsoDate(todayIso)
  const diffDays = Math.round((d.getTime() - t.getTime()) / 86_400_000)
  if (diffDays === 1) return 'tomorrow'
  if (diffDays <= 6) return 'thisweek'
  return 'later'
}

export function groupByStatus(items: Task[]): Record<TaskStatus, Task[]> {
  const by: Record<TaskStatus, Task[]> = { todo: [], doing: [], done: [] }
  for (const t of items) by[t.status]?.push(t)
  // 组内排序：截止升序（无日期垫底），再按优先级降序
  const prio: Record<string, number> = { high: 0, medium: 1, low: 2 }
  for (const k of Object.keys(by) as TaskStatus[]) {
    by[k].sort((a, b) => {
      const da = datePart(a.due_date)
      const db = datePart(b.due_date)
      if (da !== db) return (da ?? '9999') < (db ?? '9999') ? -1 : 1
      return (prio[a.priority] ?? 3) - (prio[b.priority] ?? 3)
    })
  }
  return by
}

export function groupByDate(items: Task[], todayIso: string): Record<DateBucket, Task[]> {
  const by: Record<DateBucket, Task[]> = { overdue: [], today: [], tomorrow: [], thisweek: [], later: [], nodate: [] }
  for (const t of items) by[bucketOf(t, todayIso)].push(t)
  for (const k of Object.keys(by) as DateBucket[]) {
    by[k].sort((a, b) => {
      const da = datePart(a.due_date) ?? '9999'
      const db = datePart(b.due_date) ?? '9999'
      if (da !== db) return da < db ? -1 : 1
      return (a.due_time ?? '99:99') < (b.due_time ?? '99:99') ? -1 : 1
    })
  }
  return by
}

/** 看板顶部统计（stats/summary 语义一致，但由列表本地推导，免额外请求）。 */
export function taskStats(items: Task[], todayIso: string): {
  total: number
  todo: number
  doing: number
  done: number
  overdue: number
  dueToday: number
} {
  let overdue = 0
  let dueToday = 0
  for (const t of items) {
    if (t.status !== 'done') {
      const b = bucketOf(t, todayIso)
      if (b === 'overdue') overdue += 1
      if (b === 'today') dueToday += 1
    }
  }
  return {
    total: items.length,
    todo: items.filter((t) => t.status === 'todo').length,
    doing: items.filter((t) => t.status === 'doing').length,
    done: items.filter((t) => t.status === 'done').length,
    overdue,
    dueToday,
  }
}

/** 时间轴单日行（任务截止 + 排程负载合并）。 */
export interface TimelineDay {
  date: string
  /** 该日截止的任务 */
  dueTasks: Task[]
  /** 该日排程的任务负载（/api/schedule/range items） */
  scheduled: Array<{ task_id: number | null; title: string; start_time: string | null; end_time: string | null; estimated_minutes: number | null }>
  /** 该日排程预估总分钟 */
  estimatedMinutes: number
}

/**
 * 合并任务（due_date）与排程负载（range view，生成类型 RangeDayLoad）为连续若干天的纵览。
 * - range 形状（typed）：{[date]: {items: RangeTaskItem[], estimated_minutes}}
 * - dates 是展示窗口（升序 ISO）；不在窗口内但有截止的任务不出现（时间轴只画窗口）。
 */
export function buildTaskTimeline(dates: string[], tasks: Task[], rangeView: Record<string, RangeDayLoad> | null): TimelineDay[] {
  const taskByDate = new Map<string, Task[]>()
  for (const t of tasks) {
    const due = datePart(t.due_date)
    if (!due) continue
    const arr = taskByDate.get(due)
    if (arr) arr.push(t)
    else taskByDate.set(due, [t])
  }
  return dates.map((date) => {
    const cell = rangeView?.[date]
    const scheduled = (cell?.items ?? [])
      .filter((i) => (i.title ?? '').trim().length > 0)
      .map((i) => ({
        task_id: i.task_id ?? null,
        title: i.title ?? '',
        start_time: i.start_time ?? null,
        end_time: i.end_time ?? null,
        estimated_minutes: i.estimated_minutes ?? null,
      }))      .sort((a, b) => (a.start_time ?? '99:99').localeCompare(b.start_time ?? '99:99'))
    return {
      date,
      dueTasks: [...(taskByDate.get(date) ?? [])].sort(
        (a, b) => (a.due_time ?? '99:99').localeCompare(b.due_time ?? '99:99'),
      ),
      scheduled,
      estimatedMinutes: cell?.estimated_minutes ?? 0,
    }
  })
}

export const useTasksStore = defineStore('tasks', {
  state: () => ({
    items: null as Task[] | null,
    loading: false,
    /** 时间轴：任务负载视图（/api/schedule/range，语义见 api/schedule.ts —— 任务负载不是事件） */
    range: null as Record<string, RangeDayLoad> | null,
    rangeDays: 14,
    loadingRange: false,
    rangeError: null as string | null,
    /** 进行中的乐观更新（id → 目标状态），视图据此禁用对应控件 */
    pendingIds: [] as number[],
    /** 进行中的子任务乐观更新（subtask id），视图据此禁用对应勾选 */
    pendingSubIds: [] as number[],
    error: null as string | null,
    /** 最近一次操作错误（乐观更新回滚等），视图行内展示 */
    actionError: null as string | null,
    lastRefreshedAt: null as number | null,
  }),

  getters: {
    /** todayIso 注入点（测试可拨时钟；视图用默认值） */
    stats(state): ReturnType<typeof taskStats> | null {
      if (state.items === null) return null
      return taskStats(state.items, toIsoDate(new Date()))
    },
    /** 时间轴窗口（今天起 rangeDays 天，升序） */
    timelineDates(state): string[] {
      const today = toIsoDate(new Date())
      return Array.from({ length: state.rangeDays }, (_, i) => addDays(today, i))
    },
    /** 合并后的时间轴行（任务截止 + 排程负载）；两路数据任一未加载则为 null */
    timeline(state): TimelineDay[] | null {
      if (state.items === null || state.range === null) return null
      return buildTaskTimeline(this.timelineDates, state.items, state.range)
    },
  },

  actions: {
    async load(): Promise<void> {
      this.loading = true
      this.error = null
      try {
        this.items = await listTasks()
        this.lastRefreshedAt = Date.now()
      } catch (e) {
        this.error = e instanceof Error ? e.message : '任务列表加载失败'
      } finally {
        this.loading = false
      }
    },

    /** run done 后由壳层调用：只刷已加载过的数据（不白发请求）。 */
    async refreshAll(): Promise<void> {
      const tasks: Promise<void>[] = []
      if (this.items !== null) tasks.push(this.load())
      if (this.range !== null) tasks.push(this.loadRange(this.rangeDays))
      await Promise.all(tasks)
    },

    /** 拉取时间轴窗口的任务负载视图（今天起 days 天）。 */
    async loadRange(days?: number): Promise<void> {
      const n = days ?? this.rangeDays
      this.rangeDays = n
      this.loadingRange = true
      this.rangeError = null
      try {
        const today = toIsoDate(new Date())
        this.range = await getRangeView(today, addDays(today, n - 1))
      } catch (e) {
        // range 是时间轴的负载侧；失败在时间轴行内可见（约束①），不影响看板列表
        this.rangeError = e instanceof Error ? `任务负载加载失败：${e.message}` : '任务负载加载失败'
      } finally {
        this.loadingRange = false
      }
    },

    /**
     * 完成态切换（看板核心交互）：乐观更新本地 → PATCH 落库；失败回滚并落 actionError
     * （约束①：失败不沉默）。status 语义：todo=未完成、doing=进行中、done=完成。
     */
    async setStatus(taskId: number, status: TaskStatus): Promise<boolean> {
      const task = this.items?.find((t) => t.id === taskId)
      if (!task || task.status === status) return true
      const prev = task.status
      task.status = status
      this.pendingIds.push(taskId)
      this.actionError = null
      try {
        const updated = await updateTask(taskId, { status })
        Object.assign(task, updated)
        return true
      } catch (e) {
        task.status = prev // 回滚
        this.actionError = e instanceof Error ? `「${task.title}」状态未保存：${e.message}` : '状态保存失败'
        return false
      } finally {
        this.pendingIds = this.pendingIds.filter((id) => id !== taskId)
      }
    },

    /** 完成态一键切换（勾选框语义）：done ↔ todo。 */
    async toggleDone(taskId: number): Promise<boolean> {
      const task = this.items?.find((t) => t.id === taskId)
      if (!task) return false
      return this.setStatus(taskId, task.status === 'done' ? 'todo' : 'done')
    },

    /**
     * 子任务完成态切换（看板卡/时间轴任务项的子任务清单点击）：乐观翻转本地 done →
     * PATCH 落定后以回包局部更新该子任务；失败回滚并落 actionError（约束①）。
     * 子任务生命周期会驱动父任务状态/进度（见 api/tasks.ts 头注释：全部完成 → 父任务 done），
     * 落定后局部重取父任务对齐；重取失败不回滚子任务（服务端已落定，下次 load 自然对齐）。
     */
    async toggleSubtask(taskId: number, subtaskId: number): Promise<boolean> {
      const task = this.items?.find((t) => t.id === taskId)
      const sub = task?.subtasks?.find((s) => s.id === subtaskId)
      if (!task || !sub) return false
      const prev = sub.done
      sub.done = !prev
      this.pendingSubIds.push(subtaskId)
      this.actionError = null
      try {
        const updated = await updateSubtask(taskId, subtaskId, { done: sub.done })
        sub.done = updated.done
        sub.completed_at = updated.completed_at
        try {
          Object.assign(task, await getTask(taskId))
        } catch {
          // 父任务对齐失败：子任务已在服务端落定，不回滚也不打断；下次 load 对齐
        }
        return true
      } catch (e) {
        sub.done = prev // 回滚
        this.actionError = e instanceof Error ? `「${sub.title}」未保存：${e.message}` : '子任务保存失败'
        return false
      } finally {
        this.pendingSubIds = this.pendingSubIds.filter((id) => id !== subtaskId)
      }
    },

    async create(input: Parameters<typeof createTask>[0]): Promise<Task | null> {
      this.actionError = null
      try {
        const task = await createTask(input)
        this.items = [...(this.items ?? []), task]
        return task
      } catch (e) {
        this.actionError = e instanceof Error ? e.message : '任务创建失败'
        return null
      }
    },

    /** 软删除（入回收站，可恢复）。乐观移除 + 失败回滚。 */
    async remove(taskId: number): Promise<boolean> {
      const items = this.items
      const idx = items?.findIndex((t) => t.id === taskId) ?? -1
      if (!items || idx < 0) return true
      const removed = items.splice(idx, 1)[0]
      this.actionError = null
      try {
        await deleteTask(taskId)
        return true
      } catch (e) {
        items.splice(idx, 0, removed) // 回滚
        this.actionError = e instanceof Error ? e.message : '删除失败'
        return false
      }
    },

    /** 从回收站恢复（回收站视图调用；恢复后看板列表下次 load 时自然出现）。 */
    async restore(taskId: number): Promise<boolean> {
      this.actionError = null
      try {
        await restoreTask(taskId)
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? e.message : '恢复失败'
        return false
      }
    },
  },
})
