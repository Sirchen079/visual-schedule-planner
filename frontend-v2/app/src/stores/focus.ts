/**
 * 番茄钟 store：当前计时 + 本地秒针 + 今日累计。
 * - current：GET /api/focus/current（壳层挂载 init 一次，页面刷新后恢复进行中的计时）。
 * - 秒针本地推算：elapsed = now - started_at（本地 naive ISO，Date 解析即本地时间），
 *   1s interval 只更新 now 驱动重渲，绝不拿后端轮询当秒针；页面隐藏后 interval 被浏览器
 *   节流也无碍——恢复可见的第一个 tick 由 started_at 重算，自动校正。
 * - 防漂移：进行中每 45s 对账一次 /current（计时可能被其它端 stop/顶替），以远端为准落定。
 * - todayMinutes：GET /api/focus/stats?days=1 的 total_minutes；start/stop 成功后刷新。
 * - logs：GET /api/focus/logs?days=1 的今日记录（「记录」面板打开时才拉），按 started_at 倒序；
 *   removeLog 删除单条后出列并复用 stats 刷新路径校准今日累计；stop 成功后若已加载过则顺带刷新。
 */
import { defineStore } from 'pinia'
import {
  deleteFocusLog,
  getCurrentFocus,
  getFocusStats,
  listFocusLogs,
  startFocus,
  stopFocus,
  type FocusKind,
  type FocusLog,
} from '../api/focus'

/** 本地秒针间隔（毫秒） */
export const FOCUS_TICK_MS = 1_000
/** 每 N 个秒针对账一次 /current（45s，落在约定的 30~60s 区间） */
export const FOCUS_RECONCILE_TICKS = 45

interface FocusState {
  current: FocusLog | null
  todayMinutes: number
  /** 今日记录（logs 面板数据；null = 尚未加载过） */
  logs: FocusLog[] | null
  logsLoading: boolean
  logsError: string | null
  /** 单条删除失败提示（409 仍在进行中 / 其它异常） */
  logActionError: string | null
  /** 本地秒针基准（tick 更新，驱动 mm:ss 重算） */
  now: number
  starting: boolean
  stopping: boolean
  error: string | null
}

/** 由 started_at 推算已进行秒数（纯函数，单测用） */
export function elapsedSecondsOf(log: FocusLog | null, nowMs: number): number {
  if (!log) return 0
  const started = new Date(log.started_at).getTime()
  if (Number.isNaN(started)) return 0
  return Math.max(0, Math.floor((nowMs - started) / 1000))
}

