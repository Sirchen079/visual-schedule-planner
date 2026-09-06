import { describe, expect, it } from 'vitest'
import { buildTimeline } from './timeline'
import { initialRunState } from '../../stores/run'
import type { ConversationMessage } from '../../api/ai'

function msg(id: number, role: string, text: string): ConversationMessage {
  return { id, role, display: { text }, created_at: '2026-09-04T12:00:00' }
}

describe('buildTimeline：历史 + live run 合并', () => {
  it('历史消息按服务端顺序；无 run 内容时只返回历史', () => {
    const items = buildTimeline({
      messages: [msg(1, 'user', '你好'), msg(2, 'assistant', '你好呀')],
      run: { ...initialRunState() },
    })
    expect(items.map((i) => i.kind)).toEqual(['history-user', 'history-assistant'])
  })

  it('sentMessage 回显排在历史之后；live 内容按 seq 单调合并（text/reasoning/tool 交错）', () => {
    const run = initialRunState()
    run.conversationId = 5
    run.sentMessage = '帮我看下周五空不空'
    // 模拟事件到达序：text(1) → tool(2) → text(3)
    run.segments.push(
      { kind: 'text', content: '我先查一下。', seq: 1 },
      { kind: 'text', content: '周五 14:00 后空闲。', seq: 3 },
    )
    run.toolCalls.push({
      callId: 'c1',
      tool: 'find_free_slots',
      argsPreview: '{}',
      status: 'ok',
      resultPreview: 'ok',
      durationMs: 12,
      seq: 2,
    })
    const items = buildTimeline({
      messages: [msg(9, 'user', '上一轮的问题')],
      run,
    })
    expect(items.map((i) => i.kind)).toEqual([
      'history-user',
      'sent',
      'text',
      'tool',
      'text',
    ])
    const seqs = items.filter((i) => 'seq' in i).map((i) => (i as { seq: number }).seq)
    expect(seqs).toEqual([...seqs].sort((a, b) => a - b))
  })

  it('run 未关联会话（conversationId=null）时不产生 live 项', () => {
    const run = initialRunState()
    run.sentMessage = '孤儿回显也不该出现'
    const items = buildTimeline({ messages: [], run })
    expect(items).toHaveLength(0)
  })
})
