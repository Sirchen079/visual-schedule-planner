/**
 * REST fetch 封装。
 * - baseURL 同源：dev 走 Vite 代理（localhost:5173 → 127.0.0.1:8421，绕 OriginGuard 必须同源）；
 *   生产由后端 SPA 托管，天然同源。因此这里直接用相对路径。
 * - JSON 编解码。
 * - 错误规整为 {status, message}（HttpError），message 优先取后端 detail/message。
 */

export interface ApiErrorBody {
  status: number
  message: string
}

export class HttpError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'HttpError'
    this.status = status
  }

  toBody(): ApiErrorBody {
    return { status: this.status, message: this.message }
  }
}

export type QueryValue = string | number | boolean | undefined | null

export interface HttpOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  query?: Record<string, QueryValue>
  body?: unknown
  signal?: AbortSignal
}

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  let url = path
  if (query) {
    const qs = Object.entries(query)
      .filter(([, v]) => v !== undefined && v !== null)
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
      .join('&')
    if (qs) url += (url.includes('?') ? '&' : '?') + qs
  }
  return url
}

/** 从 FastAPI 风格错误响应里提取可读消息。 */
async function normalizeError(res: Response): Promise<HttpError> {
  let message = `请求失败（HTTP ${res.status}）`
  try {
    const data: unknown = await res.json()
    if (data && typeof data === 'object') {
      const d = data as Record<string, unknown>
      if (typeof d.detail === 'string') message = d.detail
      else if (Array.isArray(d.detail)) {
        // 422 校验错误：detail 是 [{loc, msg, type}, ...]
        message = d.detail
          .map((item) => (item && typeof item === 'object' && 'msg' in item ? String(item.msg) : JSON.stringify(item)))
          .join('; ')
      } else if (typeof d.message === 'string') message = d.message
    }
  } catch {
    // 错误体不是 JSON，保留默认消息
  }
  return new HttpError(res.status, message)
}

export async function request<T>(path: string, opts: HttpOptions = {}): Promise<T> {
  let res: Response
  try {
    res = await fetch(buildUrl(path, opts.query), {
      method: opts.method ?? 'GET',
      headers: opts.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
    })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    throw new HttpError(0, '网络错误：无法连接本地服务（127.0.0.1:8421）')
  }
  if (!res.ok) throw await normalizeError(res)
  if (res.status === 204) return undefined as T
  const text = await res.text()
  if (!text) return undefined as T
  return JSON.parse(text) as T
}

export const http = {
  get<T>(path: string, query?: Record<string, QueryValue>): Promise<T> {
    return request<T>(path, { query })
  },
  post<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, { method: 'POST', body })
  },
  patch<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, { method: 'PATCH', body })
  },
  put<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, { method: 'PUT', body })
  },
  del<T>(path: string): Promise<T> {
    return request<T>(path, { method: 'DELETE' })
  },
}
