import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useConversationStore } from './conversation'
import { useRunStore } from './run'
import type { ConversationState } from '../api/sessions'

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

describe('运行中插话（steering）', () => {
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

  /** 等待 watcher 触发的收敛链跑完（全链路微任务驱动，若干轮宏任务足够）。 */
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

  /** 让会话 1 进入本地 run 进行中（模拟活跃 run 的本地流）。 */
  function startRun(conv: ReturnType<typeof useConversationStore>, run: ReturnType<typeof useRunStore>): void {
    conv.activeId = 1
    run.consume({ v: 1, type: 'run_started', run_id: 'r1', conversation_id: 1 })
  }

  /** 记录 /ai/chat/stream 收到的消息体。 */
  const streamMessages: string[] = []

  /** 缺省 fetch 替身：/steer 受理、聊天流记账、其余（历史/列表）返回空。 */
  function stubDefaultFetch(steer: Response | Promise<Response> | Error = jsonResponse({ run_id: 'r1', accepted: true })): ReturnType<typeof vi.fn> {
    streamMessages.length = 0
    return vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const target = String(url)
      if (target.endsWith('/steer')) {
        if (steer instanceof Error) throw steer
        return steer
      }
      if (target === '/ai/chat/stream') {
        streamMessages.push((JSON.parse(String(init?.body ?? '{}')) as { message: string }).message)
        return sseStream(`rq${streamMessages.length}`, 1)
      }
      return jsonResponse([])
    })
  }

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal('localStorage', memoryStorage())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('run 活跃时 sendMessage 走插话：乐观条目 + POST steer + 立即清草稿，不开聊天流', async () => {
    const fetchMock = stubDefaultFetch()
    vi.stubGlobal('fetch', fetchMock)
    const conv = useConversationStore()
    const run = useRunStore()
    startRun(conv, run)
    conv.draftText = '帮我加一条日程'

    await conv.sendMessage('帮我加一条日程')
    expect(conv.steerEntries).toHaveLength(1)
    expect(conv.steerEntries[0]).toMatchObject({ text: '帮我加一条日程', runId: 'r1', messageId: null })
    expect(conv.steerEntries[0]!.token).toBeTruthy()
    expect(conv.draftText).toBe('') // 插话即清草稿
    expect(fetchMock).toHaveBeenCalledWith(
      '/ai/conversations/1/steer',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ text: '帮我加一条日程', token: conv.steerEntries[0]!.token }) }),
    )
    expect(streamMessages).toEqual([]) // 不开新聊天流
    expect(conv.queuedMessages).toEqual([]) // 也不再进 v1 队列

    await conv.sendMessage('   ') // 空白不插话
    expect(conv.steerEntries).toHaveLength(1)
  })

  it('插话清草稿的等值守卫：草稿已被改写时不动草稿（程序化调用安全）', async () => {
    vi.stubGlobal('fetch', stubDefaultFetch())
    const conv = useConversationStore()
    const run = useRunStore()
    startRun(conv, run)
    conv.draftText = '别动我'
    await conv.sendMessage('插话内容')
    expect(conv.draftText).toBe('别动我')
    expect(conv.steerEntries.map((e) => e.text)).toEqual(['插话内容'])
  })

  it('steer_accepted 凭 token 确认注入；落库行进消息列表后乐观条目移除防重复', async () => {
    vi.stubGlobal('fetch', stubDefaultFetch())
    const conv = useConversationStore()
    const run = useRunStore()
    startRun(conv, run)
    await conv.sendMessage('插话甲')
    const token = conv.steerEntries[0]!.token

    run.consume({ v: 1, type: 'steer_accepted', text: '插话甲', message_id: 55, token })
    expect(conv.steerEntries[0]!.messageId).toBe(55) // 已注入

    conv.messages = [{ id: 55, role: 'user', display: { text: '插话甲', steered: true }, created_at: '' }]
    conv.dedupeSteered()
    expect(conv.steerEntries).toEqual([]) // 服务端行已进历史：移除乐观条目

    run.consume({ v: 1, type: 'steer_accepted', text: '陌生插话', message_id: 66, token: '不存在的token' })
    expect(conv.steerEntries).toEqual([]) // 未知 token 不产生任何条目
  })

  it('run 正常收敛：未确认的插话回退补发，已确认的不补发；确认条目随历史对账移除', async () => {
    streamMessages.length = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const target = String(url)
      if (target.endsWith('/steer')) return jsonResponse({ run_id: 'r1', accepted: true })
      if (target === '/ai/chat/stream') {
        streamMessages.push((JSON.parse(String(init?.body ?? '{}')) as { message: string }).message)
        return sseStream(`rq${streamMessages.length}`, 1)
      }
      if (target === '/ai/conversations/1') {
        // 已确认插话的落库行（steered user 行，id=55）
        return jsonResponse([{ id: 55, role: 'user', display: { text: '插话甲', steered: true }, created_at: '' }])
      }
      return jsonResponse([])
    }))
    const conv = useConversationStore()
    const run = useRunStore()
    startRun(conv, run)

    await conv.sendMessage('插话甲')
    const confirmedToken = conv.steerEntries[0]!.token
    run.consume({ v: 1, type: 'steer_accepted', text: '插话甲', message_id: 55, token: confirmedToken })
    await conv.sendMessage('插话乙')
    expect(conv.steerEntries).toHaveLength(2)
    expect(streamMessages).toEqual([])

    run.consume({ v: 1, type: 'run_completed', run_id: 'r1', usage: {}, elapsed_ms: 5, done_reason: 'end_turn' })
    run.consume({ v: 1, type: 'done', run_id: 'r1' })
    await settle()
    expect(run.phase).toBe('completed')
    expect(streamMessages).toEqual(['插话乙']) // 只有未确认的补发
    expect(conv.queuedMessages).toEqual([])
    expect(conv.steerEntries).toEqual([]) // 甲的落库行(id=55)已进历史 → 乐观条目移除
  })

  it('steer 409（服务端已无活跃 run）且本地 run 仍活跃 → 转 v1 队列，run 收敛后续发', async () => {
    vi.stubGlobal('fetch', stubDefaultFetch(jsonResponse({ detail: '当前没有进行中的任务' }, 409)))
    const conv = useConversationStore()
    const run = useRunStore()
    startRun(conv, run)

    await conv.sendMessage('补发我')
    expect(conv.steerEntries).toEqual([]) // 条目移除
    expect(conv.queuedMessages).toEqual(['补发我']) // 本地活跃态滞后 → 队列兜底
    expect(streamMessages).toEqual([])

    run.consume({ v: 1, type: 'done', run_id: 'r1' })
    await settle()
    expect(streamMessages).toEqual(['补发我']) // 收敛后由既有队列机制续发
  })

  it('steer 409 且本地 run 恰在 POST 期间收敛 → 直接常规发送，恰好一次', async () => {
    let resolveSteer!: (value: Response) => void
    vi.stubGlobal('fetch', stubDefaultFetch(new Promise<Response>((r) => { resolveSteer = r })))
    const conv = useConversationStore()
    const run = useRunStore()
    startRun(conv, run)

    const sending = conv.sendMessage('补发我')
    await settle(2)
    expect(conv.steerEntries).toHaveLength(1)

    run.consume({ v: 1, type: 'done', run_id: 'r1' }) // 本地 run 先收敛
    resolveSteer(jsonResponse({ detail: '当前没有进行中的任务' }, 409)) // 409 后到
    await sending
    await settle()
    expect(conv.steerEntries).toEqual([])
    expect(conv.queuedMessages).toEqual([])
    expect(streamMessages).toEqual(['补发我'])
  })

  it('steer 网络异常回退：本地 run 仍活跃 → 转 v1 队列，收敛后自动续发', async () => {
    vi.stubGlobal('fetch', stubDefaultFetch(new Error('网络错误')))
    const conv = useConversationStore()
    const run = useRunStore()
    startRun(conv, run)

    await conv.sendMessage('网络断了也要送到')
    expect(conv.steerEntries).toEqual([])
    expect(conv.queuedMessages).toEqual(['网络断了也要送到'])
    expect(streamMessages).toEqual([])

    run.consume({ v: 1, type: 'done', run_id: 'r1' })
    await settle()
    expect(streamMessages).toEqual(['网络断了也要送到'])
  })

  it('run 以错误收敛时未确认插话仍回退补发（模型从未见过该消息）', async () => {
    vi.stubGlobal('fetch', stubDefaultFetch())
    const conv = useConversationStore()
    const run = useRunStore()
    startRun(conv, run)
    await conv.sendMessage('错误前的插话')

    run.consume({ v: 1, type: 'run_error', run_id: 'r1', message: '上游过载', retryable: true })
    run.consume({ v: 1, type: 'done', run_id: 'r1' })
    expect(run.phase).toBe('error')
    await settle()
    expect(conv.steerEntries).toEqual([])
    expect(streamMessages).toEqual(['错误前的插话']) // 补发开新流
  })

  it('run 被取消收敛：未注入的插话转待发队列保留（用户处置），已注入的保留展示，均不自动续发', async () => {
    vi.stubGlobal('fetch', stubDefaultFetch())
    const conv = useConversationStore()
    const run = useRunStore()
    startRun(conv, run)
    await conv.sendMessage('第一条')
    await conv.sendMessage('第二条')
    run.consume({ v: 1, type: 'steer_accepted', text: '第一条', message_id: 77, token: conv.steerEntries[0]!.token })
    expect(conv.steerEntries).toHaveLength(2)

    await run.cancel()
    await settle()
    expect(run.phase).toBe('cancelled')
    expect(conv.steerEntries.map((e) => e.text)).toEqual(['第一条']) // 已确认注入的保留（落库行真实存在）
    expect(conv.queuedMessages).toEqual(['第二条']) // 未注入的转 v1 队列，由用户处置
    expect(streamMessages).toEqual([]) // 取消不自动续发
  })

  it('撤回：POST 在途时中断请求并移除条目，不回退发送；已受理后不可撤回', async () => {
    streamMessages.length = 0
    const steerSignals: AbortSignal[] = []
    let releaseSteer: ((value: Response) => void) | null = null
    vi.stubGlobal('fetch', vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const target = String(url)
      if (target.endsWith('/steer')) {
        const signal = (init?.signal as AbortSignal | undefined) ?? null
        if (signal) steerSignals.push(signal)
        if (signal?.aborted) throw new DOMException('aborted', 'AbortError')
        return new Promise<Response>((resolve, reject) => {
          releaseSteer = resolve
          signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
        })
      }
      if (target === '/ai/chat/stream') {
        streamMessages.push((JSON.parse(String(init?.body ?? '{}')) as { message: string }).message)
        return sseStream(`rq${streamMessages.length}`, 1)
      }
      return jsonResponse([])
    }))
    const conv = useConversationStore()
    const run = useRunStore()
    startRun(conv, run)

    // 第一条：POST 在途（可撤回窗口）→ 撤回中断请求
    const sending1 = conv.sendMessage('撤回我')
    await settle(2)
    expect(conv.steerEntries).toHaveLength(1)
    conv.withdrawSteer(conv.steerEntries[0]!.token)
    expect(conv.steerEntries).toEqual([])
    expect(steerSignals[0]!.aborted).toBe(true) // 请求被中断
    await sending1
    await settle()
    expect(conv.queuedMessages).toEqual([]) // 撤回不回退发送
    expect(streamMessages).toEqual([])

    // 第二条：放行 POST（已受理）→ 不可撤回
    const sending2 = conv.sendMessage('已受理不可撤')
    await settle(2)
    releaseSteer!(jsonResponse({ run_id: 'r1', accepted: true }))
    await sending2
    expect(conv.steerEntries).toHaveLength(1)
    expect(conv.steerEntries[0]!.runId).toBe('r1')
    conv.withdrawSteer(conv.steerEntries[0]!.token)
    expect(conv.steerEntries).toHaveLength(1) // 撤回被拒绝
  })

  it('切换会话清空插话条目并中断在途 POST，不跨会话回退发送', async () => {
    let resolveSteer!: (value: Response) => void
    const pending = new Promise<Response>((r) => { resolveSteer = r })
    vi.stubGlobal('fetch', stubDefaultFetch(pending))
    const conv = useConversationStore()
    const run = useRunStore()
    startRun(conv, run)

    const sending = conv.sendMessage('旧会话的插话')
    await settle(2)
    expect(conv.steerEntries).toHaveLength(1)

    await conv.select(2) // 切到会话 2：条目清空 + 在途 POST 被中断
    expect(conv.steerEntries).toEqual([])

    resolveSteer(jsonResponse({ run_id: 'r1', accepted: true })) // 迟到的受理不复活条目
    await sending
    await settle()
    expect(conv.steerEntries).toEqual([])
    expect(conv.queuedMessages).toEqual([])
    expect(streamMessages).toEqual([])
  })

  it('远端 run（另一窗口执行）仍走 v1 队列，远端收敛后自动续发', async () => {
    vi.stubGlobal('fetch', stubDefaultFetch())
    const conv = useConversationStore()
    conv.activeId = 1
    conv.sessionState = {
      conversation_id: 1, active_run_id: 'rX', latest_run_id: 'rX', status: 'running',
      approvals: [], plan: null, can_resume: false, message_count: 0, archive_count: 0,
      working_rounds: 0, summary: '', model: '', context_window: null,
    }

    await conv.sendMessage('远端排队')
    expect(conv.steerEntries).toEqual([])
    expect(conv.queuedMessages).toEqual(['远端排队'])
    expect(streamMessages).toEqual([])

    conv.sessionState = { ...conv.sessionState, active_run_id: null } as ConversationState
    await settle() // 远端 run 收敛（remoteRunId 消失）→ 队列续发
    expect(streamMessages).toEqual(['远端排队'])
    expect(conv.queuedMessages).toEqual([])
  })

  it('本地 run 活跃但直发占用中（sending）→ 维持静默忽略，不插话不排队', async () => {
    vi.stubGlobal('fetch', stubDefaultFetch())
    const conv = useConversationStore()
    const run = useRunStore()
    startRun(conv, run)
    conv.sending = true
    await conv.sendMessage('第三条')
    expect(conv.steerEntries).toEqual([])
    expect(conv.queuedMessages).toEqual([])
    expect(streamMessages).toEqual([])
  })
})

