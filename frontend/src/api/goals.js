// OKR 目标 API 封装。相对路径 /goals：dev 经 Vite proxy，prod 同源走后端
// KR 的 link 约定：manual → {}；tag_task_count → { tag: "标签名" }；habit_checkins → { habit_id: 数字 }
const BASE = '/goals'

async function parse(res) {
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`请求失败 (${res.status}) ${text}`)
  }
  if (res.status === 204) return null
  return res.json()
}

// 默认带上已归档目标（界面置灰展示，便于取消归档）；后端已按 sort_order 排序
export function listGoals() {
  return fetch(`${BASE}?include_archived=true`).then(parse)
}

export function createGoal(goal) {
  return fetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(goal),
  }).then(parse)
}

export function updateGoal(id, patch) {
  return fetch(`${BASE}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  }).then(parse)
}

export function deleteGoal(id) {
  return fetch(`${BASE}/${id}`, { method: 'DELETE' }).then(parse)
}

export function createKeyResult(goalId, kr) {
  return fetch(`${BASE}/${goalId}/krs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(kr),
  }).then(parse)
}

// patch 可含 title/kind/target_value/unit/link/current_value（current_value 仅 manual 生效）
export function updateKeyResult(krId, patch) {
  return fetch(`${BASE}/krs/${krId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  }).then(parse)
}

export function deleteKeyResult(krId) {
  return fetch(`${BASE}/krs/${krId}`, { method: 'DELETE' }).then(parse)
}
