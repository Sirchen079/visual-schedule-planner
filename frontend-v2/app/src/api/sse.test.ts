import { describe, expect, it } from 'vitest'
import { SSEFrameParser, SSEProtocolError, parseSSEEvent, responseError } from './sse'
import type { SSEEvent } from './contracts/events'

/** 模拟流式喂入：按 chunks 切分喂给解析器，最后 flush。 */
function feed(chunks: string[]): { frames: ReturnType<SSEFrameParser['push']>; parser: SSEFrameParser } {
  const parser = new SSEFrameParser()
  const frames = chunks.flatMap((c) => parser.push(c)).concat(parser.flush())
  return { frames, parser }
}

/** 按 n 字符一片切分字符串，构造跨 chunk 断帧场景。 */
function splitEvery(s: string, n: number): string[] {
  const out: string[] = []
  for (let i = 0; i < s.length; i += n) out.push(s.slice(i, i + n))
  return out
}

const frameA = 'event: run_started\ndata: {"v":1,"type":"run_started","run_id":"r1","conversation_id":7}\n\n'
const frameB = 'event: text_delta\ndata: {"v":1,"type":"text_delta","delta":"你好"}\n\n'
const frameC = 'event: done\ndata: {"v":1,"type":"done","run_id":"r1"}\n\n'

describe('SSEFrameParser', () => {
  it('单 chunk 单帧', () => {
    const { frames } = feed([frameA])
    expect(frames).toEqual([{ event: 'run_started', data: '{"v":1,"type":"run_started","run_id":"r1","conversation_id":7}' }])
  })

  it('多帧粘连在同一 chunk', () => {
    const { frames } = feed([frameA + frameB + frameC])
    expect(frames.map((f) => f.event)).toEqual(['run_started', 'text_delta', 'done'])
  })

  it('跨 chunk 断帧：每 7 字符切一刀，仍解析出完整帧', () => {
    const raw = frameA + frameB + frameC
    const { frames } = feed(splitEvery(raw, 7))
    expect(frames.map((f) => f.event)).toEqual(['run_started', 'text_delta', 'done'])
    expect(JSON.parse(frames[1].data)).toMatchObject({ type: 'text_delta', delta: '你好' })
  })

  it('跨 chunk 断帧：在 event: 行中间与 data JSON 中间切断', () => {
    const raw = frameA + frameB + frameC
    const cut1 = frameA.indexOf('run_started') + 4 // event 名中间
    const cut2 = frameA.length + 20 // 下一帧的 data JSON 中间
    const { frames } = feed([raw.slice(0, cut1), raw.slice(cut1, cut2), raw.slice(cut2)])
    expect(frames.map((f) => f.event)).toEqual(['run_started', 'text_delta', 'done'])
  })

  it('兼容 \\r\\n 换行', () => {
    const { frames } = feed([frameA.replace(/\n/g, '\r\n')])
    expect(frames).toHaveLength(1)
    expect(frames[0].event).toBe('run_started')
  })

  it('忽略 : 注释行（keepalive）', () => {
    const raw = ': ping\n\n' + frameB
    const { frames } = feed([raw])
    expect(frames).toEqual([{ event: 'text_delta', data: '{"v":1,"type":"text_delta","delta":"你好"}' }])
  })

  it('flush 兜底：流结束时最后一帧没有终止空行', () => {
    const { frames } = feed([frameA, 'event: done\ndata: {"v":1,"type":"done","run_id":"r1"}'])
    expect(frames.map((f) => f.event)).toEqual(['run_started', 'done'])
  })

  it('连续多个空行不产生空帧', () => {
    const { frames } = feed([frameA + '\n\n\n'])
    expect(frames).toHaveLength(1)
  })

  it('event 后无 data 的帧被忽略，且不污染下一帧的 event 名', () => {
    const raw = 'event: ghost\n\ndata: {"v":1,"type":"done","run_id":"r1"}\n\n'
    const { frames } = feed([raw])
    expect(frames).toHaveLength(1)
    expect(frames[0].event).toBe('message') // 无 event: 行 → 默认 message
    expect(frames[0].data).toContain('done')
  })

  it('跨 chunk 的多字节 UTF-8 字符（经 TextDecoder stream 模式）', () => {
    const bytes = new TextEncoder().encode(frameB)
    const decoder = new TextDecoder('utf-8')
    const parser = new SSEFrameParser()
    // 3 字节 UTF-8「你」被从中间切开
    const frames = [bytes.slice(0, 30), bytes.slice(30, 45), bytes.slice(45)]
      .flatMap((b) => parser.push(decoder.decode(b, { stream: true })))
      .concat(parser.flush())
    const ev = parseSSEEvent(frames[0])
    expect(ev).toMatchObject({ type: 'text_delta', delta: '你好' })
  })
})

describe('parseSSEEvent', () => {
  it('按 type 收窄为 SSEEvent 判别联合', () => {
    const ev = parseSSEEvent({ event: 'tool_call_started', data: '{"v":1,"type":"tool_call_started","call_id":"c1","tool":"t","args_preview":"{}"}' })
    if (ev.type !== 'tool_call_started') throw new Error('未收窄到 tool_call_started')
    expect(ev.call_id).toBe('c1')
    expect(ev.tool).toBe('t')
  })

  it('data 非法 JSON → SSEProtocolError', () => {
    expect(() => parseSSEEvent({ event: 'text_delta', data: '{oops' })).toThrow(SSEProtocolError)
  })

  it('data 缺 type 字段 → SSEProtocolError', () => {
    expect(() => parseSSEEvent({ event: 'x', data: '{"v":1}' })).toThrow(SSEProtocolError)
  })

  it('整段事件流解析冒烟：19 联合的 6 种典型事件逐一通过', () => {
    const events: SSEEvent[] = [
      { v: 1, type: 'run_started', run_id: 'r', conversation_id: 1 },
      { v: 1, type: 'stage_changed', stage: 'streaming_text' },
      { v: 1, type: 'heartbeat', elapsed_ms: 5000, stage: 'streaming_text', last_event_age_ms: 100 },
      { v: 1, type: 'usage_updated', tokens_in: 1, tokens_out: 2, cost_estimate: 0, model: 'm' },
      { v: 1, type: 'run_error', run_id: 'r', message: 'x', retryable: false },
      { v: 1, type: 'done', run_id: 'r' },
    ]
    for (const ev of events) {
      const frame = { event: ev.type, data: JSON.stringify(ev) }
      expect(parseSSEEvent(frame).type).toBe(ev.type)
    }
  })
})

describe('responseError（非 2xx 响应体 → 可读消息 + 原样错误体）', () => {
  it('typed 拒绝体（ResumeBlockedOut）：默认消息 + body 原样携带供上层解读', () => {
    const body = { pending: [{ action_id: 20, tool_name: 'create_event' }], consumed: false, message: '' }
    const out = responseError(400, body)
    expect(out.message).toBe('请求失败（HTTP 400）') // 顶层无 detail 字符串，不误读
    expect(out.body).toBe(body)
  })

  it('detail 字符串（FastAPI HTTPException）→ 取为可读消息', () => {
    expect(responseError(404, { detail: '审批不存在或已结案' }).message).toBe('审批不存在或已结案')
  })

  it('非 JSON / 非对象体 → 默认消息，body 为 undefined', () => {
    expect(responseError(500, undefined).message).toBe('请求失败（HTTP 500）')
    expect(responseError(502, 'Bad Gateway').message).toBe('请求失败（HTTP 502）')
  })
})
