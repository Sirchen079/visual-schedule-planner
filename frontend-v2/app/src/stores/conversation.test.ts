import { beforeEach, describe, expect, it, vi } from 'vitest'
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
