const BASE = '/ai'
const DEFAULT_TIMEOUT_MS = 45000
const TEST_TIMEOUT_MS = 60000
const CHAT_TIMEOUT_MS = 180000

function redactErrorText(value) {
  return String(value ?? '')
    .replace(/(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s,;"'}]+/gi, '$1[已隐藏]')
    .replace(/(x-api-key\s*[:=]\s*)[^\s,;"'}]+/gi, '$1[已隐藏]')
    .replace(/((?:api[_-]?key|token|secret|password)["']?\s*[:=]\s*["']?)[^"',\s}]+/gi, '$1[已隐藏]')
    .replace(/\b(sk|ak|pk)-[A-Za-z0-9_-]{12,}\b/g, '$1-[已隐藏]')
}

function compactErrorMessage(value) {
  const text = redactErrorText(value)
    .replace(/\s+/g, ' ')
    .trim()
  if (!text) return ''
  return text.length > 260 ? `${text.slice(0, 260)}...` : text
}

function extractErrorMessage(payload) {
  if (!payload) return ''
  if (typeof payload === 'string') return payload
  if (Array.isArray(payload)) {
    return payload
      .map(extractErrorMessage)
      .filter(Boolean)
      .join('；')
  }
  if (typeof payload === 'object') {
    return (
      extractErrorMessage(payload.detail) ||
      extractErrorMessage(payload.message) ||
      extractErrorMessage(payload.error)
    )
  }
  return ''
}

async function parse(res) {
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    let detail = text
    try {
      detail = extractErrorMessage(JSON.parse(text))
    } catch {
      detail = text
    }
    const safeDetail = compactErrorMessage(detail)
    throw new Error(safeDetail ? `请求失败 (${res.status})：${safeDetail}` : `请求失败 (${res.status})`)
  }
  if (res.status === 204) return null
  return res.json()
}

function request(path, options = {}, timeoutMs = DEFAULT_TIMEOUT_MS) {
  const controller = new AbortController()
  let timedOut = false
  let onAbort = null
  const externalSignal = options.signal
  const timeoutId = window.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)

  if (externalSignal) {
    onAbort = () => controller.abort()
    if (externalSignal.aborted) onAbort()
    else externalSignal.addEventListener('abort', onAbort, { once: true })
  }

  const fetchOptions = { ...options, signal: controller.signal }

  return fetch(path, fetchOptions)
    .then(parse)
    .catch((err) => {
      if (timedOut) throw new Error('请求超时，请稍后重试')
      if (err?.name === 'AbortError') throw new Error('请求已取消')
      if (err instanceof TypeError) throw new Error('网络请求失败，请检查后端服务是否可用')
      if (err instanceof Error) throw new Error(compactErrorMessage(err.message) || '操作失败')
      throw new Error('操作失败')
    })
    .finally(() => {
      window.clearTimeout(timeoutId)
      if (externalSignal && onAbort) externalSignal.removeEventListener('abort', onAbort)
    })
}

export function listAiConfigs() {
  return request(`${BASE}/configs`)
}

export function createAiConfig(payload) {
  return request(`${BASE}/configs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function updateAiConfig(id, payload) {
  return request(`${BASE}/configs/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function enableAiConfig(id) {
  return request(`${BASE}/configs/${id}/enable`, { method: 'POST' })
}

export function testAiConfig(id) {
  return request(`${BASE}/configs/${id}/test`, { method: 'POST' }, TEST_TIMEOUT_MS)
}

export function listAiModels(payload) {
  return request(`${BASE}/models`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }, TEST_TIMEOUT_MS)
}

export function listAiConversations() {
  return request(`${BASE}/conversations`)
}

export function getAiConversation(id) {
  return request(`${BASE}/conversations/${id}`)
}

export function renameConversation(id, title) {
  return request(`${BASE}/conversations/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
}

export function deleteConversation(id) {
  return request(`${BASE}/conversations/${id}`, { method: 'DELETE' })
}

export function listAiSkills() {
  return request(`${BASE}/skills`)
}

export function createAiSkill(payload) {
  return request(`${BASE}/skills`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function updateAiSkill(id, payload) {
  return request(`${BASE}/skills/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function enableAiSkill(id) {
  return request(`${BASE}/skills/${id}/enable`, { method: 'POST' })
}

export function disableAiSkills() {
  return request(`${BASE}/skills/disable-all`, { method: 'POST' })
}

export function importAiSkill(payload) {
  return request(`${BASE}/skills/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function sendAiChat(payload, options = {}) {
  return request(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: options.signal,
  }, options.timeoutMs || CHAT_TIMEOUT_MS)
}

export function uploadAiAttachment(file) {
  const form = new FormData()
  form.append('file', file)
  return request(`${BASE}/attachments`, {
    method: 'POST',
    body: form,
  }, CHAT_TIMEOUT_MS)
}

export function confirmAiAction(id) {
  return request(`${BASE}/actions/${id}/confirm`, { method: 'POST' })
}

export function executeAiAction(id, confirmToken) {
  return request(`${BASE}/actions/${id}/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirm_token: confirmToken }),
  })
}

// 拒绝待确认操作：pending/confirmed（未执行）→ rejected，终态。返回更新后的 action。
export function rejectAiAction(id) {
  return request(`${BASE}/actions/${id}/reject`, { method: 'POST' })
}

// 确认/拒绝后回灌续跑：若该会话有待续跑的 checkpoint 且全部 pending 已结案则续跑，
// 否则返回 {resumed:false, waiting:N}（前端静默处理）。
export function resumeAiChat(conversationId) {
  return request(`${BASE}/chat/resume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversation_id: conversationId }),
  }, CHAT_TIMEOUT_MS)
}

// ---- 阶段 C1：Plan Mode 批准/拒绝 ----
export function approveAiPlan(messageId, steps = null) {
  return request(`${BASE}/plan/${messageId}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(steps ? { steps } : {}),
  }, CHAT_TIMEOUT_MS)
}

// ---- 阶段 D1：工具「始终允许」授权管理 ----
export function listAiGrants() {
  return request(`${BASE}/grants`)
}

export function createAiGrant(toolName, argPattern = '') {
  return request(`${BASE}/grants`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tool_name: toolName, arg_pattern: argPattern }),
  })
}

