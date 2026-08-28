<script setup>
// 单个工具调用结果卡片：替代原始 JSON dump，按状态/工具名/参数摘要/可折叠结果呈现。
// 视觉样式复用父级 .assistant-shell 命名空间（AssistantView 全局样式块）。
import { computed, ref } from 'vue'
import ArtIcon from '../../components/ArtIcon.vue'

const props = defineProps({
  tool: { type: Object, required: true }, // {tool, args, result}
})

// 工具名 → 中文友好名映射；未命中显示原始名（MCP 工具特化处理）
const TOOL_LABELS = {
  list_tasks: '查看任务', create_task: '创建任务', list_reminders: '查看提醒',
  create_reminder: '创建提醒', list_files: '查看资料', create_note_file: '创建资料',
  create_subtask: '创建子任务', create_subtasks: '创建子任务', list_subtasks: '查看子任务',
  attach_file_to_task: '关联资料', save_attachment_to_library: '保存附件',
  list_day_schedule: '查看日程', list_month_schedule: '查看月度日程', assign_task_to_day: '安排日程',
  list_habits: '查看习惯', create_habit: '创建习惯', check_in_habit: '习惯打卡',
  list_journal_entries: '查看日记', write_journal: '写日记',
  list_goals: '查看目标', create_goal: '创建目标', update_kr_progress: '更新 KR 进度',
  start_timer: '开始计时', stop_timer: '停止计时',
  update_task: '更新任务', update_file_notes: '更新资料备注',
  detach_file_from_task: '取消资料关联', delete_task: '删除任务', delete_file: '删除资料',
  bulk_update_tasks: '批量更新任务', bulk_delete_tasks: '批量删除任务',
  bulk_delete_files: '批量删除资料', empty_trash: '清空回收站',
  import_web_resources: '导入联网资料',
  update_schedule_entry: '更新日程', delete_schedule_entry: '删除日程',
  bulk_assign_tasks_to_days: '批量安排日程', auto_plan_tasks: '自动排程',
  create_skill: '创建 Skill', create_mcp_server: '配置 MCP',
}

function friendlyName(name) {
  const n = String(name || '')
  if (TOOL_LABELS[n]) return TOOL_LABELS[n]
  if (n.startsWith('mcp__')) {
    // mcp__s1__echo → MCP·echo
    const parts = n.split('__')
    return `MCP·${parts[parts.length - 1] || n}`
  }
  return n
}

const result = computed(() => props.tool?.result || {})
// 运行中（_running）优先于一切：tool_call_start 建卡时 result 恰为 {ok:false,pending:true}，
// 此前会被误判成「待确认」。这里用显式 _running 标志覆盖，呈现蓝色「执行中」+ 旋转图标。
const isRunning = computed(() => props.tool?._running === true)
const isOk = computed(() => result.value?.ok === true)
const isSkipped = computed(() => isOk.value && result.value?.skipped === true)
const isPending = computed(() => !isRunning.value && result.value?.pending === true)
const isFailed = computed(() => !isRunning.value && !isOk.value && !isPending.value)

const statusTone = computed(() => {
  if (isRunning.value) return 'aqua'
  if (isPending.value) return 'amber'
  if (isFailed.value) return 'coral'
  if (isSkipped.value) return 'pearl'
  return 'aqua'
})
const statusLabel = computed(() => {
  if (isRunning.value) return '执行中'
  if (isPending.value) return '待确认'
  if (isFailed.value) return '失败'
  if (isSkipped.value) return '跳过'
  return '成功'
})
const statusIcon = computed(() => {
  if (isRunning.value) return 'refresh'
  if (isPending.value) return 'refresh'
  if (isFailed.value) return 'close'
  return 'check'
})

// 参数摘要：取关键字段拼成一行
function argSummary(args) {
  const a = args || {}
  const keys = ['title', 'name', 'date', 'task_id', 'file_id', 'habit_id', 'goal_id', 'content', 'notes', 'query']
  const parts = []
  for (const k of keys) {
    if (a[k] !== undefined && a[k] !== null && a[k] !== '') {
      let v = String(a[k])
      if (v.length > 40) v = v.slice(0, 40) + '…'
      parts.push(`${k}:${v}`)
    }
  }
  if (!parts.length && Array.isArray(a.task_ids)) parts.push(`${a.task_ids.length} 个任务`)
  if (!parts.length && Array.isArray(a.assignments)) parts.push(`${a.assignments.length} 项安排`)
  const summary = parts.slice(0, 3).join(' · ')
  return summary.length > 60 ? summary.slice(0, 60) + '…' : summary
}

