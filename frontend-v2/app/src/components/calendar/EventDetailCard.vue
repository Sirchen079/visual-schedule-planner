<script setup lang="ts">
/**
 * 事件详情及编辑浮层。重复事件的修改作用于整个系列。
 * 日期、时间、提醒与 RRULE 通过日程接口保存。
 */
import { computed, onUnmounted, reactive, ref, watch } from 'vue'
import { useScheduleStore } from '../../stores/schedule'
import ReminderFields from './ReminderFields.vue'
import { getEvent, updateEvent, type EventDetail } from '../../api/schedule'
import { registerEscLayer } from '../../composables/hotkeyPorts'
import { categoryLabel, repeatRuleText } from '../../utils/recurrence'
import { parseIsoDate } from '../../utils/date'

const props = defineProps<{
  eventId: number | null
  occurrenceDate?: string | null
  /** 点击处的 expand occurrence 携带的 repeat_note（详情端点不透出该字段时的消费通路） */
  repeatNoteHint?: string | null
}>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'saved', event: EventDetail): void }>()

const schedule = useScheduleStore()
const detail = ref<EventDetail | null>(null)
const form = reactive({ title:'', date:'', start_time:'', end_time:'', location:'', category:'general', notes:'', reminder_time:'' })
const editError = ref(''), editNotice = ref('')
function fillForm(event: EventDetail): void {
  Object.assign(form, { title:event.title, date:event.date, start_time:event.start_time ?? '', end_time:event.end_time ?? '',
    location:event.location, category:event.category, notes:event.notes, reminder_time:event.reminder_time ?? '' })
}
async function saveEvent(): Promise<void> {
  if (!detail.value || saving.value) return
  editError.value = ''; editNotice.value = ''
  if (!form.title.trim()) { editError.value = '请填写行程名称。'; return }
  if (!form.date) { editError.value = '请选择日期。'; return }
  if (form.start_time && form.end_time && form.end_time <= form.start_time &&
      (form.start_time !== detail.value.start_time || form.end_time !== detail.value.end_time)) {
    editError.value = '结束时间应晚于开始时间。'; return
  }
  if (!form.start_time && detail.value.remind_offsets?.length && !form.reminder_time) {
    editError.value = '此行程已开启提醒。改为全天时，请填写下方的提醒时间。'; return
  }
  const original = detail.value, id = original.id, revision = seq
  const values = { ...form, title:form.title.trim(), start_time:form.start_time || null, end_time:form.end_time || null, reminder_time:form.reminder_time || null }
  const patch: Parameters<typeof updateEvent>[1] = {}
  for (const key of Object.keys(values) as Array<keyof typeof values>) {
    if (values[key] !== original[key]) (patch as Record<string, unknown>)[key] = values[key]
  }
  if (!Object.keys(patch).length) { editNotice.value = '行程信息未发生变化。'; return }
  saving.value = true
  try {
    const updated = await updateEvent(id, patch)
    void schedule.refreshAll()
    if (revision !== seq || props.eventId !== id) return
    detail.value = updated; fillForm(updated)
    reminderTime.value = updated.reminder_time ?? null
    editNotice.value = updated.recur_rrule ? '重复行程已保存，日历中的整个系列已更新。' : '行程已保存，日历已更新。'
    emit('saved', updated)
  } catch (e) { if (revision === seq) editError.value = e instanceof Error ? e.message : '保存失败，修改内容仍保留。' }
  finally { if (revision === seq) saving.value = false }
}

const loading = ref(false)
const error = ref<string | null>(null)
/** 请求序号：竞态时只采纳最后一次请求的结果 */
let seq = 0
const reminderOffsets = ref<number[]>([])
const reminderTime = ref<string | null>(null)
const saving = ref(false)
const reminderError = ref('')
const reminderNotice = ref('')
async function saveReminders(): Promise<void> {
  if (!detail.value || saving.value) return
  const id = detail.value.id, revision = seq
  saving.value = true; reminderError.value = ''; reminderNotice.value = ''
  try {
    const updated = await updateEvent(id, { remind_offsets: [...reminderOffsets.value], reminder_time: reminderTime.value || null })
    void schedule.refreshAll()
    if (revision !== seq || props.eventId !== id) return
    detail.value = updated
    form.reminder_time = updated.reminder_time ?? ''
    emit('saved', updated)
    reminderOffsets.value = [...(updated.remind_offsets ?? [])]; reminderTime.value = updated.reminder_time ?? null
    reminderNotice.value = reminderOffsets.value.length ? '日程提醒已保存。' : '后续日程提醒已关闭。'
  } catch (e) {
    if (revision === seq) reminderError.value = e instanceof Error ? e.message : '提醒保存失败，请重试。'
  } finally { if (revision === seq) saving.value = false }
}

