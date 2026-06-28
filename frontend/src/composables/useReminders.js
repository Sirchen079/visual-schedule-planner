import { computed, onUnmounted, ref } from 'vue'
import { getDueReminders } from '../api/reminders'

const STORAGE_KEY = 'reminded_tasks'
const POLL_INTERVAL = 60_000

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

  async function refresh(silent = false) {
    if (!silent) loading.value = true
    try {
      const data = await getDueReminders(24)
      upcoming.value = data.upcoming
      overdue.value = data.overdue
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
      saveReminded(notified)
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

  return { upcoming, overdue, count, panelOpen, loading, refresh, start, stop }
}
