const BASE = '/schedule'

async function parse(res) {
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`请求失败 (${res.status}) ${text}`)
  }
  if (res.status === 204) return null
  return res.json()
}

export function getDaySchedule(date) {
  return fetch(`${BASE}/day?date=${encodeURIComponent(date)}`).then(parse)
}

export function getMonthSchedule({ year, month }) {
  return fetch(
    `${BASE}/month?year=${encodeURIComponent(year)}&month=${encodeURIComponent(month)}`
  ).then(parse)
}

export function createScheduleEntry(payload) {
  return fetch(`${BASE}/entries`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(parse)
}

export function updateScheduleEntry(id, payload) {
  return fetch(`${BASE}/entries/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(parse)
}

export function deleteScheduleEntry(id) {
  return fetch(`${BASE}/entries/${id}`, { method: 'DELETE' }).then(parse)
}
