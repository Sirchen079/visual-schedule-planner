<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import DetailDialog from './DetailDialog.vue'
import { getTask, updateTask, updateSubtask, type Task, type TaskUpdateInput } from '../../api/tasks'
import { getTaskEntries, type ScheduleEntry } from '../../api/schedule'
import { useScheduleStore } from '../../stores/schedule'
import { useTasksStore } from '../../stores/tasks'
import { renderMarkdown } from '../../utils/md'
import { repeatRuleText } from '../../utils/recurrence'

const props = defineProps<{ taskId: number | null; occurrenceDate?: string | null }>()
const emit = defineEmits<{ close: [] }>()
const schedule = useScheduleStore(), tasks = useTasksStore()
const task = ref<Task | null>(null), entries = ref<ScheduleEntry[]>([])
const loading = ref(false), saving = ref(false), error = ref(''), actionError = ref(''), entriesError = ref(''), notice = ref('')
const editor = ref<HTMLDetailsElement | null>(null)
let revision = 0
const form = reactive({ title:'', notes:'', start_date:'', due_date:'', due_time:'', priority:'medium', estimated_minutes:'' })
const statusLabel = computed(() => ({ todo:'待办', doing:'进行中', done:'已完成' }[task.value?.status ?? 'todo']))
const completed = computed(() => task.value?.subtasks?.filter(s => s.done).length ?? 0)
const recurrence = computed(() => task.value?.recur_rrule ? repeatRuleText(null, task.value.recur_rrule)
  : ({ daily:'每天', weekdays:'工作日', weekly:'每周', monthly:'每月' } as Record<string,string>)[task.value?.recur_rule ?? ''] ?? '')
function fill(t: Task) {
  Object.assign(form, { title:t.title, notes:t.notes, start_date:t.start_date?.slice(0,10) ?? '', due_date:t.due_date?.slice(0,10) ?? '', due_time:t.due_time ?? '', priority:t.priority, estimated_minutes:t.estimated_minutes == null ? '' : String(t.estimated_minutes) })
}
async function load() {
  const id = props.taskId, token = ++revision
  if (id == null) { task.value = null; return }
  loading.value = true; error.value = ''; entriesError.value = ''; task.value = null; entries.value = []
  const [detail, plans] = await Promise.allSettled([getTask(id), getTaskEntries(id)])
  if (token !== revision) return
  if (detail.status === 'fulfilled') { task.value = detail.value; fill(detail.value) }
  else error.value = detail.reason instanceof Error ? detail.reason.message : '任务详情加载失败'
  if (plans.status === 'fulfilled') entries.value = plans.value
  else entriesError.value = '排期加载失败，请重试。'
  loading.value = false
}
watch(() => props.taskId, () => { saving.value = false; actionError.value = ''; notice.value = ''; if (editor.value) editor.value.open = false; void load() }, { immediate:true })
onBeforeUnmount(() => { revision++ })
async function refreshViews() { await Promise.all([schedule.refreshAll(), tasks.refreshAll()]) }
async function changeStatus() {
  if (!task.value || saving.value) return
  const id = task.value.id, token = revision, status = task.value.status === 'done' ? 'todo' : 'done'
  saving.value = true; actionError.value = ''
  try {
    const updated = await updateTask(id, { status })
    void refreshViews()
    if (token === revision) { task.value = updated; notice.value = '任务状态已更新。' }
  } catch(e) { if (token === revision) actionError.value = e instanceof Error ? e.message : '状态更新失败' }
  finally { if (token === revision) saving.value = false }
}
async function toggleSubtask(id: number, done: boolean) {
  if (!task.value || saving.value) return
  const taskId = task.value.id, token = revision
  saving.value = true; actionError.value = ''
  try {
    await updateSubtask(taskId, id, { done: !done })
    void refreshViews()
    const updated = await getTask(taskId)
    if (token === revision) task.value = updated
  } catch(e) { if (token === revision) actionError.value = e instanceof Error ? e.message : '子任务更新失败，请重新加载确认状态。' }
  finally { if (token === revision) saving.value = false }
}
async function save() {
  if (!task.value || saving.value) return
  const id = task.value.id, token = revision
  const patch: TaskUpdateInput = {}
  const values = { title:form.title.trim(), notes:form.notes, due_time:form.due_time || null, priority:form.priority, estimated_minutes:form.estimated_minutes === '' ? null : Number(form.estimated_minutes) }
  for (const [key,value] of Object.entries(values)) if (value !== task.value[key as keyof Task]) (patch as Record<string, unknown>)[key] = value
  for (const key of ['start_date','due_date'] as const) if (form[key] !== (task.value[key]?.slice(0,10) ?? '')) patch[key] = form[key] ? `${form[key]}T00:00:00` : null
  if (!values.title) { actionError.value = '请填写任务标题。'; return }
  if (!Object.keys(patch).length) { if (editor.value) editor.value.open = false; return }
  saving.value = true; actionError.value = ''; notice.value = ''
  try {
    const updated = await updateTask(id, patch)
    void refreshViews()
    if (token === revision) { task.value = updated; fill(updated); notice.value = '已保存，日历和今日已同步更新。'; if (editor.value) editor.value.open = false }
  } catch(e) { if (token === revision) actionError.value = e instanceof Error ? e.message : '保存失败，修改内容已保留。' }
  finally { if (token === revision) saving.value = false }
}
</script>