async function load(): Promise<void> {
  if (props.eventId === null) return
  const my = ++seq
  loading.value = true
  error.value = null
  detail.value = null
  try {
    const d = await getEvent(props.eventId)
    if (my !== seq) return // 期间已换事件/关闭：丢弃过期结果
    detail.value = d
    fillForm(d); editError.value = ''; editNotice.value = ''
    reminderOffsets.value = [...(d.remind_offsets ?? [])]; reminderTime.value = d.reminder_time ?? null
    reminderError.value = ''; reminderNotice.value = ''
  } catch (e) {
    if (my !== seq) return
    error.value = e instanceof Error ? e.message : '事件详情加载失败'
  } finally {
    if (my === seq) loading.value = false
  }
}


/**
 * Esc 关闭并入全局分层第 ③ 层：不再自挂 window keydown（统一的快捷键注册入口），
 * 详情打开期间向 hotkeyPorts 注册 tier 3 条目，由 useHotkeys 的统一 Esc 分发调用 close。
 * 行为与原局部监听一致：Esc 且详情打开 → emit('close')；多浮层并存时先关更内层（第②层）。
 */
let deregEsc: (() => void) | null = null

watch(
  () => props.eventId,
  (id) => {
    seq++; saving.value = false; reminderError.value = ''; reminderNotice.value = ''
    if (id === null) {
      detail.value = null
      error.value = null
      loading.value = false
      deregEsc?.()
      deregEsc = null
      return
    }
    void load()
    if (deregEsc === null) deregEsc = registerEscLayer({ tier: 3, close: () => emit('close') })
  },
  { immediate: true },
)

onUnmounted(() => {
  seq++; deregEsc?.()
  deregEsc = null
})

const dateLabel = computed(() => {
  const original = detail.value
  const d = original ? { ...original, date: props.occurrenceDate || original.date } : null
  if (!d?.date) return '—'
  const wd = `星期${'日一二三四五六'[parseIsoDate(d.date).getDay()]}`
  const [y, m, day] = d.date.split('-')
  return `${y} 年 ${Number(m)} 月 ${Number(day)} 日 · ${wd}`
})

const recurText = computed(() =>
  repeatRuleText(detail.value?.repeat_note ?? props.repeatNoteHint, detail.value?.recur_rrule),
)
const isRecurring = computed(
  () => Boolean((detail.value?.repeat_note ?? props.repeatNoteHint)?.trim()) ||
    Boolean(detail.value?.recur_rrule && detail.value.recur_rrule.trim()),
)
</script>

