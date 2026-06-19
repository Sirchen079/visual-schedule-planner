// 任务 API 封装。相对路径 /tasks：dev 经 Vite proxy，prod 同源走后端
const BASE = '/tasks'

async function parse(res) {
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`请求失败 (${res.status}) ${text}`)
  }
  if (res.status === 204) return null
  return res.json()
}

export function listTasks() {
  return fetch(BASE).then(parse)
}

export function createTask(task) {
  return fetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(task),
  }).then(parse)
}

export function updateTask(id, patch) {
  return fetch(`${BASE}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  }).then(parse)
}

export function deleteTask(id) {
  return fetch(`${BASE}/${id}`, { method: 'DELETE' }).then(parse)
}

export function listTrash() {
  return fetch(`${BASE}/trash`).then(parse)
}

export function restoreTask(id) {
  return fetch(`${BASE}/${id}/restore`, { method: 'POST' }).then(parse)
}

export function purgeTask(id) {
  return fetch(`${BASE}/${id}/purge`, { method: 'DELETE' }).then(parse)
}

export function listTags() {
  return fetch(`${BASE}/tags`).then(parse)
}

export function createSubtask(taskId, title) {
  return fetch(`${BASE}/${taskId}/subtasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  }).then(parse)
}

export function updateSubtask(taskId, id, patch) {
  return fetch(`${BASE}/${taskId}/subtasks/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  }).then(parse)
}

export function deleteSubtask(taskId, id) {
  return fetch(`${BASE}/${taskId}/subtasks/${id}`, { method: 'DELETE' }).then(parse)
}
