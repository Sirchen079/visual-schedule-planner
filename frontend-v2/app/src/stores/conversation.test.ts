import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useConversationStore } from './conversation'
import { useRunStore } from './run'

/** http.ts 走全局 fetch（同源相对路径），node 测试环境下用 stub 模拟后端响应。 */
function jsonResponse(payload: unknown, status = 200): Response {
  const text = JSON.stringify(payload)
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => text,
    json: async () => JSON.parse(text),
  } as unknown as Response
}

const CONV_LIST = [
  { id: 1, title: '导入课表', updated_at: '2026-09-04T12:55:16' },
  { id: 2, title: '安排周五回顾', updated_at: '2026-09-04T10:00:00' },
]

const CONV_1_MESSAGES = [
  {
    id: 1,
    role: 'user',
    display: { text: '导入课表', attachments: [{ id: 7, name: '课表.docx' }] },
    created_at: '2026-09-04T12:00:00',
  },
  { id: 2, role: 'assistant', display: { text: '完成，17 条课程已建。' }, created_at: '2026-09-04T12:00:30' },
]

describe('conversation store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('keeps brainstorming choices per conversation and restores the last sent mode', () => {
    const conv = useConversationStore()
    expect(conv.activeBrainstormMode).toBe(false)
    conv.activeId = 1
    conv.messages = [{ id: 1, role: 'user', display: { text: '梳理需求', brainstorm_mode: true }, created_at: '' }]
    expect(conv.activeBrainstormMode).toBe(true)
    conv.setBrainstormMode(false)
    expect(conv.activeBrainstormMode).toBe(false)
    conv.activeId = 2
    conv.messages = []
    expect(conv.activeBrainstormMode).toBe(false)
    conv.setBrainstormMode(true)
    conv.activeId = 1
    expect(conv.activeBrainstormMode).toBe(false)
    conv.activeId = 2
    expect(conv.activeBrainstormMode).toBe(true)
  })

  it('refresh 拉取会话列表；select 加载历史并落活跃指针', async () => {
    const calls: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string | URL | Request) => {
        calls.push(String(url))
        if (String(url) === '/ai/conversations') return jsonResponse(CONV_LIST)
        return jsonResponse(CONV_1_MESSAGES)
      }),
    )
    try {
      const conv = useConversationStore()
      await conv.refresh()
      expect(conv.conversations).toHaveLength(2)

      await conv.select(1)
      expect(conv.activeId).toBe(1)
      expect(conv.messages).toHaveLength(2)
      expect(conv.activeTitle).toBe('导入课表')
      expect(calls.filter((c) => c === '/ai/conversations/1')).toHaveLength(1)
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('startNew 清空活跃指针；attachFromRun 在 run_started 回填新会话并刷新列表', async () => {
    const fetchMock = vi.fn(async (url: string | URL | Request) => {
      if (String(url) === '/ai/conversations') return jsonResponse(CONV_LIST)
      return jsonResponse([])
    })
    vi.stubGlobal('fetch', fetchMock)
    try {
      const conv = useConversationStore()
      conv.activeId = 2
      conv.messages = CONV_1_MESSAGES as never
      conv.startNew()
      expect(conv.activeId).toBeNull()
      expect(conv.messages).toHaveLength(0)
      expect(conv.activeTitle).toBe('新对话')

      conv.attachFromRun(11)
      expect(conv.activeId).toBe(11)
      expect(fetchMock).toHaveBeenCalledWith('/ai/conversations', expect.anything()) // 触发列表刷新
      // 刷新完成前列表里还没有 11 → 标题回退「会话 11」
      expect(conv.activeTitle).toBe('会话 11')
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('select 时若该会话的 run 已终态 → 重置 run store 防止时间线重复；活跃 run 不动', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(CONV_1_MESSAGES)),
    )
    try {
      const conv = useConversationStore()
      const run = useRunStore()
      // 模拟一轮已完成的 run（有残留 live 内容）
      run.consume({ v: 1, type: 'run_started', run_id: 'r1', conversation_id: 1 })
      run.consume({ v: 1, type: 'text_delta', delta: '回答' })
      run.consume({ v: 1, type: 'done', run_id: 'r1' })
      expect(run.phase).toBe('completed')

      await conv.select(1)
      expect(run.segments).toHaveLength(0) // 已重置
      expect(run.conversationId).toBe(1) // reset 保留 conversationId

      // 活跃 run：select 同会话不清内容
      run.consume({ v: 1, type: 'run_started', run_id: 'r2', conversation_id: 1 })
      run.consume({ v: 1, type: 'text_delta', delta: '正在回答' })
      await conv.select(1)
      expect(run.segments).toHaveLength(1)
      expect(run.phase).toBe('streaming')
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('startNew 在 run 活跃时拒绝（同会话单 run，避免孤儿流）', () => {
    const conv = useConversationStore()
    const run = useRunStore()
    conv.activeId = 2
    run.consume({ v: 1, type: 'run_started', run_id: 'r9', conversation_id: 2 })
    conv.startNew()
    expect(conv.activeId).toBe(2)
  })

  it('附件草稿：上传成功入列、可移除；上传失败记录 error 不入列', async () => {
    let fail = false
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        if (fail) return jsonResponse({ detail: '文件类型不支持' }, 422)
        return jsonResponse({ file_id: 33, name: 'a.pdf', kind: 'pdf', parse_status: 'parsed' })
      }),
    )
    try {
      const conv = useConversationStore()
      await conv.uploadAttachment(new File(['x'], 'a.pdf', { type: 'application/pdf' }))
      expect(conv.draftAttachments).toEqual([{ id: 33, name: 'a.pdf' }])
      expect(conv.attachmentIds).toEqual([33])

      conv.removeAttachment(33)
      expect(conv.draftAttachments).toHaveLength(0)

      fail = true
      await conv.uploadAttachment(new File(['x'], 'b.zip', { type: 'application/zip' }))
      expect(conv.error).toContain('文件类型不支持')
      expect(conv.draftAttachments).toHaveLength(0)
    } finally {
      vi.unstubAllGlobals()
    }
  })
})

