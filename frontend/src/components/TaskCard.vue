<script setup>
import { computed, inject, ref } from 'vue'
import ArtIcon from './ArtIcon.vue'
import ContextMenu from './ContextMenu.vue'
import { deleteTask, restoreTask, updateTask } from '../api/tasks'
import { startTimer } from '../api/timer'

const props = defineProps({
  task: { type: Object, required: true },
})
const emit = defineEmits(['click', 'quick-status'])

// 全局 toast 与应用内确认对话框(App.vue provide);提供降级以防组件树外调用
const toast = inject('toast', { success: () => {}, error: () => {}, info: () => {}, undo: () => {} })
const confirmDialog = inject('confirm-dialog', (o) => Promise.resolve(window.confirm(o.message || '')))

const priMeta = computed(() => {
  const map = {
    高: { color: 'var(--pri-high)', bg: 'color-mix(in srgb, var(--pri-high) 12%, transparent)' },
    中: { color: 'var(--pri-mid)', bg: 'color-mix(in srgb, var(--pri-mid) 15%, transparent)' },
    低: { color: 'var(--pri-low)', bg: 'color-mix(in srgb, var(--pri-low) 12%, transparent)' },
  }
  return map[props.task.priority] || map['中']
})

const dueLabel = computed(() => {
  if (!props.task.due_date) return ''
  const d = new Date(props.task.due_date)
  return `${d.getMonth() + 1}/${d.getDate()}`
})

const isOverdue = computed(() => {
  if (!props.task.due_date || props.task.status === '完成') return false
  return new Date(props.task.due_date) < new Date(new Date().toDateString())
})

const subDoneCount = computed(
  () => (props.task.subtasks || []).filter((s) => s.done).length
)

const subPct = computed(() => {
  const all = props.task.subtasks || []
  if (!all.length) return 0
  return Math.round((subDoneCount.value / all.length) * 100)
})

// 悬停快捷状态切换：按当前状态推进到下一列，点击不打开弹窗
const NEXT_STATUS = {
  待办: { status: '进行中', icon: 'chevron-right', tone: 'aqua', label: '开始推进' },
  进行中: { status: '完成', icon: 'check', tone: 'mint', label: '标记完成' },
  完成: { status: '待办', icon: 'restore', tone: 'sand', label: '重新打开' },
}
const nextMeta = computed(() => NEXT_STATUS[props.task.status] || NEXT_STATUS['待办'])

// ---- 右键菜单 ----
// 改动直接调任务 API，再经 tasks:refresh 事件让 App 静默刷新列表（父链路 BoardView 无需新增转发）
const menuOpen = ref(false)
const menuX = ref(0)
const menuY = ref(0)

function toIso(d) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
function isoAfter(days) {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return toIso(d)
}
// 下周一：今天周一也算下一周；(8 - 周几) % 7 落在 1..7，周日(0)时为 1
function nextMondayIso() {
  const d = new Date()
  d.setDate(d.getDate() + (((8 - d.getDay()) % 7) || 7))
  return toIso(d)
}

const menuItems = computed(() => {
  const t = props.task
  const due = (t.due_date || '').slice(0, 10)
  const advance =
    t.status === '完成'
      ? { key: 'reopen', label: '重新打开为待办', icon: 'restore' }
      : t.status === '进行中'
        ? { key: 'advance', label: '标为完成', icon: 'check' }
        : { key: 'advance', label: '标为进行中', icon: 'chevron-right' }
  return [
    { key: 'focus', label: '开始专注', icon: 'priority' },
    { separator: true },
    advance,
    {
      key: 'due',
      label: '改期',
      icon: 'calendar',
      children: [
        { key: 'due-today', label: '今天截止', active: due === isoAfter(0) },
        { key: 'due-tomorrow', label: '明天截止', active: due === isoAfter(1) },
        { key: 'due-next-monday', label: '下周一截止', active: due === nextMondayIso() },
        { key: 'due-clear', label: '清除截止', active: !due },
      ],
    },
    {
      key: 'pri',
      label: '设优先级',
      icon: 'priority',
      children: [
        { key: 'pri-高', label: '高', active: t.priority === '高' },
        { key: 'pri-中', label: '中', active: t.priority === '中' },
        { key: 'pri-低', label: '低', active: t.priority === '低' },
      ],
    },
    { separator: true },
    { key: 'delete', label: '删除', icon: 'trash', danger: true },
  ]
})

