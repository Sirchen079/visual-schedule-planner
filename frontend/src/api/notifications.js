// 通知中心 API 封装。相对路径 /notifications：dev 经 Vite proxy，prod 同源走后端
const BASE = '/notifications'

async function parse(res) {
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`请求失败 (${res.status}) ${text}`)
  }
  if (res.status === 204) return null
  return res.json()
}

export function listNotifications(limit = 50) {
  return fetch(`${BASE}?limit=${limit}`).then(parse)
}

export function getUnreadCount() {
  return fetch(`${BASE}/unread-count`).then(parse)
}

export function markNotificationRead(id) {
  return fetch(`${BASE}/${id}/read`, { method: 'POST' }).then(parse)
}

export function markAllNotificationsRead() {
  return fetch(`${BASE}/read-all`, { method: 'POST' }).then(parse)
}
