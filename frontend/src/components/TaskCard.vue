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
        <span v-if="task.subtasks?.length" class="subs">
          <span class="meta-icon">✓</span>
          <span>{{ subDoneCount }}/{{ task.subtasks.length }}</span>
        </span>
        <span v-if="task.files?.length" class="files">
          <span class="meta-icon">📎</span>
          <span>{{ task.files.length }}</span>
        </span>
      </div>
      <div v-if="task.subtasks?.length" class="sub-list">
        <div class="sub-item" v-for="s in task.subtasks" :key="s.id">
          <span class="sub-mark" :class="{ done: s.done }">{{ s.done ? '✓' : '' }}</span>
          <span class="sub-title" :class="{ done: s.done }">{{ s.title }}</span>
          <span v-if="s.completed_at" class="sub-time">{{ fmtTime(s.completed_at) }}</span>
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

.subs {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

/* hover 展开子任务：默认收起，悬停时展开 */
.sub-list {
  max-height: 0;
  overflow: hidden;
  opacity: 0;
  margin-top: 0;
  transition: max-height 0.32s ease, opacity 0.25s ease, margin-top 0.3s ease;
}

.task-card:hover .sub-list {
  max-height: 300px;
  opacity: 1;
  margin-top: 11px;
}

.sub-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 2px;
  font-size: 12.5px;
  border-top: 1px dashed var(--border);
}

.sub-item:first-child {
  border-top: none;
}

.sub-mark {
  width: 15px;
  height: 15px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 700;
  flex-shrink: 0;
  color: var(--text-muted);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-inset);
  transition: background 0.2s ease, border-color 0.2s ease;
}

.sub-mark.done {
  background: var(--pri-low);
  border-color: var(--pri-low);
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

.sub-time {
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
}
</style>