function onContextMenu(e) {
  menuX.value = e.clientX
  menuY.value = e.clientY
  menuOpen.value = true
}

function notifyChanged() {
  window.dispatchEvent(new CustomEvent('tasks:refresh'))
}

async function applyPatch(patch) {
  try {
    await updateTask(props.task.id, patch)
    notifyChanged()
  } catch (e) {
    toast.error(`操作失败：${e.message}`)
  }
}

async function onMenuSelect(item) {
  switch (item.key) {
    case 'focus':
      await startFocus()
      break
    case 'advance':
      await applyPatch({ status: props.task.status === '进行中' ? '完成' : '进行中' })
      break
    case 'reopen':
      await applyPatch({ status: '待办' })
      break
    case 'due-today':
      await applyPatch({ due_date: isoAfter(0) })
      break
    case 'due-tomorrow':
      await applyPatch({ due_date: isoAfter(1) })
      break
    case 'due-next-monday':
      await applyPatch({ due_date: nextMondayIso() })
      break
    case 'due-clear':
      await applyPatch({ due_date: null })
      break
    case 'pri-高':
    case 'pri-中':
    case 'pri-低':
      await applyPatch({ priority: item.key.slice(4) })
      break
    case 'delete':
      await removeSelf()
      break
  }
}

// 开始专注：调计时接口并 toast，再派 focus:start 事件让 FocusTimer 同步状态（避免组件间硬耦合）
async function startFocus() {
  const t = props.task
  try {
    await startTimer(t.id)
    toast.success(`已开始专注《${t.title}》`)
    window.dispatchEvent(new CustomEvent('focus:start', { detail: t }))
  } catch (e) {
    toast.error(`开始专注失败：${e.message}`)
  }
}

// 与 App.vue 的删除流程一致：确认 → 移入回收站 → toast 可撤销恢复
async function removeSelf() {
  const t = props.task
  const ok = await confirmDialog({
    title: '移入回收站',
    message: `「${t.title}」将移入回收站，可在回收站恢复。`,
    confirmText: '移入回收站',
  })
  if (!ok) return
  try {
    await deleteTask(t.id)
    notifyChanged()
    toast.undo(`已将「${t.title}」移入回收站`, async () => {
      await restoreTask(t.id)
      notifyChanged()
    })
  } catch (e) {
    toast.error(`删除失败：${e.message}`)
  }
}

</script>

<template>
  <article
    class="task-card"
    tabindex="0"
    role="button"
    :aria-label="`任务：${task.title}`"
    @click="emit('click', task)"
    @keydown.enter.prevent="emit('click', task)"
    @keydown.space.prevent="emit('click', task)"
    @contextmenu.prevent="onContextMenu"
  >
    <div class="card-glow" :style="{ background: priMeta.color }"></div>
    <div class="card-inner">
      <div class="row main">
        <span class="title">{{ task.title }}</span>
        <span
          class="pri-badge"
          :style="{ color: priMeta.color, background: priMeta.bg }"
        >
          <ArtIcon name="priority" tone="coral" :size="15" />
          <span>{{ task.priority }}</span>
        </span>
      </div>
      <div class="row meta">
        <span v-if="dueLabel" class="due" :class="{ overdue: isOverdue }">
          <ArtIcon name="calendar" :tone="isOverdue ? 'coral' : 'pearl'" :size="15" />
          <span>{{ dueLabel }}</span>
        </span>
        <span v-if="task.status === '进行中'" class="progress">
          <span class="bar"><span class="fill" :style="{ width: task.progress + '%' }"></span></span>
          <span>{{ task.progress }}%</span>
        </span>
        <span v-if="task.subtasks?.length" class="subs-badge">
          <ArtIcon name="steps" tone="mint" :size="15" />
          <span>{{ subDoneCount }}/{{ task.subtasks.length }}</span>
        </span>
        <span v-if="task.files?.length" class="files">
          <ArtIcon name="file" tone="aqua" :size="15" />
          <span>{{ task.files.length }}</span>
        </span>
      </div>

      <div v-if="task.subtasks?.length" class="sub-summary">
        <span>{{ subDoneCount }}/{{ task.subtasks.length }} 子任务</span>
        <span class="sub-mini">
          <span class="sub-mini-fill" :style="{ width: subPct + '%' }"></span>
        </span>
        <span>{{ subPct }}%</span>
      </div>
    </div>
    <button
      class="quick-status"
      :title="`${nextMeta.label}（→ ${nextMeta.status}）`"
      :aria-label="nextMeta.label"
      tabindex="-1"
      @click.stop="emit('quick-status', task, nextMeta.status)"
    >
      <ArtIcon :name="nextMeta.icon" :tone="nextMeta.tone" :size="14" />
    </button>
    <ContextMenu
      :open="menuOpen"
      :x="menuX"
      :y="menuY"
      :items="menuItems"
      @close="menuOpen = false"
      @select="onMenuSelect"
    />
  </article>
