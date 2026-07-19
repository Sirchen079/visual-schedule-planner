// 习惯打卡 API 封装。相对路径 /habits：dev 经 Vite proxy，prod 同源走后端
const BASE = '/habits'

async function parse(res) {
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`请求失败 (${res.status}) ${text}`)
  }
  if (res.status === 204) return null
  return res.json()
}

export function listHabits() {
  return fetch(BASE).then(parse)
}

export function createHabit(habit) {
  return fetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(habit),
  }).then(parse)
}

export function updateHabit(id, patch) {
  return fetch(`${BASE}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  }).then(parse)
}

export function deleteHabit(id) {
  return fetch(`${BASE}/${id}`, { method: 'DELETE' }).then(parse)
}

// date 可选（YYYY-MM-DD），缺省由后端按当天处理；返回更新后的完整习惯（含 streak/进度）
export function checkHabit(id, date) {
  return fetch(`${BASE}/${id}/check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(date ? { date } : {}),
  }).then(parse)
}

export function uncheckHabit(id, date) {
  return fetch(`${BASE}/${id}/uncheck`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(date ? { date } : {}),
  }).then(parse)
}

export function getHabitLogs(id, days = 84) {
  return fetch(`${BASE}/${id}/logs?days=${days}`).then(parse)
}
