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
  if (payload.due_date) payload.due_date = payload.due_date + 'T23:59:59'
  emit('save', payload)
}
</script>

<template>
  <form class="task-form" @submit.prevent="save">
    <div class="field">
      <label>标题 <span class="required">*</span></label>
      <input v-model="form.title" placeholder="要做什么？" autofocus />
    </div>

    <div class="grid">
      <div class="field">
        <label>截止日期</label>
        <input type="date" v-model="form.due_date" />
      </div>
      <div class="field">
        <label>优先级</label>
        <select v-model="form.priority">
          <option value="高">高</option>
          <option value="中">中</option>
          <option value="低">低</option>
        </select>
      </div>
      <div class="field">
        <label>状态</label>
        <select v-model="form.status">
          <option>待办</option>
          <option>进行中</option>
          <option>完成</option>
        </select>
      </div>
      <div class="field">
        <label>进度 {{ form.progress }}%</label>
        <input type="range" min="0" max="100" v-model.number="form.progress" />
      </div>
    </div>

    <div class="field">
      <label>备注</label>
      <textarea v-model="form.notes" rows="3" placeholder="补充说明…"></textarea>
    </div>

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
  gap: 16px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

label {
  font-size: 13px;
  color: var(--text-soft);
  font-weight: 600;
}

.required {
  color: var(--pri-high);
}

.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 4px;
}

@media (max-width: 520px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
