/**
 * 通知 store：未读数轮询 + 面板列表 + 已读维护。
 * - 无 SSE 推送：未读数 30s 轮询一次（startPolling/stopPolling 由壳层挂载/卸载调用，页面隐藏时暂停 tick，
 *   恢复可见立即补拉一次）；轮询失败静默（下一 tick 自愈），不打扰用户。
 * - 面板每次打开都重拉列表（openPanel，顺带校准未读数）；关闭只收面板不清数据。
 * - 已读走本地增量维护：markRead/markAllRead 成功后就地落章 read_at 并维护 unreadCount，不整表重拉闪烁。
 */
import { defineStore } from 'pinia'
import {
  getUnreadCount,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type Notification,
} from '../api/notifications'

/** 未读数轮询间隔（毫秒） */
export const NOTIFICATIONS_POLL_MS = 30_000

interface NotificationsState {
  unreadCount: number
  notifications: Notification[] | null
  panelOpen: boolean
  loading: boolean
  error: string | null
  /** 标记已读失败等操作级错误（与列表加载 error 分开，语义不互染） */
  actionError: string | null
  /** 正在标记已读的通知 id */
  markingRead: number[]
  markingAll: boolean
}

/** 页面是否隐藏（node 测试环境无 document，容错为「可见」） */
function isHidden(): boolean {
  return typeof document !== 'undefined' && document.visibilityState === 'hidden'
}

// 模块级定时器/监听器句柄：轮询是壳层级单例，不进响应式状态（同 run.ts 的 activeAbort 惯例）
let pollTimer: ReturnType<typeof setInterval> | null = null
let visibilityHandler: (() => void) | null = null

export const useNotificationsStore = defineStore('notifications', {
  state: (): NotificationsState => ({
    unreadCount: 0,
    notifications: null,
    panelOpen: false,
    loading: false,
    error: null,
    actionError: null,
    markingRead: [],
    markingAll: false,
  }),

  actions: {
    /** 拉一次未读数（轮询 tick 与恢复可见补拉共用）；失败静默等下一 tick。 */
    async refreshUnread(): Promise<void> {
      try {
        const r = await getUnreadCount()
        this.unreadCount = r.count
      } catch {
        // 轮询失败不打扰：下一 tick 重试
      }
    },

    /** 启动未读数轮询（幂等）：立即拉一次，此后每 30s 一 tick；页面隐藏时暂停、恢复可见即补拉。 */
    startPolling(): void {
      if (pollTimer !== null) return
      void this.refreshUnread()
      pollTimer = setInterval(() => {
        if (isHidden()) return
        void this.refreshUnread()
      }, NOTIFICATIONS_POLL_MS)
      if (typeof document !== 'undefined') {
        visibilityHandler = () => {
          if (document.visibilityState === 'visible') void this.refreshUnread()
        }
        document.addEventListener('visibilitychange', visibilityHandler)
      }
    },

    /** 停止轮询并解绑可见性监听（壳层 onUnmounted 调用；幂等，绝不泄漏 interval）。 */
    stopPolling(): void {
      if (pollTimer !== null) {
        clearInterval(pollTimer)
        pollTimer = null
      }
      if (visibilityHandler !== null && typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', visibilityHandler)
      }
      visibilityHandler = null
    },

    /** 打开面板：每次打开都重拉列表保证新鲜，未读数顺带与服务端对账。 */
    async openPanel(): Promise<void> {
      this.panelOpen = true
      this.loading = true
      this.error = null
      try {
        const [rows, unread] = await Promise.all([listNotifications(), getUnreadCount()])
        this.notifications = rows
        this.unreadCount = unread.count
      } catch (e) {
        this.error = e instanceof Error ? e.message : '通知加载失败'
      } finally {
        this.loading = false
      }
    },

    closePanel(): void {
      this.panelOpen = false
    },

    /** 单条已读：成功后就地落章 read_at 并扣减未读数；已是已读则不白发请求。 */
    async markRead(id: number): Promise<void> {
      const item = this.notifications?.find((n) => n.id === id)
      if (!item || item.read_at !== null || this.markingRead.includes(id)) return
      this.markingRead = [...this.markingRead, id]
      this.actionError = null
      try {
        await markNotificationRead(id)
        item.read_at = new Date().toISOString()
        if (this.unreadCount > 0) this.unreadCount -= 1
      } catch (e) {
        this.actionError = e instanceof Error ? e.message : '标记已读失败'
      } finally {
        this.markingRead = this.markingRead.filter((x) => x !== id)
      }
    },

    /** 全部已读：服务端把所有通知置读，本地就地落章面板内未读项并把未读数清零。 */
    async markAllRead(): Promise<void> {
      if (this.markingAll) return
      this.markingAll = true
      this.actionError = null
      try {
        await markAllNotificationsRead()
        const now = new Date().toISOString()
        for (const n of this.notifications ?? []) {
          if (n.read_at === null) n.read_at = now
        }
        this.unreadCount = 0
      } catch (e) {
        this.actionError = e instanceof Error ? e.message : '全部已读失败'
      } finally {
        this.markingAll = false
      }
    },
  },
})
