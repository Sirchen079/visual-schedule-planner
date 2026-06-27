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