</template>

<style scoped>
.task-card {
  position: relative;
  cursor: pointer;
  margin-bottom: 10px;
  border-radius: var(--radius-sm);
  background: var(--surface);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-xs), var(--shadow-inset);
  overflow: hidden;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
}

.task-card:hover {
  transform: translateY(-1px);
  border-color: var(--border-strong);
  box-shadow: var(--shadow-sm), var(--shadow-inset);
}

.task-card:active {
  transform: scale(0.99);
}

.task-card:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.card-glow {
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
  opacity: 0.95;
}

.card-inner {
  padding: 13px 14px 13px 15px;
  position: relative;
}

.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.main {
  align-items: flex-start;
}

.title {
  font-weight: 650;
  font-size: 15px;
  word-break: break-word;
  color: var(--text);
  line-height: 1.5;
  flex: 1;
  letter-spacing: 0;
}

.pri-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 700;
  padding: 3px 9px;
  border-radius: var(--radius-pill);
  flex-shrink: 0;
  margin-top: 1px;
}

.meta {
  margin-top: 11px;
  color: var(--text-soft);
  font-size: 12px;
  gap: 14px;
  flex-wrap: wrap;
}

.due,
.files {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.due.overdue {
  color: var(--pri-high);
  font-weight: 600;
}

.progress {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.bar {
  display: inline-block;
  width: 44px;
  height: 5px;
  background: var(--surface-3);
  border-radius: var(--radius-pill);
  overflow: hidden;
  box-shadow: inset 0 1px 2px color-mix(in srgb, var(--overlay-bg) 20%, transparent);
}

.fill {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--sea-300));
  border-radius: var(--radius-pill);
  transition: width 0.5s ease;
}

/* 子任务完成度徽标（常驻 meta 行） */
.subs-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 9px;
  border-radius: var(--radius-pill);
  background: var(--accent-soft);
  color: var(--accent-hover);
  font-weight: 700;
  border: 1px solid var(--border);
  box-shadow: var(--shadow-inset);
}

.sub-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  color: var(--text-soft);
  font-size: 12px;
}

.sub-mini {
  flex: 1;
  min-width: 52px;
  height: 5px;
  border-radius: var(--radius-pill);
  background: var(--surface-3);
  overflow: hidden;
  box-shadow: inset 0 1px 2px color-mix(in srgb, var(--overlay-bg) 20%, transparent);
}

.sub-mini-fill {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--sea-300));
  border-radius: var(--radius-pill);
  transition: width 0.5s ease;
}

/* 悬停浮现的快捷状态切换（待办→进行中→完成→待办） */
.quick-status {
  position: absolute;
  right: 10px;
  bottom: 10px;
  z-index: 2;
  width: 28px;
  height: 28px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--surface-2);
  border: 1px solid var(--border);
  color: var(--text-soft);
  box-shadow: var(--shadow-xs);
  opacity: 0;
  transform: translateY(3px);
  transition: opacity 0.15s ease, transform 0.15s ease, background 0.15s ease,
    border-color 0.15s ease;
}

.task-card:hover .quick-status,
.quick-status:focus-visible {
  opacity: 1;
  transform: none;
}

.quick-status:hover {
  background: var(--accent-soft);
  border-color: var(--accent);
  box-shadow: var(--shadow-xs);
}
</style>
