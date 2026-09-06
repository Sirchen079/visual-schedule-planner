/**
 * POST SSE 客户端（EventSource 不支持 POST，故用 fetch + ReadableStream 自封装）。
 *
 * 后端帧格式（FRONTEND_HANDBOOK §4）：`event: <type>\ndata: <json>\n\n`
 * - SSEFrameParser：纯字符串增量解析器，跨 chunk 断帧安全、支持多帧粘连、
 *   兼容 \r\n 与 \r 换行、忽略 `:` 注释行、flush 兜底无终止空行的最后一帧。
 * - parseSSEEvent：data JSON → events.d.ts 的 SSEEvent 判别联合（按 type 收窄）。
 * - streamSSE：回调式（onEvent/onError/onClose），支持 AbortController 取消。
 */
import type { SSEEvent } from './contracts/events'

export interface SSEFrame {
  event: string
  data: string
}

/** 协议层错误：帧不完整到无法恢复、data 非法 JSON、缺 type 字段等。 */
export class SSEProtocolError extends Error {
  constructor(
    message: string,
    readonly raw?: string,
  ) {
    super(message)
    this.name = 'SSEProtocolError'
  }
}

export class SSERequestError extends Error {
  constructor(
    readonly status: number,
    message: string,
    /** 非 2xx 响应的 JSON 错误体原文（typed 拒绝体如 ResumeBlockedOut 原样携带，供上层解读）。 */
    readonly body?: unknown,
  ) {
    super(message)
    this.name = 'SSERequestError'
  }
}

/** 非 2xx 响应体 → 可读消息 + 原样错误体。纯函数便于单测。 */
export function responseError(status: number, data: unknown): { message: string; body: unknown } {
  let message = `请求失败（HTTP ${status}）`
  if (data && typeof data === 'object') {
    const d = data as { detail?: unknown }
    if (typeof d.detail === 'string') message = d.detail
  }
  return { message, body: data }
}

export class SSEFrameParser {
  private buffer = ''
  private dataLines: string[] = []
  private eventName = ''

  /** 喂入一个文本 chunk，返回其中已完整终止的帧。 */
  push(chunk: string): SSEFrame[] {
    this.buffer += chunk
    const frames: SSEFrame[] = []
    let idx: number
    while ((idx = this.buffer.indexOf('\n')) >= 0) {
      const line = this.buffer.slice(0, idx).replace(/\r$/, '')
      this.buffer = this.buffer.slice(idx + 1)
      this.handleLine(line, frames)
    }
    return frames
  }

  /** 流结束时调用：处理残留的半行与未终止的最后一帧。 */
  flush(): SSEFrame[] {
    const frames: SSEFrame[] = []
    if (this.buffer) {
      const line = this.buffer.replace(/\r$/, '')
      this.buffer = ''
      this.handleLine(line, frames)
    }
    if (this.dataLines.length) frames.push(this.takeFrame())
    return frames
  }

  private handleLine(line: string, out: SSEFrame[]): void {
    if (line === '') {
      // 空行 = 帧边界。有 data 才成帧；没有则按 SSE 规范重置 event 缓冲。
      if (this.dataLines.length) out.push(this.takeFrame())
      else this.eventName = ''
      return
    }
    if (line.startsWith(':')) return // 注释/心跳 keepalive 行
    const colon = line.indexOf(':')
    const field = colon < 0 ? line : line.slice(0, colon)
    let value = colon < 0 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') this.eventName = value
    else if (field === 'data') this.dataLines.push(value)
    // id/retry 等字段本协议不使用，忽略
  }

  private takeFrame(): SSEFrame {
    const frame = { event: this.eventName || 'message', data: this.dataLines.join('\n') }
    this.eventName = ''
    this.dataLines = []
    return frame
  }
}

/** data JSON → SSEEvent 判别联合。以 data.type 为权威；event: 行仅作参考。 */
export function parseSSEEvent(frame: SSEFrame): SSEEvent {
  let payload: unknown
  try {
    payload = JSON.parse(frame.data)
  } catch {
    throw new SSEProtocolError(`SSE data 不是合法 JSON（event=${frame.event}）`, frame.data)
  }
  if (typeof payload !== 'object' || payload === null || typeof (payload as { type?: unknown }).type !== 'string') {
    throw new SSEProtocolError('SSE data 缺少 type 字段，无法收窄为 SSEEvent', frame.data)
  }
  return payload as SSEEvent
}

export interface SSEStreamInit {
  method?: 'GET' | 'POST'
  body?: unknown
  signal?: AbortSignal
}

export interface SSEStreamHandlers {
  onEvent: (ev: SSEEvent) => void
  /** 请求失败（非 2xx / 网络不通 / 流内协议错误）。主动取消不会触发。 */
  onError: (err: SSERequestError) => void
  /** 网络层流结束（无论是否收到 done）。主动取消也会走到这里。 */
  onClose: (info: { gotDoneEvent: boolean }) => void
}

function isAbort(e: unknown): boolean {
  return e instanceof DOMException && e.name === 'AbortError'
}

/**
 * 打开一条 SSE 流并持续消费到结束。
 * 约定：done 是唯一权威终点；gotDoneEvent=false 的正常关闭属于异常中断，由上层 run 状态机裁决。
 */
export async function streamSSE(url: string, init: SSEStreamInit, h: SSEStreamHandlers): Promise<void> {
  let res: Response
  try {
    res = await fetch(url, {
      method: init.method ?? 'POST',
      headers: {
        Accept: 'text/event-stream',
        ...(init.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      },
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
      signal: init.signal,
    })
  } catch (e) {
    if (isAbort(e)) {
      h.onClose({ gotDoneEvent: false })
      return
    }
    h.onError(new SSERequestError(0, '网络错误：无法连接本地服务（127.0.0.1:8421）'))
    return
  }

  if (!res.ok) {
    let data: unknown
    try {
      data = await res.json()
    } catch {
      // 非 JSON 错误体
    }
    const { message, body } = responseError(res.status, data)
    h.onError(new SSERequestError(res.status, message, body))
    return
  }
  if (!res.body) {
    h.onError(new SSERequestError(res.status, '响应缺少正文流，无法按 SSE 消费'))
    return
  }

  const parser = new SSEFrameParser()
  // stream:true 让跨 chunk 截断的多字节 UTF-8 字符正确解码
  const decoder = new TextDecoder('utf-8')
  const reader = res.body.getReader()
  let gotDone = false

  const dispatch = (frames: SSEFrame[]): void => {
    for (const frame of frames) {
      const ev = parseSSEEvent(frame)
      if (ev.type === 'done') gotDone = true
      h.onEvent(ev)
    }
  }

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      dispatch(parser.push(decoder.decode(value, { stream: true })))
    }
    dispatch(parser.push(decoder.decode()))
    dispatch(parser.flush())
  } catch (e) {
    if (isAbort(e)) {
      h.onClose({ gotDoneEvent: gotDone })
      return
    }
    h.onError(new SSERequestError(-1, e instanceof Error ? e.message : String(e)))
    return
  }
  h.onClose({ gotDoneEvent: gotDone })
}
