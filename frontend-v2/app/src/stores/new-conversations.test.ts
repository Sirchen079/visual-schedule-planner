import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useConversationStore } from './conversation'
import { useRunStore } from './run'
import { buildTimeline } from '../components/chat/timeline'

const msg = (id: number, text: string) => ({ id, role: 'user', display: { text }, created_at: '2032-01-01T10:00:00' })
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
function stream(cid: number, text = '新回复') {
  const events = [{ v: 1, type: 'run_started', run_id: `r${cid}`, conversation_id: cid },
    { v: 1, type: 'text_delta', delta: text }, { v: 1, type: 'done', run_id: `r${cid}` }]
  return new Response(events.map(e => `data: ${JSON.stringify(e)}\n\n`).join(''), { headers: { 'Content-Type': 'text/event-stream' } })
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
beforeEach(() => setActivePinia(createPinia()))
afterEach(() => vi.unstubAllGlobals())

describe('new conversation boundaries', () => {
  it('clears the old run and sends null, then continues with the server-created id and keeps earlier turns', async () => {
    const bodies: any[] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/ai/chat/stream') { bodies.push(JSON.parse(String(init?.body))); return stream(8) }
      if (url === '/ai/conversations/8') return json([msg(80, '本会话第一条')])
      return json([])
    }))
    const conv = useConversationStore(), run = useRunStore()
    conv.activeId = 7
    conv.messages = [msg(7, '旧对话秘密')]
    conv.draftAttachments = [{ id: 99, name: '旧附件' }]
    conv.sentEchoAttachments = [{ id: 98, name: '旧回显' }]
    run.conversationId = 7
    run.segments = [{ kind: 'text', seq: 1, content: '旧回复' }]
    conv.startNew()
    expect(conv.activeId).toBeNull()
    expect(run.conversationId).toBeNull()
    expect(run.segments).toEqual([])
    expect(conv.messages).toEqual([])
    expect(conv.attachmentIds).toEqual([])
    expect(conv.sentEchoAttachments).toEqual([])
    await conv.sendMessage('本会话第一条')
    expect(bodies[0].conversation_id).toBeNull()
    expect(bodies[0].attachment_ids).toEqual([])
    expect(conv.activeId).toBe(8)
    await conv.sendMessage('继续当前会话')
    expect(bodies[1].conversation_id).toBe(8)
    expect(conv.messages).toEqual([msg(80, '本会话第一条')])
    expect(buildTimeline({ messages: conv.messages, run, activeConversationId: conv.activeId })).toHaveLength(3)
    expect(JSON.stringify(conv.messages)).not.toContain('旧对话秘密')
  })

  it('explicit null overrides stale run identity; an omitted identity preserves intentional continuation', async () => {
    const bodies: any[] = []
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => {
      bodies.push(JSON.parse(String(init?.body)))
      return stream(10)
    }))
    const run = useRunStore()
    run.conversationId = 9
    await run.sendMessage('新消息', { conversationId: null })
    expect(bodies[0].conversation_id).toBeNull()
    await run.sendMessage('继续')
    expect(bodies[1].conversation_id).toBe(10)
  })

  it('ignores old history and errors after starting new, including a switch away and back', async () => {
    const first = deferred<Response>(), second = deferred<Response>()
    let requests = 0
    vi.stubGlobal('fetch', vi.fn(() => (++requests === 1 ? first : second).promise))
    const conv = useConversationStore()
    const old = conv.select(7)
    conv.startNew()
    const current = conv.select(7)
    second.resolve(json([msg(8, '当前记录')]))
    await current
    first.resolve(json([msg(1, '过期记录')]))
    await old
    expect(conv.messages).toEqual([msg(8, '当前记录')])
    const pending = deferred<Response>()
    vi.stubGlobal('fetch', vi.fn(() => pending.promise))
    const loading = conv.select(8)
    conv.startNew()
    pending.resolve(json({ detail: '旧请求失败' }, 500))
    await loading
    expect(conv.messages).toEqual([])
    expect(conv.error).toBeNull()
    expect(conv.loading).toBe(false)
  })

  it('discards an attachment that finishes after new while keeping the new upload in progress', async () => {
    const first = deferred<Response>(), second = deferred<Response>()
    let requests = 0
    vi.stubGlobal('fetch', vi.fn(() => (++requests === 1 ? first : second).promise))
    const conv = useConversationStore()
    const old = conv.uploadAttachment(new File(['old'], 'old.txt'))
    conv.startNew()
    const fresh = conv.uploadAttachment(new File(['new'], 'new.txt'))
    first.resolve(json({ file_id: 1, name: 'old.txt' }))
    await old
    expect(conv.draftAttachments).toEqual([])
    expect(conv.uploading).toBe(true)
    second.resolve(json({ file_id: 2, name: 'new.txt' }))
    await fresh
    expect(conv.draftAttachments).toEqual([{ id: 2, name: 'new.txt' }])
    expect(conv.uploading).toBe(false)
  })

  it('switches away from completed live output without mixing it into another conversation', async () => {
    const run = useRunStore(), conv = useConversationStore()
    run.conversationId = 7
    run.sentMessage = '不属于另一会话'
    run.segments = [{ kind: 'text', seq: 1, content: '旧回复' }]
    expect(buildTimeline({ messages: [msg(8, '另一会话')], run, activeConversationId: 8 })).toHaveLength(1)
    vi.stubGlobal('fetch', vi.fn(async () => json([msg(8, '另一会话')])))
    await conv.select(8)
    expect(run.conversationId).toBe(8)
    expect(run.segments).toEqual([])
    expect(run.sentMessage).toBeNull()
  })

  it('blocks duplicate sends and new while the first stream is still connecting', async () => {
    const connection = deferred<Response>()
    const fetchMock = vi.fn(() => connection.promise)
    vi.stubGlobal('fetch', fetchMock)
    const run = useRunStore(), conv = useConversationStore()
    const first = run.sendMessage('第一条', { conversationId: null })
    expect(run.isActive).toBe(true)
    const version = conv.viewVersion
    conv.startNew()
    expect(conv.viewVersion).toBe(version)
    await run.sendMessage('重复消息')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    connection.resolve(stream(8))
    await first
    expect(run.isActive).toBe(false)
  })

  it('cancel during connection remains cancelled and clears the connection lock', async () => {
    vi.stubGlobal('fetch', vi.fn((_url: string, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => reject(new DOMException('cancelled', 'AbortError')))
    })))
    const run = useRunStore()
    const waiting = run.sendMessage('取消这次请求')
    await run.cancel()
    await waiting
    expect(run.phase).toBe('cancelled')
    expect(run.isActive).toBe(false)
    expect(run.error).toBeNull()
  })
})
