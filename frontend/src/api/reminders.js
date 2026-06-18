export function getDueReminders(hours = 24) {
  return fetch(`/reminders/due?hours=${hours}`).then((r) => {
    if (!r.ok) throw new Error(`提醒查询失败 (${r.status})`)
    return r.json()
  })
}
