// 日记 API 封装。相对路径 /journal：dev 经 Vite proxy，prod 同源走后端
const BASE = '/journal'

async function parse(res) {
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    const err = new Error(`请求失败 (${res.status}) ${text}`)
    err.status = res.status
    throw err
  }
  if (res.status === 204) return null
  return res.json()
}

export function listEntries(limit = 30) {
  return fetch(`${BASE}?limit=${limit}`).then(parse)
}

// 404 = 该日无日记，调用方按 err.status === 404 视为空白新篇
export function getEntry(date) {
  return fetch(`${BASE}/${date}`).then(parse)
}

export function upsertEntry(date, payload) {
  return fetch(`${BASE}/${date}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(parse)
}

export function deleteEntry(date) {
  return fetch(`${BASE}/${date}`, { method: 'DELETE' }).then(parse)
}
