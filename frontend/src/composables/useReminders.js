import { computed, onUnmounted, ref } from 'vue'
import { getDueReminders } from '../api/reminders'
import { getUnreadCount } from '../api/notifications'

const STORAGE_KEY = 'reminded_tasks'
const POLL_INTERVAL = 60_000

// 通知未读数为模块级共享状态：通知中心标记已读后调用 refreshUnreadCount 即时刷新角标，
// 不必等下一轮 60s 轮询；接口失败时保持上次值
const unreadCount = ref(0)

export async function refreshUnreadCount() {
  try {
    const data = await getUnreadCount()
    unreadCount.value = data?.unread ?? 0
  } catch {
    // 网络波动等：保持上次值，下次重试
  }
}

function loadReminded() {
  try {
    return new Set(JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'))
  } catch {
    return new Set()
  }
}

function saveReminded(set) {
  // 只保留最近 200 条，避免无限增长
  const arr = Array.from(set).slice(-200)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(arr))
}

export function useReminders() {
  const upcoming = ref([])
  const overdue = ref([])
  const triggered = ref([])
  const panelOpen = ref(false)
  const loading = ref(false)
  let timer = null
  const notified = loadReminded()

  const count = computed(() => upcoming.value.length + overdue.value.length)

  function notify(task, isOverdue = false) {
    const title = isOverdue ? '任务已逾期' : '任务即将到期'
    const body = `${task.title}${task.due_date ? '\n截止：' + new Date(task.due_date).toLocaleString('zh-CN') : ''}`
    try {
      if (window.Notification && Notification.permission === 'granted') {
        new Notification(title, { body })
      }
    } catch {
      // 通知 API 不可用时静默降级到页内提醒
    }
  }

  // 偏移分钟 → 中文文案（截止时 / 提前N分钟 / 提前N小时 / 提前N天）
  function offsetLabel(minutes) {
    if (!minutes) return '截止时'
    if (minutes % 1440 === 0) return `提前${minutes / 1440}天`
    if (minutes % 60 === 0) return `提前${minutes / 60}小时`
    return `提前${minutes}分钟`
  }

  function triggeredDueTime(item) {
    return item.task?.due_time || String(item.due_at || '').slice(11, 16)
  }

  // 到点提醒：标题为任务名，正文带截止时刻与偏移文案
  function notifyTriggered(item) {
    try {
      if (window.Notification && Notification.permission === 'granted') {
        new Notification(item.task.title, {
          body: `截止 ${triggeredDueTime(item)} · ${offsetLabel(item.offset_minutes)}`,
        })
      }
    } catch {
      // 通知 API 不可用时静默降级到页内提醒
    }
  }

  async function refresh(silent = false) {
    if (!silent) loading.value = true
    try {
      const data = await getDueReminders(24)
      upcoming.value = data.upcoming
      overdue.value = data.overdue
      triggered.value = data.triggered || []
      // 对新增的逾期/即将到期弹通知（去重）
      for (const t of overdue.value) {
        const key = `od-${t.id}`
        if (!notified.has(key)) {
          notify(t, true)
          notified.add(key)
        }
      }
      for (const t of upcoming.value) {
        const key = `up-${t.id}`
        if (!notified.has(key)) {
          notify(t, false)
          notified.add(key)
        }
      }
      // 到点提醒按 任务+触发时刻 去重（跨轮询只弹一次）
      for (const item of triggered.value) {
        const key = `zs-remind-${item.task.id}-${item.remind_at}`
        if (!notified.has(key)) {
          notifyTriggered(item)
          notified.add(key)
        }
      }
      saveReminded(notified)
      // 顺带刷新通知中心未读数（内部自行容错，失败保持上次值）
      await refreshUnreadCount()
    } catch {
      // 网络波动等：静默，下次重试
    } finally {
      loading.value = false
    }
  }

  function start() {
    refresh()
    timer = setInterval(() => refresh(true), POLL_INTERVAL)
  }

  function stop() {
    if (timer) clearInterval(timer)
    timer = null
  }

  onUnmounted(stop)

  return { upcoming, overdue, triggered, count, panelOpen, loading, unreadCount, refresh, start, stop }
}