<template>
  <DetailDialog :open="taskId !== null" label="任务详情" @close="emit('close')">
    <p v-if="loading" class="muted" role="status">正在加载任务…</p>
    <div v-else-if="error" role="alert"><p>{{ error }}</p><button class="action" @click="load">重新加载</button></div>
    <template v-else-if="task">
      <h2>{{ task.title }}</h2>
      <div class="task-meta"><span class="status">{{ statusLabel }}</span><span>{{ { high:'高',medium:'中',low:'低' }[task.priority] }}优先级</span><span v-if="task.estimated_minutes">预计 {{ task.estimated_minutes }} 分钟</span><span v-for="tag in task.tags" :key="tag">{{ tag }}</span></div>
      <dl class="dates"><template v-if="task.start_date"><dt>开始</dt><dd>{{ task.start_date.slice(0,10) }}</dd></template><template v-if="task.due_date"><dt>截止</dt><dd>{{ task.due_date.slice(0,10) }} {{ task.due_time }}</dd></template></dl>
      <dl v-if="recurrence || task.remind_offsets?.length" class="dates"><template v-if="recurrence"><dt>重复</dt><dd>{{ recurrence }}</dd></template><template v-if="task.remind_offsets?.length"><dt>提醒</dt><dd>{{ task.remind_offsets.map(n => n === 0 ? '截止时' : `提前 ${n} 分钟`).join('、') }}</dd></template></dl>
      <section v-if="task.notes" class="task-section"><h3>详细说明</h3><div class="full-notes" v-html="renderMarkdown(task.notes)" /></section>
      <section v-if="task.subtasks?.length" class="task-section"><h3>子任务 <span>{{ completed }} / {{ task.subtasks.length }}</span></h3><ul class="subtasks"><li v-for="sub in task.subtasks" :key="sub.id"><label><input type="checkbox" :checked="sub.done" :disabled="saving" @change="toggleSubtask(sub.id, sub.done)" /><span :class="{ done:sub.done }">{{ sub.title }}</span><small v-if="sub.estimated_minutes">{{ sub.estimated_minutes }} 分钟</small></label></li></ul></section>
      <details class="task-section" :open="entries.some(e => e.date === occurrenceDate)"><summary>全部排期 <span>{{ entries.length }} 次</span></summary><p v-if="entriesError" role="alert">{{ entriesError }} <button @click="load">重新加载</button></p><p v-else-if="!entries.length" class="muted">尚未设置排期。</p><ol v-else class="plans"><li v-for="entry in entries" :key="entry.id" :data-selected="entry.date === occurrenceDate"><div><time>{{ entry.date }}</time><span>{{ entry.start_time || (entry.end_time ? '开始未定' : '全天') }}{{ entry.end_time ? `–${entry.end_time}` : entry.start_time ? ' · 结束未定' : '' }}</span></div><p v-if="entry.note">{{ entry.note }}</p></li></ol></details>
      <p v-if="actionError" role="alert" class="feedback">{{ actionError }}</p><p v-if="notice" role="status" class="feedback">{{ notice }}</p>
      <div class="task-actions"><button class="action" :disabled="saving" @click="changeStatus">{{ task.status === 'done' ? '标记为待办' : '标记为完成' }}</button></div>
      <details ref="editor" class="task-section editor"><summary>编辑任务</summary><form @submit.prevent="save"><fieldset :disabled="saving"><label>任务标题<input v-model="form.title" required maxlength="200" /></label><label>详细说明<textarea v-model="form.notes" rows="6" /></label><div class="fields"><label>开始日期<input v-model="form.start_date" type="date" /></label><label>截止日期<input v-model="form.due_date" type="date" /></label><label>截止时间<input v-model="form.due_time" type="time" /></label><label>预计分钟<input v-model="form.estimated_minutes" type="number" min="0" /></label></div><label>优先级<select v-model="form.priority"><option value="high">高</option><option value="medium">中</option><option value="low">低</option></select></label><div class="task-actions"><button class="action" type="submit">{{ saving ? '保存中…' : '保存修改' }}</button><button type="button" @click="fill(task); if(editor) editor.open=false">取消</button></div></fieldset></form></details>
    </template>
  </DetailDialog>
