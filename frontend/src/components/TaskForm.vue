<script setup>
import { reactive, ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: Object, default: null },
})
const emit = defineEmits(['save', 'cancel'])

const form = reactive({
  title: '',
  notes: '',
  start_date: '',
  end_date: '',
  due_date: '',
  priority: '中',
  status: '待办',
  progress: 0,
  tags: [],
})
const tagInput = ref('')

// 校验反馈：标题必填；开始日期不能晚于结束日期
const errors = reactive({ title: '', dateRange: '' })

watch(
  () => props.modelValue,
  (v) => {
    if (v) {
      form.title = v.title || ''
      form.notes = v.notes || ''
      form.start_date = v.start_date ? v.start_date.slice(0, 10) : ''
      form.end_date = v.end_date ? v.end_date.slice(0, 10) : ''
      form.due_date = v.due_date ? v.due_date.slice(0, 10) : ''
      form.priority = v.priority || '中'
      form.status = v.status || '待办'
      form.progress = v.progress ?? 0
      form.tags = (v.tags || []).map((t) => t.name)
    } else {
      Object.assign(form, {
        title: '',
        notes: '',
        start_date: '',
        end_date: '',
        due_date: '',
        priority: '中',
        status: '待办',
        progress: 0,
        tags: [],
      })
    }
    tagInput.value = ''
    errors.title = ''
    errors.dateRange = ''
  },
  { immediate: true }
)

// 输入修正后即时清除对应错误
watch(
  () => form.title,
  (v) => {
    if (v.trim()) errors.title = ''
  }
)
watch([() => form.start_date, () => form.end_date], () => {
  errors.dateRange = ''
})

function addTag() {
  const name = tagInput.value.trim()
  if (name && !form.tags.includes(name)) {
    form.tags.push(name)
  }
  tagInput.value = ''
}
function removeTag(i) {
  form.tags.splice(i, 1)
}

function save() {
  errors.title = form.title.trim() ? '' : '请填写任务标题'
  errors.dateRange =
    form.start_date && form.end_date && form.start_date > form.end_date
      ? '开始日期不能晚于结束日期'
      : ''
  if (errors.title || errors.dateRange) return
  const payload = { ...form }
  // 日期：空值传 null（后端 Optional），有值则带时间部分对齐到整天
  const dateFields = { start_date: 'T00:00:00', end_date: 'T23:59:59', due_date: 'T23:59:59' }
  for (const [k, suffix] of Object.entries(dateFields)) {
    payload[k] = payload[k] ? payload[k] + suffix : null
  }
  emit('save', payload)
}
</script>

<template>
  <form
    class="task-form"
    @submit.prevent="save"
    @keydown.ctrl.enter.prevent="save"
    @keydown.meta.enter.prevent="save"
  >
    <div class="field">
      <label>标题 <span class="required">*</span></label>
      <input v-model="form.title" placeholder="要做什么？" autofocus :class="{ invalid: errors.title }" />
      <p v-if="errors.title" class="field-error">{{ errors.title }}</p>
    </div>

    <div class="grid">
      <div class="field">
        <label>开始日期</label>
        <input type="date" v-model="form.start_date" :class="{ invalid: errors.dateRange }" />
      </div>
      <div class="field">
        <label>结束日期</label>
        <input type="date" v-model="form.end_date" :class="{ invalid: errors.dateRange }" />
        <p v-if="errors.dateRange" class="field-error">{{ errors.dateRange }}</p>
      </div>
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
      <label>标签（回车添加，用于日历分类着色）</label>
      <div class="tag-input">
        <span class="tag-chip" v-for="(t, i) in form.tags" :key="t">
          {{ t }}
          <button type="button" class="tag-x" @click="removeTag(i)">✕</button>
        </span>
        <input
          v-model="tagInput"
          placeholder="如：科研、导师、杂事"
          @keydown.enter.prevent="addTag"
        />
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

.field-error {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--danger);
}

input.invalid {
  border-color: var(--danger);
}

input.invalid:focus {
  border-color: var(--danger);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--danger) 16%, transparent);
}

.grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.tag-input {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  align-items: center;
  padding: 8px 10px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.tag-input input {
  flex: 1;
  min-width: 140px;
  background: transparent;
  border: none;
  outline: none;
  font-size: 13px;
  color: var(--text);
}

.tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border-radius: var(--radius-pill);
  background: var(--accent-soft);
  color: var(--accent-hover);
  font-size: 12px;
  font-weight: 600;
  border: 1px solid var(--border);
  box-shadow: var(--shadow-inset);
  transition: transform 0.15s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.15s ease;
}

.tag-chip:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px var(--accent-glow), var(--shadow-inset);
}

.tag-x {
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
  font-size: 11px;
  padding: 0;
  opacity: 0.7;
}

.tag-x:hover {
  opacity: 1;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 4px;
}

@media (max-width: 640px) {
  .grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 520px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
