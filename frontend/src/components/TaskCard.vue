<script setup>
import { computed } from 'vue'

const props = defineProps({
  task: { type: Object, required: true },
})
const emit = defineEmits(['click'])

const priMeta = computed(() => {
  const map = {
    高: { color: 'var(--pri-high)', bg: 'rgba(242, 107, 122, 0.12)' },
    中: { color: 'var(--pri-mid)', bg: 'rgba(251, 191, 122, 0.15)' },
    低: { color: 'var(--pri-low)', bg: 'rgba(116, 230, 156, 0.12)' },
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

function fmtTime(t) {
  if (!t) return ''
  return new Date(t).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<template>
  <div class="task-card" @click="emit('click', task)">
    <div class="card-glow" :style="{ background: priMeta.color }"></div>
    <div class="card-inner">
      <div class="row main">
        <span class="title">{{ task.title }}</span>
        <span
          class="pri-badge"
          :style="{ color: priMeta.color, background: priMeta.bg }"
        >
          {{ task.priority }}
        </span>
      </div>
      <div class="row meta">
        <span v-if="dueLabel" class="due" :class="{ overdue: isOverdue }">
          <span class="meta-icon">⏰</span>
          <span>{{ dueLabel }}</span>
        </span>
        <span v-if="task.status === '进行中'" class="progress">
          <span class="bar"><span class="fill" :style="{ width: task.progress + '%' }"></span></span>
          <span>{{ task.progress }}%</span>
        </span>
        <span v-if="task.subtasks?.length" class="subs-badge">
          <span class="meta-icon">✅</span>
          <span>{{ subDoneCount }}/{{ task.subtasks.length }}</span>
        </span>
        <span v-if="task.files?.length" class="files">
          <span class="meta-icon">📎</span>
          <span>{{ task.files.length }}</span>
        </span>
      </div>

      <div v-if="task.subtasks?.length" class="sub-list">
        <div class="sub-head">
          <span class="sub-head-icon float-slow">🐚</span>
          <span class="sub-head-text">子任务进度</span>
          <span class="sub-head-pct">{{ subPct }}%</span>
          <span class="sub-mini">
            <span class="sub-mini-fill" :style="{ width: subPct + '%' }"></span>
          </span>
        </div>
        <div class="sub-item" v-for="s in task.subtasks" :key="s.id">
          <span class="sub-check" :class="{ done: s.done }">
            <span v-if="s.done">✓</span>
          </span>
          <span class="sub-title" :class="{ done: s.done }">{{ s.title }}</span>
          <span v-if="s.completed_at" class="sub-done-tag">
            <span>🕐</span><span>{{ fmtTime(s.completed_at) }}</span>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.task-card {
  position: relative;
  cursor: pointer;
  margin-bottom: 12px;
  border-radius: var(--radius-sm);
  background: var(--surface);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm), var(--shadow-inset);
  overflow: hidden;
  transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1),
    box-shadow 0.25s ease;
}

.task-card:hover {
  transform: translateY(-4px) rotate(0.3deg);
  box-shadow: var(--shadow-md), var(--shadow-inset);
}

.card-glow {
  position: absolute;
  top: 0;
  left: 0;
  width: 5px;
  height: 100%;
  opacity: 0.85;
  transition: width 0.25s ease;
}

.task-card:hover .card-glow {
  width: 7px;
}

.card-inner {
  padding: 14px 15px;
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
  font-weight: 500;
  font-size: 14.5px;
  word-break: break-word;
  color: var(--text);
  line-height: 1.5;
  flex: 1;
  letter-spacing: 0.01em;
}

.pri-badge {
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

.meta-icon {
  font-size: 11px;
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
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.05);
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

/* hover 展开子任务详情 */
.sub-list {
  max-height: 0;
  overflow: hidden;
  opacity: 0;
  margin-top: 0;
  transition: max-height 0.32s ease, opacity 0.25s ease, margin-top 0.3s ease;
}

.task-card:hover .sub-list {
  max-height: 340px;
  opacity: 1;
  margin-top: 12px;
}

.sub-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 11px;
  border-radius: var(--radius-xs);
  background: linear-gradient(135deg, var(--accent-soft), var(--surface-2));
  border: 1px solid var(--border);
  box-shadow: var(--shadow-inset);
  margin-bottom: 4px;
}

.sub-head-icon {
  font-size: 14px;
}

.sub-head-text {
  flex: 1;
  font-size: 11.5px;
  font-weight: 700;
  color: var(--text-soft);
}

.sub-head-pct {
  font-size: 12px;
  font-weight: 800;
  color: var(--accent-hover);
}

.sub-mini {
  width: 52px;
  height: 5px;
  border-radius: var(--radius-pill);
  background: var(--surface-3);
  overflow: hidden;
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.06);
}

.sub-mini-fill {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--sea-300));
  border-radius: var(--radius-pill);
  transition: width 0.5s ease;
}

.sub-item {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 6px 4px;
  font-size: 12.5px;
}

.sub-check {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 800;
  flex-shrink: 0;
  border: 1.5px solid var(--border-strong);
  color: transparent;
  background: var(--surface);
  box-shadow: var(--shadow-inset);
  transition: background 0.25s ease, border-color 0.25s ease;
}

.sub-check.done {
  background: linear-gradient(135deg, var(--foam-400), var(--foam-500));
  border-color: var(--foam-500);
  color: #fff;
}

.sub-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-soft);
}

.sub-title.done {
  text-decoration: line-through;
  color: var(--text-muted);
}

.sub-done-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 10.5px;
  font-weight: 600;
  color: var(--foam-500);
  background: rgba(116, 230, 156, 0.12);
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  border: 1px solid rgba(116, 230, 156, 0.25);
  flex-shrink: 0;
}
</style>
