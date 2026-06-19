const BASE = '/files'

async function parse(res) {
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`请求失败 (${res.status}) ${text}`)
  }
  if (res.status === 204) return null
  return res.json()
}

export function listFiles(q = '') {
  const url = q ? `${BASE}?q=${encodeURIComponent(q)}` : BASE
  return fetch(url).then(parse)
}

export function uploadFile(file, notes = '') {
  const form = new FormData()
  form.append('file', file)
  form.append('notes', notes)
  return fetch(BASE, { method: 'POST', body: form }).then(parse)
}

export function deleteFile(id) {
  return fetch(`${BASE}/${id}`, { method: 'DELETE' }).then(parse)
}

export function listTrashFiles() {
  return fetch(`${BASE}/trash`).then(parse)
}

export function restoreFile(id) {
  return fetch(`${BASE}/${id}/restore`, { method: 'POST' }).then(parse)
}

export function purgeFile(id) {
  return fetch(`${BASE}/${id}/purge`, { method: 'DELETE' }).then(parse)
}

export function getContentUrl(id) {
  return `${BASE}/${id}/content`
}

export function listTaskFiles(taskId) {
  return fetch(`/tasks/${taskId}/files`).then(parse)
}

export function attachFile(taskId, fileId) {
  return fetch(`/tasks/${taskId}/files/${fileId}`, { method: 'POST' }).then(parse)
}

export function detachFile(taskId, fileId) {
  return fetch(`/tasks/${taskId}/files/${fileId}`, { method: 'DELETE' }).then(parse)
}
