/**
 * 对话时间线：把「持久化历史消息」与「live run 流内容」合并成一个可渲染的有序列表。
 *
 * 顺序 = 历史消息（服务端顺序）→ 本地回显的刚发送消息 → live 内容（seq 单调序）。
 * 纯函数，便于单测。审批卡/计划卡不进时间线（由 ChatThread 固定渲染在流末尾，
 * 与 final-shell 一致：待决卡片是线程最末、最醒目的元素）。
 */
import type { ConversationMessage, ConversationMessageDisplay } from '../../api/ai'
import type { useRunStore } from '../../stores/run'

export type RunStore = ReturnType<typeof useRunStore>

export type ThreadItem =
  | { kind: 'history-user'; id: number; text: string; attachments: { id: number; name: string }[] }
  | { kind: 'history-assistant'; id: number; text: string; display: ConversationMessageDisplay }
  | { kind: 'sent'; text: string; attachments: { id: number; name: string }[] }
  | { kind: 'text'; seq: number; content: string }
  | { kind: 'reasoning'; seq: number; content: string }
  | { kind: 'tool'; seq: number; callId: string }

interface TimelineInput {
  activeConversationId?: number | null
  messages: ConversationMessage[]
  /** 刚发送消息的附件快照（本地回显显示附件 chip；历史落库后以服务端为准） */
  sentEchoAttachments?: { id: number; name: string }[]
  run: Pick<
    RunStore,
    'conversationId' | 'sentMessage' | 'segments' | 'toolCalls'
  > & { runId?: string | null; renderedRunIds?: string[] }
}

type LiveItem =
  | { kind: 'text'; seq: number; content: string }
  | { kind: 'reasoning'; seq: number; content: string }
  | { kind: 'tool'; seq: number; callId: string }

export function buildTimeline({ messages, sentEchoAttachments = [], run, activeConversationId }: TimelineInput): ThreadItem[] {
  const items: ThreadItem[] = []
  const visibleRun = !!run.conversationId && (activeConversationId === undefined || run.conversationId === activeConversationId)
  const hasLiveContent = !!(run.sentMessage || run.segments.length || run.toolCalls.length)
  for (const m of messages) {
    if (visibleRun && hasLiveContent && run.runId && (m.display.run_id === run.runId || run.renderedRunIds?.includes(m.display.run_id ?? ''))) continue
    if (m.role === 'user') {
      items.push({
        kind: 'history-user',
        id: m.id,
        text: m.display.text,
        attachments: (m.display.attachments ?? []).map((a) => ({ id: a.id, name: a.name })),
      })
    } else {
      items.push({ kind: 'history-assistant', id: m.id, text: m.display.text, display: m.display })
    }
  }
  if (!run.conversationId || (activeConversationId !== undefined && run.conversationId !== activeConversationId)) return items
  if (run.sentMessage) items.push({ kind: 'sent', text: run.sentMessage, attachments: sentEchoAttachments })
  const live: LiveItem[] = []
  for (const s of run.segments) {
    live.push(
      s.kind === 'text'
        ? { kind: 'text', seq: s.seq, content: s.content }
        : { kind: 'reasoning', seq: s.seq, content: s.content },
    )
  }
  for (const c of run.toolCalls) live.push({ kind: 'tool', seq: c.seq, callId: c.callId })
  live.sort((a, b) => a.seq - b.seq)
  items.push(...live)
  return items
}
