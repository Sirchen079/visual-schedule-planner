<script setup>
// 单条消息气泡：结构化渲染文本块（不用 v-html）、工具结果 details、危险操作确认卡，
// assistant 消息 hover 显示「复制」。视觉样式集中在 AssistantView.vue 的样式块维护。
import { computed, inject, reactive, ref, watch, onBeforeUnmount } from 'vue'
import ArtIcon from '../../components/ArtIcon.vue'
import ToolCallCard from './ToolCallCard.vue'
import PlanCard from './PlanCard.vue'
import WorkPlanCard from './WorkPlanCard.vue'

const props = defineProps({
  message: { type: Object, required: true },
  assistantName: { type: String, default: '知时助手' },
  pendingTokens: { type: Object, default: () => ({}) },
  busy: { type: Boolean, default: false },
  // 当前 run 的实时状态文案（用于占位气泡的"正在思考…"提示）
  runStatus: { type: String, default: '' },
})
const emit = defineEmits(['first-confirm', 'second-confirm', 'reject', 'approve-plan', 'reject-plan', 'grant-action'])

// 阶段 D1：每个 pending action 的「以后都允许」勾选状态（按 action.id）
const grantChecked = reactive({})

// 阶段 D1：首次确认前若勾选了「以后都允许」，先发 grant-action（父组件创建 grant），再走首次确认
function onFirstConfirm(action) {
  if (grantChecked[action.id] && action.action_type) {
    emit('grant-action', { toolName: action.action_type, action })
    grantChecked[action.id] = false
  }
  emit('first-confirm', action)
}

// 二次确认防误点：token 出现后 600ms 内锁定执行按钮，防止第一次确认后快速双击直接触发执行
const SECOND_CONFIRM_COOLDOWN_MS = 600
const secondConfirmLocked = reactive({})
const cooldownTimers = []
watch(
  () => Object.keys(props.pendingTokens || {}),
  (curKeys, prevKeys) => {
    const prev = new Set(prevKeys || [])
    for (const actionId of curKeys) {
      if (prev.has(actionId)) continue
      secondConfirmLocked[actionId] = true
      const timer = window.setTimeout(() => {
        secondConfirmLocked[actionId] = false
      }, SECOND_CONFIRM_COOLDOWN_MS)
      cooldownTimers.push(timer)
    }
  },
  { deep: true }
)
onBeforeUnmount(() => {
  cooldownTimers.forEach((t) => window.clearTimeout(t))
})

// 悬浮窗宿主没有 toast provider，调用前必须判空
const toast = inject('toast', null)

// 工具名 → 中文动词（用于底部动作摘要 chip）
const ACTION_VERBS = {
  create_task: '创建任务', create_reminder: '创建提醒', create_note_file: '创建资料',
  create_subtask: '创建子任务', create_subtasks: '创建子任务', create_habit: '创建习惯',
  create_goal: '创建目标', write_journal: '写日记', check_in_habit: '习惯打卡',
  attach_file_to_task: '关联资料', save_attachment_to_library: '保存附件',
  assign_task_to_day: '安排日程', update_kr_progress: '更新 KR',
  start_timer: '开始计时', stop_timer: '停止计时',
  update_task: '更新任务', delete_task: '删除任务', delete_file: '删除资料',
  update_file_notes: '更新备注', detach_file_from_task: '取消关联',
  bulk_update_tasks: '批量更新', bulk_delete_tasks: '批量删除', bulk_delete_files: '批量删除',
  empty_trash: '清空回收站', import_web_resources: '导入资料',
  list_tasks: '查看任务', list_reminders: '查看提醒', list_files: '查看资料',
  list_subtasks: '查看子任务', list_day_schedule: '查看日程', list_month_schedule: '查看月度',
  list_habits: '查看习惯', list_journal_entries: '查看日记', list_goals: '查看目标',
  update_schedule_entry: '更新日程', delete_schedule_entry: '删除日程',
  bulk_assign_tasks_to_days: '批量安排', auto_plan_tasks: '自动排程',
  create_skill: '创建 Skill', create_mcp_server: '配置 MCP',
}

// 聚合动作摘要：[{label, count, tone}]，tone: ok|fail|pending
const actionSummary = computed(() => {
  const tools = props.message.tool_results || []
  if (!tools.length) return []
  const groups = new Map() // key: verb → {label, count, tone}
  let failCount = 0
  let pendingCount = 0
  for (const item of tools) {
    const name = String(item?.tool || '')
    const result = item?.result || {}
    if (result.ok === false && !result.pending) failCount += 1
    if (result.pending) pendingCount += 1
    const verb = ACTION_VERBS[name] || (name.startsWith('mcp__') ? `MCP·${name.split('__').pop()}` : name)
    const existing = groups.get(verb)
    if (existing) existing.count += 1
    else groups.set(verb, { label: verb, count: 1 })
  }
  const summary = [...groups.values()].map((g) => ({ ...g, tone: 'ok' }))
  if (failCount) summary.push({ label: `失败 ${failCount}`, count: failCount, tone: 'fail' })
  if (pendingCount) summary.push({ label: `待确认 ${pendingCount}`, count: pendingCount, tone: 'pending' })
  return summary
})

