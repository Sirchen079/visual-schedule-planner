<script setup>
import { computed } from 'vue'
import ArtIcon from './ArtIcon.vue'

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
  </div>
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
  font-size: 14.5px;
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
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.06);
}

.sub-mini-fill {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--sea-300));
  border-radius: var(--radius-pill);
  transition: width 0.5s ease;
}
</style>