export function deleteAiGrant(grantId) {
  return request(`${BASE}/grants/${grantId}`, { method: 'DELETE' })
}

// 阶段 FU-2.1：批准计划流式版（与 streamAiChat 同 SSE 协议）
export async function streamAiApprovePlan(messageId, steps = null, { signal, onEvent } = {}) {
  const res = await fetch(`${BASE}/plan/${messageId}/approve/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(steps ? { steps } : {}),
    signal,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    let detail = text
    try { detail = extractErrorMessage(JSON.parse(text)) } catch { /* keep raw */ }
    const safeDetail = compactErrorMessage(detail)
    throw new Error(safeDetail ? `请求失败 (${res.status})：${safeDetail}` : `请求失败 (${res.status})`)
  }
  await consumeSseStream(res, onEvent, signal)
}

export function rejectAiPlan(messageId, reason = '') {
  return request(`${BASE}/plan/${messageId}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(reason ? { reason } : {}),
  })
}

// ---- SSE 流式（阶段 4）----
// fetch POST + ReadableStream 消费；按 \n\n 分帧解析 SSE，回调 onEvent(event, data)。
// 不走 180s 总超时封装（流式可长时运行），用外部 signal 控制取消。
// 解析失败或网络断开时抛错（含 abort 检测）。
export async function streamAiChat(payload, { signal, onEvent } = {}) {
  const res = await fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    let detail = text
    try { detail = extractErrorMessage(JSON.parse(text)) } catch { /* keep raw */ }
    const safeDetail = compactErrorMessage(detail)
    throw new Error(safeDetail ? `请求失败 (${res.status})：${safeDetail}` : `请求失败 (${res.status})`)
  }
  await consumeSseStream(res, onEvent, signal)
}

export async function streamAiResume(conversationId, { signal, onEvent } = {}) {
  const res = await fetch(`${BASE}/chat/resume/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversation_id: conversationId }),
    signal,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    let detail = text
    try { detail = extractErrorMessage(JSON.parse(text)) } catch { /* keep raw */ }
    const safeDetail = compactErrorMessage(detail)
    throw new Error(safeDetail ? `请求失败 (${res.status})：${safeDetail}` : `请求失败 (${res.status})`)
  }
  await consumeSseStream(res, onEvent, signal)
}

// 中断进行中的流式 agent run（阶段 5）：set 后端对应 run_id 的取消事件。
// 幂等：未知 run_id 返回 ok:false（前端停止按钮无脑调即可）。
export function cancelAiChat(runId) {
  return request(`${BASE}/chat/cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_id: runId }),
  }, DEFAULT_TIMEOUT_MS)
}

