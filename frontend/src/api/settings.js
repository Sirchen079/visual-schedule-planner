// 应用设置 API 封装。相对路径 /settings：dev 经 Vite proxy，prod 同源走后端
const BASE = '/settings'

async function parse(res) {
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`请求失败 (${res.status}) ${text}`)
  }
  return res.json()
}

export function getSettings() {
  return fetch(BASE).then(parse)
}

export function updateSettings(patch) {
  return fetch(BASE, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ settings: patch }),
  }).then(parse)
}