function pendingStatusText(action) {
  if (action.status === 'pending') return '等待确认'
  if (action.status === 'confirmed') return '已一次确认'
  if (action.status === 'executed') return '已执行'
  if (action.status === 'rejected') return '已拒绝'
  if (action.status === 'expired') return '已过期'
  return action.status || '待处理'
}

// 终态：不再展示确认/拒绝按钮，卡片降级为只读状态条
function isTerminalStatus(action) {
  return ['executed', 'rejected', 'expired'].includes(action.status)
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }
  // 非安全上下文（如 file:// 悬浮窗）降级：隐藏 textarea + execCommand
  const el = document.createElement('textarea')
  el.value = text
  el.style.position = 'fixed'
  el.style.opacity = '0'
  document.body.appendChild(el)
  el.select()
  document.execCommand('copy')
  el.remove()
}

async function copyMessage() {
  try {
    await copyText(props.message.content || '')
    toast?.success('已复制')
  } catch {
    toast?.error('复制失败')
  }
}

// 占位思考态：assistant 消息 streaming 中、且既无正文也无工具卡也无待确认动作时，
// 渲染"正在思考…"三点跳动指示器（对齐 Claude Code 发送后的即时反馈）。
const isThinkingPlaceholder = computed(() => {
  const m = props.message
  return (
    m?.role === 'assistant' &&
    m?.streaming === true &&
    !String(m?.content || '').trim() &&
    !(m?.tool_results?.length) &&
    !(m?.pending_actions?.length)
  )
})

// ---- reasoning（思维链）折叠块（阶段 3）：reasoning 由 AssistantView 累积到 message.reasoning ----
// streaming 期间默认展开流式追加；done 后默认折叠（用户可手动展开）。仅当 reasoning 非空时渲染。
const reasoningText = computed(() => String(props.message?.reasoning || '').trim())
const reasoningOpen = ref(false)
watch(
  () => props.message?.streaming,
  (streaming) => {
    // 进入流式时展开、结束时折叠（仅在 reasoning 存在时有意义）
    if (reasoningText.value) reasoningOpen.value = streaming === true
  },
  { immediate: true }
)

// 消息底栏的 usage/耗时摘要：从 meta.usage / meta.elapsed_ms 读（历史消息刷新后仍在）
const usageMeta = computed(() => props.message?.meta?.usage || null)
const elapsedMs = computed(() => Number(props.message?.meta?.elapsed_ms) || 0)
const usageSummary = computed(() => {
  const u = usageMeta.value
  const elapsed = elapsedMs.value
  if (!u && !elapsed) return ''
  const parts = []
  if (u && Number(u.total_tokens) > 0) {
    parts.push(`${formatTokens(u.total_tokens)} tokens`)
  }
  if (elapsed > 0) {
    const sec = Math.max(1, Math.round(elapsed / 1000))
    parts.push(`${sec}s`)
  }
  return parts.join(' · ')
})

function formatTokens(n) {
  const num = Number(n) || 0
  if (num < 1000) return String(num)
  if (num < 10000) return `${(num / 1000).toFixed(1)}k`
  return `${Math.round(num / 1000)}k`
}

// 规范化行内容：tokenizeInline 可能返回字符串（纯文本）或 segments 数组。
// 统一成 segments 数组，方便模板 v-for 渲染。
function normalizeSegments(line) {
  if (line == null) return []
  if (typeof line === 'string') return [{ type: 'text', text: line }]
  if (Array.isArray(line)) return line
  return [{ type: 'text', text: String(line) }]
}
</script>

