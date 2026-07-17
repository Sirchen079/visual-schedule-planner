<script setup>
import { computed } from 'vue'
import ArtIcon from './ArtIcon.vue'

const props = defineProps({
  task: { type: Object, required: true },
})
const emit = defineEmits(['click', 'quick-status'])

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