describe('待发队列（v1 路径：远端 run / 插话回退的持久化与处置）', () => {
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

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal('localStorage', memoryStorage())
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse([])))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('队列按会话持久化到 localStorage，切换/刷新后恢复对应队列', async () => {
    const conv = useConversationStore()
    conv.activeId = 1
    conv.enqueueMessage('会话一的消息')
    expect(localStorage.getItem('zhishi:queued-messages:1')).toBe(JSON.stringify(['会话一的消息']))

    await conv.select(2) // 切到会话 2：队列随会话隔离
    expect(conv.queuedMessages).toEqual([])
    conv.enqueueMessage('会话二的消息')
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

  it('run 以 error/cancelled 收敛时不自动续发既有队列，队列原样保留', async () => {
    async function settle(): Promise<void> {
      for (let i = 0; i < 20; i++) await new Promise((r) => setTimeout(r, 0))
    }
    const conv = useConversationStore()
    const run = useRunStore()
    conv.activeId = 1
    conv.enqueueMessage('排队一')
    conv.enqueueMessage('排队二')

    // error 收敛（busy→idle 转换触发 watcher）
    run.consume({ v: 1, type: 'run_started', run_id: 'r1', conversation_id: 1 })
    run.consume({ v: 1, type: 'run_error', run_id: 'r1', message: '上游过载', retryable: true })
    run.consume({ v: 1, type: 'done', run_id: 'r1' })
    await settle()
    expect(conv.queuedMessages).toEqual(['排队一', '排队二'])

    // cancelled 收敛
    run.consume({ v: 1, type: 'run_started', run_id: 'r2', conversation_id: 1 })
    await run.cancel()
    await settle()
    expect(conv.queuedMessages).toEqual(['排队一', '排队二'])
  })
})