// 结果摘要文本（折叠态可见的一行）
const resultPreview = computed(() => {
  const r = result.value
  if (isFailed.value) return r?.error || '执行失败'
  if (isPending.value) return r?.error || '等待用户确认'
  if (isSkipped.value) return r?.message || '已跳过重复调用'
  if (r?.message) return r.message
  if (r?.text) return String(r.text).slice(0, 80)
  if (r?.task?.title) return `#${r.task.id} ${r.task.title}`
  if (r?.file?.original_name) return `#${r.file.id} ${r.file.original_name}`
  return '已完成'
})

// 失败/pending 默认展开，成功默认折叠
const open = ref(isFailed.value || isPending.value)
const rawJson = computed(() => JSON.stringify(props.tool, null, 2))
</script>

<template>
  <div class="tool-call-card" :class="[`tone-${statusTone}`, { 'is-running': isRunning }]">
    <button type="button" class="tool-call-head" :aria-expanded="open" @click="open = !open">
      <ArtIcon :name="statusIcon" :tone="statusTone" :size="15" :class="{ spin: isRunning }" />
      <span class="tool-call-name">{{ friendlyName(tool.tool) }}</span>
      <span v-if="argSummary(tool.args)" class="tool-call-args">{{ argSummary(tool.args) }}</span>
      <span class="tool-call-status" :class="`tone-${statusTone}`">{{ statusLabel }}</span>
      <ArtIcon :name="open ? 'expand' : 'expand'" :size="13" class="tool-call-chev" tone="pearl" />
    </button>
    <div v-show="open" class="tool-call-body">
      <p class="tool-call-preview" :class="{ failed: isFailed, pending: isPending }">{{ resultPreview }}</p>
      <details class="tool-call-raw">
        <summary>原始数据</summary>
        <pre>{{ rawJson }}</pre>
      </details>
    </div>
  </div>
</template>

<style scoped>
.tool-call-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-xs);
  background: var(--surface);
  overflow: hidden;
}

/* 运行中：图标持续旋转，强调"正在执行"而非"待确认" */
.tool-call-card.is-running {
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  background: color-mix(in srgb, var(--accent) 5%, transparent);
}
.tool-call-card.is-running .tool-call-status.tone-aqua {
  color: var(--accent-hover);
  background: var(--accent-soft);
}

.spin {
  animation: tool-call-spin 0.9s linear infinite;
}
@keyframes tool-call-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
@media (prefers-reduced-motion: reduce) {
  .spin { animation: none; }
}

.tool-call-card.tone-coral {
  border-color: color-mix(in srgb, var(--danger) 38%, transparent);
  background: color-mix(in srgb, var(--danger) 6%, transparent);
}
.tool-call-card.tone-amber {
  border-color: color-mix(in srgb, var(--warn, #d97706) 38%, transparent);
  background: color-mix(in srgb, var(--warn, #d97706) 8%, transparent);
}

.tool-call-head {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 10px;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.tool-call-name {
  font-size: 13px;
  font-weight: 800;
  color: var(--text);
  flex-shrink: 0;
}

.tool-call-args {
  min-width: 0;
  flex: 1;
  font-size: 12px;
  color: var(--text-soft);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-call-status {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  font-size: 11px;
  font-weight: 700;
  background: var(--surface-2);
  color: var(--text-soft);
}
.tool-call-status.tone-aqua { color: var(--accent-hover); background: var(--accent-soft); }
.tool-call-status.tone-coral { color: var(--pri-high); background: color-mix(in srgb, var(--danger) 14%, transparent); }
.tool-call-status.tone-amber { color: var(--warn, #b45309); background: color-mix(in srgb, var(--warn, #d97706) 14%, transparent); }
.tool-call-status.tone-pearl { color: var(--text-soft); }

.tool-call-chev {
  flex-shrink: 0;
  transition: transform 0.15s ease;
}
.tool-call-head[aria-expanded="true"] .tool-call-chev {
  transform: rotate(180deg);
}

.tool-call-body {
  padding: 0 10px 9px;
  display: grid;
  gap: 6px;
}

.tool-call-preview {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text);
}
.tool-call-preview.failed { color: var(--pri-high); font-weight: 600; }
.tool-call-preview.pending { color: var(--warn, #b45309); font-weight: 600; }

.tool-call-raw summary {
  cursor: pointer;
  color: var(--text-soft);
  font-size: 11px;
}

.tool-call-raw pre {
  max-height: 140px;
  margin: 5px 0 0;
  overflow: auto;
  padding: 8px;
  border-radius: var(--radius-xs);
  background: var(--surface-2);
  color: var(--text);
  font-size: 11px;
}
</style>
