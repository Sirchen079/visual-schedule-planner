<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{ startTime?: string | null; disabled?: boolean }>()
const offsets = defineModel<number[] | undefined>('offsets', { default: () => [] })
const reminderTime = defineModel<string | null | undefined>('reminderTime', { default: null })
const custom = ref<string | number>('')
const error = ref('')
const selected = computed(() => offsets.value ?? [])
const options = computed(() => [...new Set([0, 5, 15, 30, 60, 1440, ...selected.value])].sort((a, b) => a - b))
function label(value: number): string {
  if (value === 0) return '准时'
  if (value % 1440 === 0) return `提前 ${value / 1440} 天`
  if (value % 60 === 0) return `提前 ${value / 60} 小时`
  return `提前 ${value} 分钟`
}
function toggle(value: number): void {
  error.value = ''
  if (selected.value.includes(value)) offsets.value = selected.value.filter(n => n !== value)
  else if (selected.value.length < 8) offsets.value = [...selected.value, value].sort((a, b) => a - b)
  else error.value = '最多设置 8 个提醒时间。'
}
function addCustom(): void {
  const value = Number(custom.value)
  if (!String(custom.value).trim() || !Number.isInteger(value) || value < 0 || value > 10080) {
    error.value = '请输入 0 至 10,080 的整数分钟，最多提前 7 天。'; return
  }
  if (!selected.value.includes(value)) toggle(value)
  if (!error.value) custom.value = ''
}
</script>

<template>
  <fieldset class="reminder-fields" :disabled="props.disabled">
    <legend>日程提醒</legend>
    <div class="reminder-options">
      <label v-for="value in options" :key="value" :class="{ selected: selected.includes(value) }">
        <input type="checkbox" :checked="selected.includes(value)" :value="value" @change="toggle(value)" />{{ label(value) }}
      </label>
    </div>
    <div class="custom-reminder">
      <label>自定义提前分钟<input v-model="custom" type="number" min="0" max="10080" step="1" placeholder="例如 90" @keydown.enter.prevent="addCustom" /></label>
      <button type="button" @click="addCustom">添加</button>
      <button v-if="selected.length" type="button" @click="offsets = []; error = ''">关闭提醒</button>
    </div>
    <label v-if="!startTime && selected.length" class="day-clock">全天日程的提醒时间
      <input type="time" :value="reminderTime ?? ''" required aria-label="全天日程提醒时间" @input="reminderTime = ($event.target as HTMLInputElement).value || null" />
    </label>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p class="hint">{{ selected.length ? '提前时间以日程开始时刻为准；全天日程以所填时间为准。' : '未设置提醒。选择时间后保存即可开启。' }}应用运行时提醒，重新打开会补发最近漏过的提醒。</p>
  </fieldset>
</template>

<style scoped>
.reminder-fields { border:0; padding:0; margin:14px 0 8px; min-width:0; color:var(--ink-2); }
legend { font-size:13px; font-weight:600; margin-bottom:10px; }
.reminder-options { display:flex; flex-wrap:wrap; gap:7px; }
.reminder-options label { display:flex; align-items:center; gap:5px; border:1px solid var(--line-2); border-radius:6px; padding:6px 8px; font-size:12px; }
.reminder-options .selected { border-color:var(--amber); }
input[type=checkbox] { width:auto; accent-color:var(--amber); }
.custom-reminder { display:flex; align-items:flex-end; flex-wrap:wrap; gap:7px; margin:10px 0; }
.custom-reminder label,.day-clock { display:flex; flex-direction:column; gap:5px; font-size:12px; }
.custom-reminder input { width:130px; }
input[type=number],input[type=time] { padding:6px 8px; color:var(--ink-1); background:var(--bg-app); border:1px solid var(--line-2); border-radius:6px; font:inherit; }
button { padding:6px 9px; border:1px solid var(--line-2); border-radius:6px; font-size:12px; }
button:hover { border-color:var(--amber); }
.hint,.error { margin:8px 0 0; color:var(--ink-3); font-size:11px; line-height:1.7; }
.error { color:var(--amber); }
input:focus-visible,button:focus-visible { outline:2px solid var(--amber); outline-offset:2px; }
</style>
