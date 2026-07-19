// 计时器与时间记录 API 封装。相对路径：dev 经 Vite proxy，prod 同源走后端
async function parse(res) {
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`请求失败 (${res.status}) ${text}`)
  }
  if (res.status === 204) return null
  return res.json()
}

// kind: "pomodoro"（番茄钟，缺省）| "stopwatch"（正计时）；已有运行中计时时后端自动停掉前一个
export function startTimer(taskId, kind = 'pomodoro') {
  return fetch('/timer/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task_id: taskId, kind }),
  }).then(parse)
}

// 停掉当前运行中的计时并落库；无运行中计时时后端返回空
export function stopTimer() {
  return fetch('/timer/stop', { method: 'POST' }).then(parse)
}

// 当前运行中的 TimeLog，无则 null
export function getCurrentTimer() {
  return fetch('/timer/current').then(parse)
}

// TimeLog 列表：{id, task_id, task_title, kind, started_at, ended_at, minutes}
export function getTimeLogs(days = 30, taskId) {
  const qs = new URLSearchParams({ days: String(days) })
  if (taskId !== undefined && taskId !== null && taskId !== '') qs.set('task_id', String(taskId))
  return fetch(`/time-logs?${qs.toString()}`).then(parse)
}

// 时间投入统计：{daily, by_tag, by_task, estimates, total_minutes}
export function getTimeStats(days = 30) {
  return fetch(`/stats/time?days=${days}`).then(parse)
}