<template>
  <Teleport to="body">
    <div v-if="eventId !== null" class="detail-backdrop" @click.self="emit('close')">
      <div class="note" role="dialog" aria-label="事件详情">
        <span class="tape" />
        <button class="close" title="关闭（Esc）" aria-label="关闭详情" @click="emit('close')">×</button>

        <!-- 加载状态提示 -->
        <div v-if="loading" class="state loading">
          <span class="state-mark">…</span>
          <p>正在调取事件详情…</p>
        </div>

        <div v-else-if="error" class="state error">
          <p class="err-line">{{ error }}</p>
          <div class="state-btns">
            <button class="btn-retry" @click="load()">重试</button>
            <button class="btn-dismiss" @click="emit('close')">关闭</button>
          </div>
        </div>

        <template v-else-if="detail">
          <div class="kicker">Event Note · 事件详情</div>
          <h3 class="title">{{ detail.title }}</h3>

          <form class="event-editor" @submit.prevent="saveEvent">
            <fieldset :disabled="saving">
              <label>行程名称<input id="event-edit-title" v-model="form.title" required maxlength="200" /></label>
              <p v-if="isRecurring" class="edit-scope">这是重复行程，以下修改应用于整个系列。当前查看：{{ dateLabel }}。</p>
              <label>{{ isRecurring ? '系列开始日期' : '日期' }}<input id="event-edit-date" v-model="form.date" type="date" required /></label>
              <div class="edit-times">
                <label>开始时间<input id="event-edit-start" v-model="form.start_time" type="time" /></label>
                <label>结束时间<input id="event-edit-end" v-model="form.end_time" type="time" /></label>
              </div>
              <p class="edit-hint">留空开始和结束时间表示全天；也可只设置开始时间。</p>
              <label v-if="!form.start_time && detail.remind_offsets?.length">全天日程的提醒时间<input id="event-edit-reminder-time" v-model="form.reminder_time" type="time" /><span class="edit-hint">原有提醒将按这个时刻计算。</span></label>
              <label>地点<input id="event-edit-location" v-model="form.location" maxlength="500" placeholder="可选" /></label>
              <label>类别<select id="event-edit-category" v-model="form.category">
                <option v-if="!['general','course','meeting','exam','work','personal'].includes(form.category)" :value="form.category">{{ categoryLabel(form.category) }}</option>
                <option value="general">日常行程</option><option value="course">课程</option><option value="meeting">会议</option><option value="exam">考试</option><option value="work">工作</option><option value="personal">个人</option>
              </select></label>
              <label>备注<textarea id="event-edit-notes" v-model="form.notes" rows="3" /></label>
              <p class="edit-hint">重复：{{ recurText }}</p>
              <p v-if="editError" class="reminder-status" role="alert">{{ editError }}</p>
              <p v-if="editNotice" class="reminder-status" role="status">{{ editNotice }}</p>
              <div class="event-edit-actions"><button id="event-edit-save" class="btn-retry" :disabled="saving">{{ saving ? '保存中…' : isRecurring ? '保存整个系列' : '保存修改' }}</button><button type="button" class="btn-dismiss" :disabled="saving" @click="fillForm(detail); editError = ''; editNotice = ''">撤销未保存修改</button></div>
            </fieldset>
          </form>

          <form class="reminder-editor" @submit.prevent="saveReminders">
            <ReminderFields v-model:offsets="reminderOffsets" v-model:reminder-time="reminderTime" :start-time="detail.start_time" :disabled="saving" />
            <p v-if="isRecurring" class="reminder-status">这里的提醒设置适用于整个重复日程系列。</p>
            <p v-if="reminderError" class="reminder-status" role="alert">{{ reminderError }}</p>
            <p v-if="reminderNotice" class="reminder-status" role="status">{{ reminderNotice }}</p>
            <button id="event-reminder-save" class="btn-retry" :disabled="saving">{{ saving ? '保存中…' : '保存提醒' }}</button>
          </form>
          <div class="foot">
            <span class="mono">事件 #{{ detail.id }}</span>

          </div>
        </template>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.event-editor fieldset { border:0; padding:0; margin:0; min-width:0; display:grid; gap:11px; }
.event-editor label { display:grid; gap:5px; font-size:12px; color:var(--paper-ink-2); min-width:0; }
.event-editor input,.event-editor select,.event-editor textarea { box-sizing:border-box; width:100%; min-width:0; border:1px solid var(--paper-line); border-radius:7px; background:var(--paper-bg); color:var(--paper-ink); padding:8px 10px; font:inherit; font-size:13px; }
.event-editor input:focus,.event-editor select:focus,.event-editor textarea:focus { outline:2px solid var(--paper-accent); outline-offset:1px; }
.event-editor fieldset:disabled { opacity:.7; }
.edit-times { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:10px; }
.edit-hint,.edit-scope { margin:0; font-size:12px; line-height:1.6; color:var(--paper-ink-3); }
.edit-scope { color:var(--paper-accent-text); padding:8px; background:var(--paper-note); border:1px solid var(--paper-line); border-radius:7px; }
.event-edit-actions { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }

