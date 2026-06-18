<script setup>
import { reactive, watch } from 'vue'

const props = defineProps({
  modelValue: { type: Object, default: null },
})
const emit = defineEmits(['save', 'cancel'])

const form = reactive({
  title: '',
  notes: '',
  due_date: '',
  priority: '中',
  status: '待办',
  progress: 0,
})

watch(
  () => props.modelValue,
  (v) => {
    if (v) {
      form.title = v.title || ''
      form.notes = v.notes || ''
      form.due_date = v.due_date ? v.due_date.slice(0, 10) : ''
      form.priority = v.priority || '中'
      form.status = v.status || '待办'
      form.progress = v.progress ?? 0
    } else {
      Object.assign(form, {
        title: '',
        notes: '',
        due_date: '',
        priority: '中',
        status: '待办',
        progress: 0,
      })
    }
  },
  { immediate: true }
)

function save() {
  if (!form.title.trim()) return
  const payload = { ...form }
  // 日期转成当天 23:59:59，对齐后端 datetime
  if (payload.due_date) payload.due_date = payload.due_date + 'T23:59:59'
  emit('save', payload)
}
</script>

<template>
  <form class="task-form" @submit.prevent="save">
    <label>标题 <span style="color: var(--pri-high)">*</span></label>
    <input v-model="form.title" placeholder="要做什么？" autofocus />

    <div class="grid">
      <div>
        <label>截止日期</label>
        <input type="date" v-model="form.due_date" />
      </div>
      <div>
        <label>优先级</label>
        <select v-model="form.priority">
          <option>高</option>
          <option>中</option>
          <option>低</option>
        </select>
      </div>
      <div>
        <label>状态</label>
        <select v-model="form.status">
          <option>待办</option>
          <option>进行中</option>
          <option>完成</option>
        </select>
      </div>
      <div>
        <label>进度 {{ form.progress }}%</label>
        <input type="range" min="0" max="100" v-model.number="form.progress" />
      </div>
    </div>

    <label>备注</label>
    <textarea v-model="form.notes" rows="3" placeholder="补充说明…"></textarea>

    <div class="actions">
      <button type="button" class="ghost" @click="emit('cancel')">取消</button>
      <button type="submit">保存</button>
    </div>
  </form>
</template>

<style scoped>
.task-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
label {
  font-size: 13px;
  color: var(--text-soft);
  margin-bottom: -4px;
}
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}
input[type='range'] {
  padding: 0;
}
</style>