<template>
  <article :class="['message', message.role]">
    <div class="message-role">
      {{ message.role === 'user' ? '你' : message.role === 'assistant' ? assistantName : '系统' }}
    </div>

    <!-- 思考中占位指示器：发送后到首个 text_delta/tool_call_start 之间可见 -->
    <div v-if="isThinkingPlaceholder" class="message-thinking">
      <span class="thinking-dots" aria-hidden="true"><span></span><span></span><span></span></span>
      <span class="thinking-text">{{ runStatus || '正在思考…' }}</span>
    </div>

    <!-- 思维链折叠块（阶段 3，provider 支持时才有内容；与正文分块渲染互不污染） -->
    <details v-if="reasoningText" class="message-reasoning" :open="reasoningOpen" @toggle="reasoningOpen = $event.target.open">
      <summary>
        <ArtIcon name="assistant" tone="pearl" :size="13" />
        <span>思考过程</span>
      </summary>
      <p class="reasoning-body">{{ reasoningText }}</p>
    </details>

    <div
      v-if="message.content?.trim()"
      class="message-content"
    >
      <template v-for="(block, blockIndex) in message.blocks" :key="blockIndex">
        <h4 v-if="block.type === 'heading'" :class="`message-heading level-${block.level}`">
          <template v-for="(seg, segIndex) in normalizeSegments(block.lines[0])" :key="segIndex">
            <strong v-if="seg.type === 'bold'">{{ seg.text }}</strong>
            <code v-else-if="seg.type === 'code'">{{ seg.text }}</code>
            <a v-else-if="seg.type === 'link'" :href="seg.href" target="_blank" rel="noopener">{{ seg.text }}</a>
            <span v-else>{{ seg.text }}</span>
          </template>
        </h4>
        <blockquote v-else-if="block.type === 'quote'" class="message-quote">
          <template v-for="(seg, segIndex) in normalizeSegments(block.lines[0])" :key="segIndex">
            <strong v-if="seg.type === 'bold'">{{ seg.text }}</strong>
            <code v-else-if="seg.type === 'code'">{{ seg.text }}</code>
            <a v-else-if="seg.type === 'link'" :href="seg.href" target="_blank" rel="noopener">{{ seg.text }}</a>
            <span v-else>{{ seg.text }}</span>
          </template>
        </blockquote>
        <ol v-else-if="block.type === 'ordered'" class="message-ordered">
          <li v-for="(item, itemIndex) in block.items" :key="itemIndex">
            <template v-for="(seg, segIndex) in normalizeSegments(item)" :key="segIndex">
              <strong v-if="seg.type === 'bold'">{{ seg.text }}</strong>
              <code v-else-if="seg.type === 'code'">{{ seg.text }}</code>
              <a v-else-if="seg.type === 'link'" :href="seg.href" target="_blank" rel="noopener">{{ seg.text }}</a>
              <span v-else>{{ seg.text }}</span>
            </template>
          </li>
        </ol>
        <ul v-else-if="block.type === 'list'" class="message-list">
          <li v-for="(item, itemIndex) in block.items" :key="itemIndex">
            <template v-for="(seg, segIndex) in normalizeSegments(item)" :key="segIndex">
              <strong v-if="seg.type === 'bold'">{{ seg.text }}</strong>
              <code v-else-if="seg.type === 'code'">{{ seg.text }}</code>
              <a v-else-if="seg.type === 'link'" :href="seg.href" target="_blank" rel="noopener">{{ seg.text }}</a>
              <span v-else>{{ seg.text }}</span>
            </template>
          </li>
        </ul>
        <p v-else-if="block.type === 'paragraph'" class="message-paragraph">
          <template v-for="(line, lineIndex) in block.lines" :key="lineIndex">
            <span>
              <template v-for="(seg, segIndex) in normalizeSegments(line)" :key="segIndex">
                <strong v-if="seg.type === 'bold'">{{ seg.text }}</strong>
                <code v-else-if="seg.type === 'code'">{{ seg.text }}</code>
                <a v-else-if="seg.type === 'link'" :href="seg.href" target="_blank" rel="noopener">{{ seg.text }}</a>
                <span v-else>{{ seg.text }}</span>
              </template>
            </span>
            <br v-if="lineIndex < block.lines.length - 1" />
          </template>
        </p>
      </template>
    </div>

    <!-- 阶段 C2：工作清单（实时进度，agent 调用 update_work_plan 产出） -->
    <WorkPlanCard v-if="message.work_plan?.length" :items="message.work_plan" />

    <div v-if="message.tool_results?.length" class="tool-results">
      <ToolCallCard
        v-for="(tool, toolIndex) in message.tool_results"
        :key="toolIndex"
        :tool="tool"
      />
      <div v-if="actionSummary.length" class="action-summary">
        <span
          v-for="(chip, chipIndex) in actionSummary"
          :key="chipIndex"
          class="action-chip"
          :class="`tone-${chip.tone}`"
        >
          {{ chip.label }}<template v-if="chip.count > 1"> ×{{ chip.count }}</template>
        </span>
      </div>
    </div>

    <!-- 阶段 C1：计划卡片（plan 模式 agent 调用 propose_plan 产出，可编辑/批准/拒绝） -->
    <PlanCard
      v-if="message.plan_card"
      :plan-card="message.plan_card"
      :message-id="message.id"
      :busy="busy"
      @approve="$emit('approve-plan', $event)"
      @reject="$emit('reject-plan', $event)"
    />

    <div v-for="action in message.pending_actions || []" :key="action.id" class="pending-card">
      <div class="pending-head">
        <div>
          <strong>危险操作待确认</strong>
          <p>{{ pendingStatusText(action) }}</p>
        </div>
        <span class="danger-dot"></span>
      </div>
      <p class="pending-summary">{{ action.summary }}</p>
      <ul v-if="action.preview?.length" class="pending-preview">
        <li v-for="(line, previewIndex) in action.preview" :key="previewIndex">{{ line }}</li>
      </ul>
      <div class="pending-actions">
        <template v-if="!isTerminalStatus(action)">
          <!-- 阶段 D1：「以后都允许」勾选——勾选后点首次确认会先创建 grant，同类操作不再弹确认卡 -->
          <label v-if="!pendingTokens[action.id]" class="grant-toggle" :title="`勾选后，以后调用 ${action.action_type} 类操作不再询问`">
            <input type="checkbox" v-model="grantChecked[action.id]" />
            <span>以后都允许「{{ action.action_type }}」</span>
          </label>
          <button v-if="!pendingTokens[action.id]" class="ghost" :disabled="busy" @click="onFirstConfirm(action)">
            第一次确认
          </button>
          <button v-else class="danger second-confirm" style="display:block;width:100%;margin-top:6px" :disabled="busy || !!secondConfirmLocked[action.id]" @click="$emit('second-confirm', action)">
            我已理解影响，执行
          </button>
          <button class="ghost reject-action" :disabled="busy" @click="$emit('reject', action)">
            拒绝
          </button>
        </template>
      </div>
    </div>

    <div v-if="message.role === 'assistant' && message.content?.trim()" class="message-actions">
      <button type="button" class="ghost compact copy-action" aria-label="复制这条回复" @click="copyMessage">
        复制
      </button>
    </div>

    <!-- 底栏：本次 run 的 token 消耗与耗时（done 后定格，历史消息刷新后仍可见） -->
    <div v-if="usageSummary && message.role === 'assistant'" class="message-usage">{{ usageSummary }}</div>
  </article>