describe('消息排队与自动续发', () => {
  /** 内存版 localStorage（node 测试环境没有全局 localStorage）。 */
  function memoryStorage(): Storage {
    const map = new Map<string, string>()
    return {
      length: 0,
      key: (i: number) => [...map.keys()][i] ?? null,
      clear: () => map.clear(),
      getItem: (k: string) => map.get(k) ?? null,
      setItem: (k: string, v: string) => void map.set(k, String(v)),
      removeItem: (k: string) => void map.delete(k),
    } as Storage
  }

  /** 等待 watcher 触发的续发链收敛（全链路微任务驱动，若干轮宏任务足够）。 */
  async function settle(rounds = 20): Promise<void> {
    for (let i = 0; i < rounds; i++) await new Promise((r) => setTimeout(r, 0))
  }

  /** POST /ai/chat/stream 的 SSE 响应替身：run_started + done 正常收敛。 */
  function sseStream(runId: string, conversationId: number): Response {
    const body =
      `event: run_started\ndata: ${JSON.stringify({ v: 1, type: 'run_started', run_id: runId, conversation_id: conversationId })}\n\n` +
      `event: done\ndata: ${JSON.stringify({ v: 1, type: 'done', run_id: runId })}\n\n`
    return {
      ok: true,
      status: 200,
      body: new ReadableStream<Uint8Array>({
        start(ctrl) { ctrl.enqueue(new TextEncoder().encode(body)); ctrl.close() },
      }),
    } as unknown as Response
  }

  /** 让会话 1 进入 run 进行中（模拟本地活跃 run）。 */
  function startRun(conv: ReturnType<typeof useConversationStore>, run: ReturnType<typeof useRunStore>): void {
    conv.activeId = 1
    run.consume({ v: 1, type: 'run_started', run_id: 'r1', conversation_id: 1 })
  }

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal('localStorage', memoryStorage())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('run 活跃时 sendMessage 入队而不发请求；sending 时维持原样静默忽略', async () => {
    const fetchMock = vi.fn(async () => jsonResponse([]))
    vi.stubGlobal('fetch', fetchMock)
    const conv = useConversationStore()
    const run = useRunStore()
    startRun(conv, run)

    await conv.sendMessage('帮我加一条日程')
    expect(conv.queuedMessages).toEqual(['帮我加一条日程'])
    expect(fetchMock).not.toHaveBeenCalled()

    await conv.sendMessage('   ') // 空白消息不入队
    expect(conv.queuedMessages).toEqual(['帮我加一条日程'])

    await conv.sendMessage('第二条')
    expect(conv.queuedMessages).toEqual(['帮我加一条日程', '第二条'])

    conv.sending = true // 原 sending 拦截保持静默忽略（不转排队）
    await conv.sendMessage('第三条')
    expect(conv.queuedMessages).toEqual(['帮我加一条日程', '第二条'])
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('run 正常收敛后自动依次续发队列，直到清空', async () => {
    const streamMessages: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
        if (String(url) === '/ai/chat/stream') {
          const body = JSON.parse(String(init?.body ?? '{}')) as { message: string }
          streamMessages.push(body.message)
          return sseStream(`rq${streamMessages.length}`, 1)
        }
        return jsonResponse([])
      }),
    )
    const conv = useConversationStore()
    const run = useRunStore()
    startRun(conv, run)
    await conv.sendMessage('第一条')
    await conv.sendMessage('第二条')
    expect(streamMessages).toEqual([]) // 仍在排队，未发请求

    run.consume({ v: 1, type: 'done', run_id: 'r1' }) // 原任务正常完成
    await settle()
    expect(run.phase).toBe('completed')
    expect(conv.queuedMessages).toEqual([])
    expect(streamMessages).toEqual(['第一条', '第二条']) // 依次各开一条流
    expect(run.sentMessage).toBe('第二条')
  })

  it('run 以 error 收敛时不自动续发，队列原样保留', async () => {
    const fetchMock = vi.fn(async () => jsonResponse([]))
    vi.stubGlobal('fetch', fetchMock)
    const conv = useConversationStore()
    const run = useRunStore()
    startRun(conv, run)
    await conv.sendMessage('排队一')
    await conv.sendMessage('排队二')

    run.consume({ v: 1, type: 'run_error', run_id: 'r1', message: '上游过载', retryable: true })
    run.consume({ v: 1, type: 'done', run_id: 'r1' })
    await settle()
    expect(run.phase).toBe('error')
    expect(conv.queuedMessages).toEqual(['排队一', '排队二'])
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('run 被取消时不自动续发，队列原样保留', async () => {
    const calls: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string | URL | Request) => {
        calls.push(String(url))
        return jsonResponse({ ok: true })
      }),
    )
    const conv = useConversationStore()
    const run = useRunStore()
    startRun(conv, run)
    await conv.sendMessage('排队一')
    await conv.sendMessage('排队二')

    await run.cancel()
    await settle()
    expect(run.phase).toBe('cancelled')
    expect(conv.queuedMessages).toEqual(['排队一', '排队二'])
    expect(calls).toEqual(['/ai/runs/r1/cancel']) // 只有取消请求，没有续发流
  })

  it('队列按会话持久化到 localStorage，切换/刷新后恢复对应队列', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse([])))
    const conv = useConversationStore()
    const run = useRunStore()
    startRun(conv, run)

    await conv.sendMessage('会话一的消息')
    expect(localStorage.getItem('zhishi:queued-messages:1')).toBe(JSON.stringify(['会话一的消息']))

    await conv.select(2) // 切到会话 2：队列随会话隔离
    expect(conv.queuedMessages).toEqual([])
    await conv.sendMessage('会话二的消息') // 会话 1 的 run 仍活跃 → 入会话 2 的队
    expect(localStorage.getItem('zhishi:queued-messages:2')).toBe(JSON.stringify(['会话二的消息']))
    expect(localStorage.getItem('zhishi:queued-messages:1')).toBe(JSON.stringify(['会话一的消息']))

    await conv.select(1)
    expect(conv.queuedMessages).toEqual(['会话一的消息'])

    // 模拟刷新：全新 pinia 与 store，从 localStorage 恢复
    setActivePinia(createPinia())
    const revived = useConversationStore()
    await revived.select(1)
    expect(revived.queuedMessages).toEqual(['会话一的消息'])
  })

  it('删除队列条目并同步落盘；越界索引不动作', () => {
    const conv = useConversationStore()
    conv.activeId = 1
    conv.enqueueMessage('甲')
    conv.enqueueMessage('乙')
    conv.removeQueuedMessage(0)
    expect(conv.queuedMessages).toEqual(['乙'])
    expect(localStorage.getItem('zhishi:queued-messages:1')).toBe(JSON.stringify(['乙']))

    conv.removeQueuedMessage(5)
    expect(conv.queuedMessages).toEqual(['乙'])

    conv.removeQueuedMessage(0)
    expect(conv.queuedMessages).toEqual([])
    expect(localStorage.getItem('zhishi:queued-messages:1')).toBeNull() // 空队列清键
  })
})
