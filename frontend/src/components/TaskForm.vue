<script setup>
import { reactive, ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: Object, default: null },
  // 新建时的预填数据（如日历双击格子传入 { due_date }），编辑时忽略
  initial: { type: Object, default: null },
})
const emit = defineEmits(['save', 'cancel'])

// 提醒偏移选项（分钟）：写进 remind_offsets 数组
const REMIND_OPTIONS = [
  { value: 0, label: '截止时' },
  { value: 30, label: '提前30分钟' },
  { value: 120, label: '提前2小时' },
  { value: 1440, label: '提前1天' },
  { value: 4320, label: '提前3天' },
]

const form = reactive({
  title: '',
  notes: '',
  start_date: '',
  end_date: '',
  due_date: '',
  due_time: '',
  priority: '中',
  status: '待办',
  progress: 0,
  tags: [],
  remind_offsets: [],
  recur_rule: 'none',
  recur_interval: 1,
  estimated_minutes: null,
})
const tagInput = ref('')

// 校验反馈：标题必填；开始日期不能晚于结束日期
const errors = reactive({ title: '', dateRange: '' })

watch(
  [() => props.modelValue, () => props.initial],
  ([v, init]) => {
    if (v) {
      form.title = v.title || ''
      form.notes = v.notes || ''
      form.start_date = v.start_date ? v.start_date.slice(0, 10) : ''
      form.end_date = v.end_date ? v.end_date.slice(0, 10) : ''
      form.due_date = v.due_date ? v.due_date.slice(0, 10) : ''
      form.due_time = v.due_time || ''
      form.priority = v.priority || '中'
      form.status = v.status || '待办'
      form.progress = v.progress ?? 0
      form.tags = (v.tags || []).map((t) => t.name)
      form.remind_offsets = Array.isArray(v.remind_offsets) ? [...v.remind_offsets] : []
      form.recur_rule = v.recur_rule || 'none'
      form.recur_interval = v.recur_interval ?? 1
      form.estimated_minutes = v.estimated_minutes ?? null
    } else {
      Object.assign(form, {
        title: '',
        notes: '',
        start_date: '',
        end_date: '',
        due_date: '',
        due_time: '',
        priority: '中',
        status: '待办',
        progress: 0,
        tags: [],
        remind_offsets: [],
        recur_rule: 'none',
        recur_interval: 1,
        estimated_minutes: null,
      })
      if (init?.due_date) form.due_date = String(init.due_date).slice(0, 10)
      if (init?.due_time) form.due_time = init.due_time
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
// 截止时间依附于截止日期：清空日期时一并清空时间
watch(
  () => form.due_date,
  (v) => {
    if (!v) form.due_time = ''
  }
)

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

function toggleRemind(value) {
  const i = form.remind_offsets.indexOf(value)
  if (i === -1) form.remind_offsets.push(value)
  else form.remind_offsets.splice(i, 1)
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
  // 截止时间仅在已选截止日期时有意义
  payload.due_time = form.due_date && form.due_time ? form.due_time : null
  payload.remind_offsets = [...form.remind_offsets]
  const interval = Number.isFinite(form.recur_interval) ? Math.round(form.recur_interval) : 1
  payload.recur_interval = form.recur_rule === 'none' ? 1 : Math.min(99, Math.max(1, interval))
  // 预估耗时：可选，空值传 null（后端 Optional）
  payload.estimated_minutes =
    form.estimated_minutes === '' || form.estimated_minutes === null || form.estimated_minutes === undefined
      ? null
      : Math.max(0, Math.round(Number(form.estimated_minutes)) || 0)
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
        <label>时间</label>
        <input
          type="time"
          v-model="form.due_time"
          :disabled="!form.due_date"
          :title="form.due_date ? '截止时间' : '先选择截止日期'"
        />
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
        <label>重复</label>
        <div class="recur-row">
          <select v-model="form.recur_rule">
            <option value="none">不重复</option>
            <option value="daily">每天</option>
            <option value="weekdays">每个工作日</option>
            <option value="weekly">每周</option>
            <option value="monthly">每月</option>
          </select>
          <template v-if="form.recur_rule !== 'none'">
            <span class="recur-text">每</span>
            <input type="number" min="1" max="99" v-model.number="form.recur_interval" />
            <span class="recur-text">个周期</span>
          </template>
        </div>
      </div>
      <div class="field">
        <label>预估耗时（分钟）</label>
        <input
          type="number"
          min="0"
          step="5"
          v-model.number="form.estimated_minutes"
          placeholder="如 60"
        />
      </div>
      <div class="field">
        <label>进度 {{ form.progress }}%</label>
        <input type="range" min="0" max="100" v-model.number="form.progress" />
      </div>
    </div>

    <div class="field">
      <label>提醒</label>
      <div class="chip-group">
        <button
          v-for="opt in REMIND_OPTIONS"
          :key="opt.value"
          type="button"
          class="chip-toggle"
          :class="{ active: form.remind_offsets.includes(opt.value) }"
          @click="toggleRemind(opt.value)"
        >
          {{ opt.label }}
        </button>
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

/* 提醒 chip 多选组 */
.chip-group {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.chip-toggle {
  min-height: 30px;
  padding: 0 12px;
  border-radius: var(--radius-pill);
  background: var(--surface-2);
  border: 1px solid var(--border);
  color: var(--text-soft);
  font-size: 12px;
  font-weight: 600;
  box-shadow: none;
}

.chip-toggle:hover {
  border-color: var(--border-strong);
  box-shadow: none;
}

.chip-toggle.active {
  background: var(--accent-soft);
  border-color: color-mix(in srgb, var(--accent) 32%, var(--border));
  color: var(--accent-strong);
}

/* 重复规则的周期输入行 */
.recur-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.recur-row select {
  flex: 1;
  min-width: 0;
}

.recur-row input {
  width: 64px;
  flex-shrink: 0;
}

.recur-text {
  font-size: 12px;
  color: var(--text-soft);
  white-space: nowrap;
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