</template>

<style scoped>
/* 阶段 D1：「以后都允许」勾选条 */
.grant-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  font-size: 11px;
  color: var(--text-soft);
  cursor: pointer;
}

.grant-toggle input {
  cursor: pointer;
}

.action-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}

.action-chip {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  font-size: 11px;
  font-weight: 700;
  background: var(--surface-2);
  color: var(--text-soft);
}
.action-chip.tone-ok {
  color: var(--accent-hover);
  background: var(--accent-soft);
}
.action-chip.tone-fail {
  color: var(--pri-high);
  background: color-mix(in srgb, var(--danger) 14%, transparent);
}
.action-chip.tone-pending {
  color: var(--warn, #b45309);
  background: color-mix(in srgb, var(--warn, #d97706) 14%, transparent);
}

.message-actions {
  position: absolute;
  top: 6px;
  right: 8px;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s ease;
}

.message:hover .message-actions,
.message:focus-within .message-actions {
  opacity: 1;
  pointer-events: auto;
}

.copy-action {
  background: var(--surface-solid);
  box-shadow: var(--shadow-sm);
}

/* 思考中占位指示器：三点跳动 + 状态文案 */
.message-thinking {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 2px;
  font-size: 13px;
  color: var(--text-soft);
}
.thinking-dots {
  display: inline-flex;
  gap: 3px;
}
.thinking-dots span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  animation: thinking-bounce 1.2s ease-in-out infinite;
}
.thinking-dots span:nth-child(2) { animation-delay: 0.15s; }
.thinking-dots span:nth-child(3) { animation-delay: 0.3s; }
@keyframes thinking-bounce {
  0%, 60%, 100% { opacity: 0.3; transform: translateY(0); }
  30% { opacity: 1; transform: translateY(-3px); }
}
@media (prefers-reduced-motion: reduce) {
  .thinking-dots span { animation: none; opacity: 0.6; }
}
.thinking-text {
  font-weight: 500;
}

/* 思维链折叠块（默认折叠，斜体灰字） */
.message-reasoning {
  margin: 2px 0 6px;
  border-left: 2px solid var(--border);
  padding-left: 10px;
}
.message-reasoning summary {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-soft);
  font-weight: 600;
  list-style: none;
}
.message-reasoning summary::-webkit-details-marker { display: none; }
.reasoning-body {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-faint, var(--text-soft));
  font-style: italic;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 底栏：token · 耗时（小号灰字） */
.message-usage {
  margin-top: 6px;
  font-size: 11px;
  color: var(--text-faint, var(--text-soft));
  font-variant-numeric: tabular-nums;
}
</style>
