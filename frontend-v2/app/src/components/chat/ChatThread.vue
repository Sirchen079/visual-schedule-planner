<script setup lang="ts">
/**
 * 消息流：历史消息 + live run 内容按时间线渲染。
 * - text_delta → 正文段（流式尾部带光标）；reasoning_delta → 可折叠「思考过程」。
 * - 工具卡按流内 seq 顺序插入；审批卡/计划卡固定渲染在流末尾（线程最醒目的待决元素）。
 * - M3.5：审批卡以审批账目（approvalLedger）驱动渲染全部卡——同流多个
 *   tool_approval_requested 不再只显示 pendingApproval 单槽位的最后一张；
 *   已批准/已拒绝的卡保留图章（与日历幽灵块图章语言一致），待决卡独立操作。
 */
import { computed } from 'vue'
import { useConversationStore } from '../../stores/conversation'
import { useRunStore, type ToolCallItem } from '../../stores/run'
import AppIcon from '../AppIcon.vue'
import ApprovalCard from './ApprovalCard.vue'
import PlanCardView from './PlanCardView.vue'
import ToolCard from './ToolCard.vue'
import { buildTimeline, type ThreadItem } from './timeline'
import { renderMarkdown } from '../../utils/md'

const run = useRunStore()
const conv = useConversationStore()

const items = computed(() =>
  buildTimeline({ messages: conv.messages, sentEchoAttachments: conv.sentEchoAttachments, run, activeConversationId: conv.activeId }),
)

const showLive = computed(() => run.conversationId === conv.activeId)

const showCaret = computed(
  () => run.phase === 'streaming' && run.stage === 'streaming_text',
)

function toolByCallId(callId: string) {
  return run.toolCalls.find((c) => c.callId === callId)
}

function savedTools(events: Array<Record<string, unknown>> = [], status?: string): ToolCallItem[] {
  const tools: ToolCallItem[] = []
  for (const e of events) {
    if (e.type === 'tool_call_started') tools.push({ callId: String(e.call_id), tool: String(e.tool),
      argsPreview: String(e.args_preview ?? ''), status: 'running', resultPreview: null, durationMs: null, seq: tools.length })
    if (e.type === 'tool_call_result') {
      const tool = tools.find(t => t.callId === e.call_id)
      if (tool) { tool.status = e.ok ? 'ok' : 'error'; tool.resultPreview = String(e.result_preview ?? ''); tool.durationMs = Number(e.duration_ms ?? 0) }
    }
  }
  for (const tool of tools) if (tool.status === 'running' && status !== 'running') tool.status = status === 'awaiting_approval' ? 'pending' : 'interrupted'
  return tools
}
function savedStatus(status?: string): string {
  return ({ running:'执行中 · 自动同步已保存进度', interrupted:'已中断 · 最近进度已保存', cancelled:'已停止',
    failed:'生成失败 · 已保存本轮记录', budget_exceeded:'达到执行预算 · 已保存本轮记录', awaiting_approval:'等待审批' } as Record<string,string>)[status ?? ''] ?? ''
}

