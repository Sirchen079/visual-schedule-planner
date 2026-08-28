// MCP 服务器配置 API。相对路径 /mcp：dev 经 Vite proxy，prod 同源走后端。
const BASE = '/mcp'
const DEFAULT_TIMEOUT_MS = 45000
const TEST_TIMEOUT_MS = 60000

function redactErrorText(value) {
  return String(value ?? '')
    .replace(/(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s,;"'}]+/gi, '$1[已隐藏]')
    .replace(/(x-api-key\s*[:=]\s*)[^\s,;"'}]+/gi, '$1[已隐藏]')
    .replace(/((?:api[_-]?key|token|secret|password)["']?\s*[:=]\s*["']?)[^"',\s}]+/gi, '$1[已隐藏]')
    .replace(/\b(sk|ak|pk)-[A-Za-z0-9_-]{12,}\b/g, '$1-[已隐藏]')
}

function compactErrorMessage(value) {
  const text = redactErrorText(value).replace(/\s+/g, ' ').trim()
  if (!text) return ''
  return text.length > 260 ? `${text.slice(0, 260)}...` : text
}

function extractErrorMessage(payload) {
  if (!payload) return ''
  if (typeof payload === 'string') return payload
  if (Array.isArray(payload)) {
    return payload.map(extractErrorMessage).filter(Boolean).join('；')
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
  const timeoutId = window.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)

  return fetch(path, { ...options, signal: controller.signal })
    .then(parse)
    .catch((err) => {
      if (timedOut) throw new Error('请求超时，请稍后重试')
      if (err?.name === 'AbortError') throw new Error('请求已取消')
      if (err instanceof TypeError) throw new Error('网络请求失败，请检查后端服务是否可用')
      if (err instanceof Error) throw new Error(compactErrorMessage(err.message) || '操作失败')
      throw new Error('操作失败')
    })
    .finally(() => window.clearTimeout(timeoutId))
}

function jsonBody(method, payload) {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }
}

export function listMcpServers() {
  return request(`${BASE}/servers`)
}

export function createMcpServer(payload) {
  return request(`${BASE}/servers`, jsonBody('POST', payload))
}

export function updateMcpServer(id, payload) {
  return request(`${BASE}/servers/${id}`, jsonBody('PUT', payload))
}

export function deleteMcpServer(id) {
  return request(`${BASE}/servers/${id}`, { method: 'DELETE' })
}

// body: { enabled: boolean }
export function enableMcpServer(id, enabled) {
  return request(`${BASE}/servers/${id}/enable`, jsonBody('POST', { enabled }))
}

export function testMcpServer(id) {
  return request(`${BASE}/servers/${id}/test`, { method: 'POST' }, TEST_TIMEOUT_MS)
}

export function listMcpTools(id) {
  return request(`${BASE}/servers/${id}/tools`, {}, TEST_TIMEOUT_MS)
}
