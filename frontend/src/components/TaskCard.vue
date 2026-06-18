<script setup>
import { computed } from 'vue'

const props = defineProps({
  task: { type: Object, required: true },
})
const emit = defineEmits(['click'])

const priColor = computed(
  () =>
    ({
      高: 'var(--pri-high)',
      中: 'var(--pri-mid)',
      低: 'var(--pri-low)',
    })[props.task.priority] || 'var(--pri-mid)'
)

const dueLabel = computed(() => {
  if (!props.task.due_date) return ''
  const d = new Date(props.task.due_date)
  return `${d.getMonth() + 1}/${d.getDate()}`
})

const isOverdue = computed(() => {
  if (!props.task.due_date || props.task.status === '完成') return false
  return new Date(props.task.due_date) < new Date(new Date().toDateString())
})
</script>

<template>
  <div class="task-card card" @click="emit('click', task)">
    <div class="row">
      <span class="title">{{ task.title }}</span>
      <span class="pri-dot" :style="{ background: priColor }" :title="`优先级：${task.priority}`"></span>
    </div>
    <div v-if="dueLabel || task.status === '进行中' || task.files?.length" class="row meta">
      <span v-if="dueLabel" class="due" :class="{ overdue: isOverdue }">⏰ {{ dueLabel }}</span>
      <span v-if="task.status === '进行中'" class="progress">
        <span class="bar"><span class="fill" :style="{ width: task.progress + '%' }"></span></span>
        {{ task.progress }}%
      </span>
      <span v-if="task.files?.length">📎 {{ task.files.length }}</span>
    </div>
  </div>
</template>

<style scoped>
.task-card {
  cursor: pointer;
  padding: 12px 14px;
  margin-bottom: 10px;
  transition: box-shadow 0.2s ease, transform 0.08s ease;
}
.task-card:hover {
  box-shadow: var(--shadow-lg);
}
.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.title {
  font-weight: 500;
  word-break: break-word;
}
.pri-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.meta {
  margin-top: 8px;
  color: var(--text-soft);
  font-size: 12.5px;
  gap: 14px;
}
.due.overdue {
  color: var(--pri-high);
  font-weight: 500;
}
.progress {
  display: flex;
  align-items: center;
  gap: 6px;
}
.bar {
  display: inline-block;
  width: 38px;
  height: 5px;
  background: var(--surface-2);
  border-radius: 3px;
  overflow: hidden;
}
.fill {
  display: block;
  height: 100%;
  background: var(--accent);
}
</style>