function timeLabel(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const historyLabel = computed(() => {
  const first = conv.messages[0]
  return first ? timeLabel(first.created_at) : ''
})

function itemKey(item: ThreadItem, idx: number): string {
  if ('id' in item) return `${item.kind}-${item.id}`
  if ('seq' in item) return `${item.kind}-${item.seq}`
  return `${item.kind}-${idx}`
}
</script>

<template>
  <div class="thread-items">
    <!-- 空状态：新对话引导 -->
    <div v-if="!items.length && (!showLive || (!run.approvalLedger.length && !run.planCard))" class="empty">
      <div class="empty-mark">知时</div>
      <p class="empty-line">把想做的事告诉知时。</p>
      <p class="empty-line">安排时间、整理资料，或一起规划下一步。</p>
      <p class="empty-hint">需要确认的变更，会先与你核对。</p>
    </div>

    <!-- 历史消息统一挂在一条日期分隔线之下（与 final-shell 的 divider 一致） -->
    <div v-if="conv.messages.length" class="divider">{{ historyLabel }}</div>

    <template v-for="(item, idx) in items" :key="itemKey(item, idx)">
      <div v-if="item.kind === 'history-user'" class="msg-user">
        <span v-for="a in item.attachments" :key="a.id" class="att">{{ a.name }}</span>
        <span class="text">{{ item.text }}</span>
      </div>
      <div v-else-if="item.kind === 'history-assistant'" class="msg-ai">
        <span class="who">知时 · 助手</span>
        <div class="body" v-html="renderMarkdown(item.text)" />
        <p v-if="savedStatus(item.display.status)" class="saved-status">{{ savedStatus(item.display.status) }}</p>
        <p v-if="item.display.error" class="saved-status">{{ item.display.error }}</p>
        <details v-if="item.display.reasoning" class="think"><summary>思考过程</summary><div class="think-body">{{ item.display.reasoning }}</div></details>
        <details v-if="item.display.tools?.length" class="think"><summary>本轮工具记录</summary><ToolCard v-for="call in savedTools(item.display.tools, item.display.status)" :key="call.callId" :call="call" /></details>
      </div>
      <div v-else-if="item.kind === 'sent'" class="msg-user">
        <span v-for="a in item.attachments" :key="a.id" class="att">{{ a.name }}</span>
        <span class="text">{{ item.text }}</span>
      </div>
      <div v-else-if="item.kind === 'text'" class="msg-ai">
        <span class="who">知时 · 助手</span>
        <div class="body"><span v-html="renderMarkdown(item.content)" /><span v-if="showCaret && idx === items.length - 1" class="caret" /></div>
      </div>
      <details v-else-if="item.kind === 'reasoning'" class="think">
        <summary>
          <AppIcon name="chevron-down" class="tw" :size="12" />
          思考过程
          <span class="len">{{ item.content.length }} 字</span>
        </summary>
        <div class="think-body">{{ item.content }}</div>
      </details>
      <ToolCard v-else-if="item.kind === 'tool'" :call="toolByCallId(item.callId)!" />
    </template>

    <!-- 待决卡片固定在流末尾（审批卡按账目全量渲染：多卡并存、图章留痕） -->
    <PlanCardView v-if="showLive && run.planCard" :plan="run.planCard" />
    <ApprovalCard v-for="entry in (showLive ? run.approvalLedger : [])" :key="entry.actionId" :approval="entry" />
  </div>
</template>

<style scoped>
.saved-status { color:var(--amber); font-size:12px; margin-top:6px; }
.thread-items {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.empty {
  padding: 42px 8px 20px;
  text-align: center;
}
.empty-mark {
  font-family: var(--serif);
  font-size: 30px;
  font-weight: 600;
  color: var(--amber-soft);
  letter-spacing: 0.28em;
  text-indent: 0.28em;
  margin-bottom: 16px;
}
.empty-line {
  font-size: 13.5px;
  color: var(--ink-2);
  line-height: 1.8;
}
.empty-hint {
  margin-top: 10px;
  font-size: 12px;
  color: var(--ink-3);
}
.divider {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--ink-3);
  font-size: 12px;
  min-height: 14px;
}
.divider::before,
.divider::after {
  content: '';
  flex: 1;
  border-top: 1px solid var(--line);
}
.msg-user {
  align-self: flex-end;
  max-width: 86%;
  background: var(--bg-bubble);
  border: 1px solid var(--line-2);
  border-radius: 12px 12px 4px 12px;
  padding: 10px 14px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--ink);
  display: flex;
  flex-direction: column;
  gap: 5px;
  flex: none;
  white-space: pre-wrap;
  word-break: break-word;
}
.msg-user .att {
  font-size: 12px;
  color: var(--amber-dim);
  border: 1px dashed var(--amber-border);
  border-radius: 6px;
  padding: 2px 8px;
  align-self: flex-start;
}
.msg-ai {
  padding: 0 2px;
}
.msg-ai .who {
  display: block;
  font-family: var(--mono);
  font-size: 11.5px;
  letter-spacing: 0.16em;
  color: var(--ink-3);
  margin-bottom: 5px;
}
.msg-ai .body {
  font-size: 14.5px;
  line-height: 1.72;
  color: var(--ink);
  word-break: break-word;
}
.msg-ai .body :deep(p) {
  margin: 0 0 0.45em;
}
.msg-ai .body :deep(p:last-child) {
  margin-bottom: 0;
}
.msg-ai .body :deep(ul),
.msg-ai .body :deep(ol) {
  padding-left: 1.5em;
  margin: 0.2em 0 0.45em;
}
.msg-ai .body :deep(ul) {
  list-style: disc;
}
.msg-ai .body :deep(ol) {
  list-style: decimal;
}
.msg-ai .body :deep(li) {
  margin: 0.15em 0;
}
.msg-ai .body :deep(strong) {
  color: var(--amber-soft);
  font-weight: 600;
}
.msg-ai .body :deep(code) {
  font-family: var(--mono);
  font-size: 0.88em;
  background: var(--bg-sink);
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 0.1em 0.35em;
}
.msg-ai .body :deep(table) {
  border-collapse: collapse;
  margin: 0.3em 0 0.6em;
  font-size: 13px;
  max-width: 100%;
}
.msg-ai .body :deep(th),
.msg-ai .body :deep(td) {
  border: 1px solid var(--line-2);
  padding: 0.3em 0.7em;
  text-align: left;
  vertical-align: top;
}
.msg-ai .body :deep(th) {
  color: var(--amber-soft);
  background: var(--bg-sink);
  font-weight: 600;
  white-space: nowrap;
}
.caret {
  display: inline-block;
  width: 2px;
  height: 15px;
  background: var(--amber);
  vertical-align: -2px;
  margin-left: 3px;
  animation: blink 1.1s steps(2) infinite;
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}
.think {
  border: 1px dashed var(--line-2);
  border-radius: var(--radius-m);
  background: transparent;
  overflow: hidden;
  flex: none;
}
.think summary {
  list-style: none;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 12px;
  color: var(--ink-3);
  user-select: none;
}
.think summary::-webkit-details-marker {
  display: none;
}
.think .tw {
  transition: transform 0.15s;
}
.think[open] .tw {
  transform: rotate(180deg);
}
.think .len {
  margin-left: auto;
  font-family: var(--mono);
  font-size: 11px;
}
.think-body {
  padding: 2px 14px 10px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--ink-2);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 220px;
  overflow: auto;
}
</style>