// 内部：从 ReadableStream 消费 SSE 帧，按空行分帧，解析 event:/data: 行。
async function consumeSseStream(res, onEvent, signal) {
  if (!res.body) throw new Error('浏览器不支持流式响应')
  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let currentEvent = ''
  let dataLines = []
  const dispatch = () => {
    if (!dataLines.length) return
    const dataStr = dataLines.join('\n')
    dataLines = []
    let parsed = {}
    try { parsed = JSON.parse(dataStr) } catch { parsed = { raw: dataStr } }
    const eventName = currentEvent || 'message'
    currentEvent = ''
    if (onEvent) onEvent(eventName, parsed)
  }
  try {
    while (true) {
      if (signal?.aborted) {
        try { await reader.cancel() } catch { /* ignore */ }
        throw new DOMException('Aborted', 'AbortError')
      }
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let idx
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        for (const line of frame.split('\n')) {
          if (line.startsWith(':')) continue // comment
          if (line.startsWith('event:')) {
            currentEvent = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            dataLines.push(line.slice(5).replace(/^ /, ''))
          }
        }
        dispatch()
      }
    }
    // flush 尾部
    buffer += decoder.decode()
    if (buffer.trim()) {
      for (const line of buffer.split('\n')) {
        if (line.startsWith(':')) continue
        if (line.startsWith('event:')) currentEvent = line.slice(6).trim()
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^ /, ''))
      }
      dispatch()
    }
  } finally {
    try { reader.releaseLock() } catch { /* ignore */ }
  }
}

// ---- 每日晨报（幕僚线）----
// 当天幂等；有 AI 配置时可能触发一次模型生成，故放宽到对话级超时。
// 前端只在用户开启「每日晨报」开关后自动调用。
export function getTodayBriefing() {
  return request(`${BASE}/briefing/today`, {}, CHAT_TIMEOUT_MS)
}

// ---- AI 日报/周报 ----
const DEFAULT_REPORT_TIMEOUT_MS = 180000

export function generateReport(payload, timeoutMs = DEFAULT_REPORT_TIMEOUT_MS) {
  return request(`${BASE}/reports/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }, timeoutMs)
}

export function listReports(reportType) {
  const qs = reportType ? `?report_type=${encodeURIComponent(reportType)}` : ''
  return request(`${BASE}/reports${qs}`)
}

export function getReport(id) {
  return request(`${BASE}/reports/${id}`)
}

export function deleteReport(id) {
  return request(`${BASE}/reports/${id}`, { method: 'DELETE' })
}

// ---- AI 深度融合：内嵌动作 / 秘书自动档 ----
// 以下接口都可能触发模型调用，统一放宽到对话级超时。

// 任务一键 AI 拆解子任务；409 = 已有子任务，403 = 内嵌动作被关闭，400 = 未配置 AI
export function breakdownSubtasks(taskId) {
  return request(`${BASE}/actions/breakdown-subtasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task_id: taskId }),
  }, CHAT_TIMEOUT_MS)
}

// 任务一键 AI 排程；date 给了则直接排程（无需 AI），缺省由 AI 选日
export function scheduleTaskAi(taskId, date) {
  const body = { task_id: taskId }
  if (date) body.date = date
  return request(`${BASE}/actions/schedule-task`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }, CHAT_TIMEOUT_MS)
}

// 日记草稿（不落库）；date 缺省为今天。source: "ai" | "rule"（无 AI 配置时规则模板兜底）
export function journalDraft(date) {
  return request(`${BASE}/actions/journal-draft`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(date ? { date } : {}),
  }, CHAT_TIMEOUT_MS)
}

// 番茄钟收束语：按 TimeLog id 生成一句话小结
export function timerSignoff(logId) {
  return request(`${BASE}/actions/timer-signoff`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ log_id: logId }),
  }, CHAT_TIMEOUT_MS)
}

// 秘书自动档：当天幂等，主动排程 + 拆解任务。403 = 自动档未开启
export function runAutopilot() {
  return request(`${BASE}/autopilot/run`, { method: 'POST' }, CHAT_TIMEOUT_MS)
}
