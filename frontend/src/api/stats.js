// 统计 API 封装。相对路径 /stats：dev 经 Vite proxy，prod 同源走后端
const BASE = '/stats'

async function parse(res) {
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`请求失败 (${res.status}) ${text}`)
  }
  if (res.status === 204) return null
  return res.json()
}

export function getSummary() {
  return fetch(`${BASE}/summary`).then(parse)
}

export function getDaily(days = 90) {
  return fetch(`${BASE}/daily?days=${days}`).then(parse)
}

export function getByTag() {
  return fetch(`${BASE}/by-tag`).then(parse)
}

export function getByPriority() {
  return fetch(`${BASE}/by-priority`).then(parse)
}

export function getTokenUsage(days = 30) {
  return fetch(`${BASE}/token-usage?days=${days}`).then(parse)
}

// 逾期风险预测：规则打分，按分数降序最多 10 条
export function getRisk() {
  return fetch(`${BASE}/risk`).then(parse)
}