/** 秒数 → mm:ss（满 1h 进位为 h:mm:ss；纯函数，单测用） */
export function formatElapsed(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = String(s % 60).padStart(2, '0')
  const mm = String(m).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

// 模块级定时器句柄与防漂移护栏：不进响应式状态（同 run.ts 的 activeAbort 惯例）
let tickTimer: ReturnType<typeof setInterval> | null = null
let tickCount = 0
/** 最近一次本端 stop 的时刻：对账结果若在其后瞬间到达，可能是 stop 前的旧态，拒绝采纳 */
let lastStopAt = 0

export const useFocusStore = defineStore('focus', {
  state: (): FocusState => ({
    current: null,
    todayMinutes: 0,
    logs: null,
    logsLoading: false,
    logsError: null,
    logActionError: null,
    now: Date.now(),
    starting: false,
    stopping: false,
    error: null,
  }),

  getters: {
    isRunning(state): boolean {
      return state.current !== null
    },
    isBreak(state): boolean {
      return state.current?.kind === 'break'
    },
    elapsedSeconds(state): number {
      return elapsedSecondsOf(state.current, state.now)
    },
    elapsedLabel(): string {
      return formatElapsed(this.elapsedSeconds)
    },
  },

  actions: {
    /** 壳层挂载时初始化：恢复进行中的计时 + 拉今日累计（幂等，重复调用只重拉数据）。 */
    async init(): Promise<void> {
      await this.reconcile()
      await this.refreshToday()
    },

    /** 壳层卸载时清理秒针 interval（幂等，绝不泄漏）。 */
    dispose(): void {
      this.stopTick()
    },

    /** 拉今日累计（days=1 的 total_minutes）。 */
    async refreshToday(): Promise<void> {
      try {
        const stats = await getFocusStats(1)
        this.todayMinutes = stats.total_minutes
      } catch (e) {
        this.error = e instanceof Error ? e.message : '专注统计加载失败'
      }
    },

    /** 拉今日记录（days=1），按 started_at 倒序落定（最新在最上）。 */
    async loadLogs(): Promise<void> {
      this.logsLoading = true
      this.logsError = null
      try {
        const logs = await listFocusLogs(1)
        this.logs = [...logs].sort((a, b) => (a.started_at < b.started_at ? 1 : a.started_at > b.started_at ? -1 : 0))
      } catch (e) {
        this.logsError = e instanceof Error ? e.message : '今日记录加载失败'
      } finally {
        this.logsLoading = false
      }
    },

    /**
     * 删除一条今日记录：成功后出列并刷新今日累计（删记录会改今日累计，复用 stats 路径）；
     * 409（该条仍在进行中）或其它异常 → logActionError 并保留该条，返回 false。
     */
    async removeLog(id: number): Promise<boolean> {
      this.logActionError = null
      try {
        await deleteFocusLog(id)
        if (this.logs !== null) this.logs = this.logs.filter((log) => log.id !== id)
        await this.refreshToday()
        return true
      } catch {
        this.logActionError = '该计时仍在进行中或删除失败'
        return false
      }
    },

    /**
     * 与服务端对账 /current：null → 落定空；log → 采纳（id 相同也整体替换，
     * 让服务端的 task_title/kind 修正可见）。stop 后瞬间的旧态拒绝采纳。
     */
    async reconcile(): Promise<void> {
      try {
        const remote = await getCurrentFocus()
        if (Date.now() - lastStopAt < 5_000 && remote !== null) return
        const vanished = this.current !== null && remote === null
        this.current = remote
        if (remote !== null) {
          this.now = Date.now()
          this.startTick()
        } else {
          this.stopTick()
          if (vanished) await this.refreshToday() // 计时被其它端结束：今日累计同步校准
        }
      } catch {
        // 对账失败忽略：下一轮再试；本地秒针不受影响
      }
    },

    /**
     * 开始一段计时（已在进行中时忽略——UI 只在空闲态露出开始表单）。
     * 成功即置 current、起秒针并刷新今日累计。
     */
    async start(kind: FocusKind, taskTitle = ''): Promise<void> {
      if (this.current !== null || this.starting) return
      this.starting = true
      this.error = null
      try {
        const log = await startFocus({ kind, task_title: taskTitle })
        this.current = log
        this.now = Date.now()
        this.startTick()
        await this.refreshToday()
      } catch (e) {
        this.error = e instanceof Error ? e.message : '专注启动失败'
      } finally {
        this.starting = false
      }
    },

    /** 结束当前计时（缺省停 current，后端幂等）；无论返回什么都落定空并刷新今日累计。 */
    async stop(): Promise<void> {
      if (this.current === null || this.stopping) return
      this.stopping = true
      this.error = null
      lastStopAt = Date.now()
      try {
        await stopFocus()
      } catch (e) {
        this.error = e instanceof Error ? e.message : '结束计时失败'
      } finally {
        this.current = null
        this.stopping = false
        this.stopTick()
      }
      await this.refreshToday()
      // 新结账的记录应立即出现在「记录」面板：仅当日志已加载过才顺带刷新（不主动拉）
      if (!this.error && this.logs !== null) await this.loadLogs()
    },

    /** 秒针：进行中才跑；每 45 tick 顺带对账一次（单一定时器，便于清理）。 */
    startTick(): void {
      if (tickTimer !== null) return
      tickCount = 0
      tickTimer = setInterval(() => {
        this.now = Date.now()
        tickCount += 1
        if (tickCount % FOCUS_RECONCILE_TICKS === 0) void this.reconcile()
      }, FOCUS_TICK_MS)
    },

    stopTick(): void {
      if (tickTimer !== null) {
        clearInterval(tickTimer)
        tickTimer = null
      }
    },
  },
})