.reminder-editor {
  margin-top:10px; border-top:1px solid var(--paper-line);
  --ink-1:var(--paper-ink); --ink-2:var(--paper-ink-2); --ink-3:var(--paper-ink-3);
  --line-2:var(--paper-line); --bg-app:var(--paper-hi); --amber:var(--paper-accent);
}
.reminder-status { font-size:12px; line-height:1.6; color:var(--paper-accent-text); margin:8px 0; }
.detail-backdrop {
  position: fixed;
  inset: 0;
  z-index: 60;
  background: var(--paper-backdrop);
  backdrop-filter: blur(2px);
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 便签卡：纸面上钉着的一张便签（微倾斜 + 胶带 + 纸面投影） */
.note {
  position: relative;
  width: 420px;
  max-width: calc(100vw - 48px);
  max-height: calc(100vh - 96px);
  overflow-y: auto;
  background: var(--paper-hi);
  color: var(--paper-ink);
  border: 1px solid var(--paper-line);
  border-radius: 2px;
  padding: 22px 20px 14px;
  transform: rotate(-0.8deg);
  box-shadow:
    0 1px 0 var(--paper-block-shadow),
    var(--paper-note-shadow-1),
    var(--paper-note-shadow-2);
}
/* 胶带：牛皮纸色半透明斜贴 */
.tape {
  position: absolute;
  top: -10px;
  left: 50%;
  width: 86px;
  height: 20px;
  transform: translateX(-50%) rotate(2deg);
  background: var(--paper-kraft);
  opacity: 0.85;
  border-left: 1px solid var(--paper-line);
  border-right: 1px solid var(--paper-line);
}
.close {
  position: absolute;
  top: 8px;
  right: 10px;
  width: 26px;
  height: 26px;
  border-radius: 6px;
  font-size: 16px;
  line-height: 1;
  color: var(--paper-ink-3);
}
.close:hover {
  color: var(--paper-accent-text);
  background: var(--paper-tint);
}

.state {
  padding: 18px 2px 14px;
  font-size: 13px;
  color: var(--paper-ink-3);
}
.state-mark {
  font-family: var(--mono);
  letter-spacing: 0.3em;
  color: var(--paper-accent-text);
}
.state p {
  margin-top: 6px;
}
.state.error .err-line {
  color: var(--paper-accent-text);
  border: 1px dashed var(--paper-accent);
  border-radius: 3px;
  padding: 8px 10px;
  background: var(--paper-ghost-tint);
}
.state-btns {
  margin-top: 10px;
  display: flex;
  gap: 8px;
}
.btn-retry {
  font-size: 12.5px;
  color: var(--paper-hi);
  background: var(--paper-accent);
  border-radius: 4px;
  padding: 5px 14px;
}
.btn-retry:hover {
  background: var(--paper-accent-deep);
}
.btn-dismiss {
  font-size: 12.5px;
  color: var(--paper-ink-2);
  border: 1px solid var(--paper-line);
  border-radius: 4px;
  padding: 5px 12px;
}
.btn-dismiss:hover {
  border-color: var(--paper-accent);
}

.kicker {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--paper-accent-text);
  margin-bottom: 6px;
}
.title {
  font-family: var(--serif-paper);
  font-size: 19px;
  font-weight: 600;
  line-height: 1.3;
  margin: 0 0 10px;
  padding-bottom: 9px;
  border-bottom: 1px solid var(--paper-line);
}

.rows {
  display: flex;
  flex-direction: column;
}
.row {
  display: flex;
  gap: 12px;
  padding: 6px 0;
  border-bottom: 1px dashed var(--paper-line);
  font-size: 13px;
  line-height: 1.5;
}
.row:last-child {
  border-bottom: none;
}
.row dt {
  flex: none;
  width: 34px;
  font-size: 11.5px;
  letter-spacing: 0.14em;
  color: var(--paper-ink-3);
  padding-top: 2px;
}
.row dd {
  margin: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.row .strong {
  font-weight: 600;
  color: var(--paper-ink);
}
.mono {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--paper-ink-3);
  letter-spacing: 0.02em;
}
.mono.dim {
  color: var(--paper-ink-3);
  opacity: 0.75;
}
.rule {
  color: var(--paper-accent-text);
  font-weight: 600;
}
.row[data-recur] .rule {
  border-bottom: 1px dashed var(--paper-accent);
}
.anchor {
  margin-top: 1px;
}
.notes-row dd {
  color: var(--paper-ink-2);
}

.foot {
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px solid var(--paper-line);
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
</style>