</template>

<style scoped>
h2 { font-family:var(--serif); font-size:25px; line-height:1.4; font-weight:600; margin:0 0 12px; }
.task-meta { display:flex; flex-wrap:wrap; gap:12px; align-items:center; font-size:12px; color:var(--paper-ink-3); }
.status { padding:3px 8px; background:var(--paper-tint); border:1px solid var(--paper-line); border-radius:7px; color:var(--paper-accent-text); }
.dates { display:grid; grid-template-columns:44px 1fr; gap:8px; font-size:13px; margin:20px 0; } dt { color:var(--paper-ink-3); } dd { margin:0; font-family:var(--mono); }
.task-section { border-top:1px solid var(--paper-line); padding-top:16px; margin-top:20px; }
h3,summary { font-size:13px; font-weight:600; margin:0 0 12px; } summary { cursor:pointer; } h3 span,summary span { margin-left:8px; font-family:var(--mono); color:var(--paper-ink-3); font-weight:400; }
.full-notes { font-size:14px; line-height:1.8; overflow-wrap:anywhere; } .full-notes :deep(p) { margin:8px 0; } .full-notes :deep(pre) { overflow:auto; } .full-notes :deep(ul),.full-notes :deep(ol) { padding-left:24px; }
.subtasks,.plans { list-style:none; padding:0; margin:0; } .subtasks label { display:flex; align-items:baseline; gap:10px; padding:8px 0; font-size:14px; cursor:pointer; } .subtasks input { accent-color:var(--paper-accent); flex:none; } .subtasks label span { flex:1; } .subtasks small,.muted { color:var(--paper-ink-3); } .done { text-decoration:line-through; color:var(--paper-ink-3); }
.plans li { border-left:2px solid var(--paper-line); padding:10px 12px; margin:8px 0; font-size:13px; } .plans li[data-selected='true'] { border-color:var(--paper-accent); background:var(--paper-tint); } .plans li div { display:flex; flex-wrap:wrap; gap:12px; font-family:var(--mono); } .plans p { margin:8px 0 0; white-space:pre-wrap; line-height:1.6; }
.task-actions { display:flex; gap:16px; align-items:center; margin-top:18px; font-size:13px; } .action { padding:8px 14px; border:1px solid var(--paper-accent); border-radius:7px; color:var(--paper-accent-text); } .action:hover { background:var(--paper-tint); } button:disabled { opacity:.5; cursor:wait; }
.feedback { font-size:13px; color:var(--paper-accent-text); line-height:1.6; }
fieldset { border:0; padding:0; margin:0; min-width:0; display:grid; gap:12px; } .editor label { display:grid; gap:5px; font-size:12px; } .editor input,.editor textarea,.editor select { box-sizing:border-box; width:100%; min-width:0; border:1px solid var(--paper-line); border-radius:7px; padding:9px; font:inherit; background:var(--paper-hi); color:var(--paper-ink); } .fields { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
</style>
