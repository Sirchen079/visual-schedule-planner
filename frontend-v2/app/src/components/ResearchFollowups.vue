<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import * as api from '../api/followups'
import { useRunStore } from '../stores/run'
const props = defineProps<{ projectId: number; parentBusy: boolean }>()
const emit = defineEmits<{ updated: [] }>()
const route = useRoute(), run = useRunStore()
const rows = ref<api.Followup[]>([]), settings = ref<api.FollowupStatus | null>(null), selected = ref<api.Followup | null>(null)
const busy = ref(false), loading = ref(false), error = ref(''), notice = ref(''), historyOpen = ref(false)
const disabled = computed(() => busy.value || props.parentBusy)
const openRows = computed(() => rows.value.filter(r => ['pending','waiting','snoozed','applying'].includes(r.status)))
const historyRows = computed(() => rows.value.filter(r => !['pending','waiting','snoozed','applying'].includes(r.status)))
const labels: Record<string,string> = { pending:'待处理', waiting:'仍需补充信息', snoozed:'稍后提醒', applying:'正在落实', applied:'已落实', resolved:'情况已变化', dismissed:'已忽略' }
const policy = computed(() => !settings.value?.enabled || !settings.value.autopilot_enabled ? '发现问题后准备建议，由你决定落实。' : settings.value.autonomy === 'autonomous' ? '可按现有授权自动调整；容量不足或涉及保留的人工安排时会留给你处理。' : '已开启秘书自动档，实际调整仍按现有授权判断。')
let generation = 0, detailGeneration = 0, alive = true, openedRouteId = 0, timer: ReturnType<typeof setInterval> | undefined
const formatTime = (value: unknown) => typeof value === 'string' ? value.replace('T',' ').slice(0,16) : ''
async function load() {
  const g = ++generation, id = props.projectId
  loading.value = true
  try {
    const [list,status] = await Promise.all([api.listFollowups(id), api.followupStatus()])
    if (g !== generation) return
    rows.value = list; settings.value = status
    const wanted = Number(route.query.followup)
    if (wanted > 0 && wanted !== openedRouteId && list.some(r => r.id === wanted)) {
      openedRouteId = wanted
      await show(wanted)
    } else if (selected.value && list.some(r => r.id === selected.value?.id && r.version !== selected.value?.version)) {
      await show(selected.value.id)
    }
  } catch (e) { if (g === generation) error.value = e instanceof Error ? e.message : String(e) }
  finally { if (g === generation) loading.value = false }
}
async function show(id: number) {
  const pid = props.projectId, g = ++detailGeneration
  try { const row = await api.readFollowup(id); if (alive && g === detailGeneration && pid === props.projectId && row.project_id === pid) selected.value = row }
  catch (e) { if (alive && g === detailGeneration && pid === props.projectId) error.value = e instanceof Error ? e.message : String(e) }
}
function closeDetail() { detailGeneration++; selected.value = null }
async function act(fn: () => Promise<void>) {
  if (disabled.value) return
  detailGeneration++
  busy.value = true; error.value = ''; notice.value = ''
  try { await fn(); if (!alive) return; await load(); if (alive) emit('updated') }
  catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { busy.value = false }
}
async function check() {
  await act(async () => { selected.value = await api.checkProgress(props.projectId); notice.value = selected.value ? '已检查最新进度，跟进记录已更新。' : '当前没有需要调整的学习安排。'; window.dispatchEvent(new Event('zhishi:tasks-changed')) })
}
async function apply() {
  const row = selected.value; if (!row) return
  await act(async () => { selected.value = await api.applyFollowup(row); notice.value = '已落实调整，完成记录和人工安排已保留。'; window.dispatchEvent(new Event('zhishi:tasks-changed')) })
}
async function respond(row: api.Followup, when?: 'later' | 'tomorrow') {
  const date = new Date()
  if (when === 'later') date.setHours(date.getHours()+2)
  if (when === 'tomorrow') { date.setDate(date.getDate()+1); date.setHours(9,0,0,0) }
  await act(async () => {
    const saved = await api.respondFollowup(row, when ? date.toISOString() : undefined)
    if (selected.value?.id === row.id) selected.value = saved
    notice.value = when ? `已安排稍后提醒：${formatTime(saved.snoozed_until)}` : '已忽略当前这条跟进；同样情况不会重复提醒。'
  })
}
async function setEnabled(enabled: boolean) { await act(async () => { settings.value = await api.setFollowupEnabled(enabled) }) }
watch(() => props.projectId, () => { generation++; closeDetail(); openedRouteId = 0; rows.value = []; error.value = ''; notice.value = ''; void load() })
watch(() => route.query.followup, value => { const id = Number(value); openedRouteId = id; if (id > 0) void show(id); else closeDetail() })
watch(() => run.phase, phase => { if (['completed','cancelled','awaiting_approval'].includes(phase)) void load() })
onMounted(() => { void load(); window.addEventListener('focus',load); timer = setInterval(() => { if (!document.hidden && !busy.value) void load() },30000) })
onUnmounted(() => { alive = false; generation++; detailGeneration++; window.removeEventListener('focus',load); if (timer) clearInterval(timer) })
</script>

<template>
  <article class="followups" aria-label="持续跟进">
    <header><h2>知时在跟进</h2><button @click="check" :disabled="disabled">{{ busy ? '处理中…' : '检查进度' }}</button></header>
    <label v-if="settings" class="monitor"><input type="checkbox" :checked="settings.enabled" :disabled="disabled" @change="setEnabled(($event.target as HTMLInputElement).checked)">持续跟进全部学习项目</label>
    <p class="hint">{{ settings?.enabled ? '知时运行期间每5分钟检查一次；没有新情况不重复提醒。' : '后台跟进已暂停，仍可手动检查此项目。' }}{{ policy }}</p>
    <p v-if="settings?.last_scan?.at" class="hint">最近后台检查：{{ formatTime(settings.last_scan.at) }}</p>
    <p v-if="error" class="error" role="alert">{{ error }} <button @click="check" :disabled="disabled">重新检查</button></p>
    <p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <p v-if="!loading && !openRows.length" class="hint">当前没有待处理的跟进。</p>
    <div v-for="row in openRows" :key="row.id" class="entry">
      <div class="row"><strong>{{ row.title }}</strong><span class="tag">{{ labels[row.status] }}</span></div><p>{{ row.body }}</p><p v-if="row.error" class="error">{{ row.error }}</p>
      <p v-if="row.snoozed_until" class="hint">提醒时间：{{ formatTime(row.snoozed_until) }}</p>
      <div class="actions"><button @click="show(row.id)" :disabled="disabled">查看跟进</button><template v-if="['pending','waiting'].includes(row.status)"><button @click="respond(row,'later')" :disabled="disabled">两小时后提醒</button><button @click="respond(row,'tomorrow')" :disabled="disabled">明早提醒</button><button @click="respond(row)" :disabled="disabled">忽略这条</button></template></div>
    </div>
    <div v-if="selected" class="detail">
      <header><h3>{{ selected.title }}</h3><button @click="closeDetail">收起</button></header><p>{{ selected.body }}</p>
      <template v-if="selected.plan"><p class="hint">{{ selected.plan.assignments.length }} 项安排 · {{ selected.plan.unassigned.length }} 项未排入 · {{ selected.plan.preserved.length }} 项保留</p>
        <ol><li v-for="assignment in selected.plan.assignments" :key="assignment.unit_index"><strong>{{ selected.plan.units[assignment.unit_index]?.title }}</strong><span>{{ assignment.date }} {{ assignment.start }}–{{ assignment.end }}</span></li></ol>
        <p v-for="item in selected.plan.unassigned" :key="item.unit_index" class="hint">{{ selected.plan.units[item.unit_index]?.title }}：{{ item.reason }}</p>
        <p v-if="selected.plan.preserved.length" class="hint">已完成、正在进行、手工调整或已删除的任务保持现状。</p>
        <button v-if="selected.status === 'pending' && selected.plan.state === 'draft'" class="primary" @click="apply" :disabled="disabled">确认跟进调整</button>
      </template><p v-else class="hint">可在此页面调整目标与时间，或在左侧对话继续处理。</p>
    </div>
    <button v-if="historyRows.length" class="history-toggle" @click="historyOpen = !historyOpen">{{ historyOpen ? '收起' : '查看' }}处理记录（{{ historyRows.length }}）</button>
    <div v-if="historyOpen"><div v-for="row in historyRows" :key="row.id" class="entry"><div class="row"><strong>{{ row.title }}</strong><span class="tag">{{ labels[row.status] }}</span></div><p>{{ row.body }}</p><button @click="show(row.id)">查看记录</button></div></div>
  </article>
</template>

<style scoped>
.followups .monitor { flex-direction:row; justify-content:flex-start; }
.followups .detail { background:var(--bg-sink); }
.followups { border:1px solid var(--line); border-radius:12px; padding:20px; margin:14px 0; background:var(--bg-raise); color:var(--ink); }header,.row,.actions { display:flex; align-items:center; gap:10px; justify-content:space-between; flex-wrap:wrap; }h2 { font-size:17px; margin:0; }h3 { font-size:14px; margin:0; }.monitor { display:flex; align-items:center; gap:8px; font-size:12px; margin-top:16px; color:var(--ink-3); }.monitor input { accent-color:var(--amber); }p { font-size:13px; line-height:1.8; overflow-wrap:anywhere; }.hint { color:var(--ink-3); font-size:12px; }button { font:inherit; font-size:12px; padding:8px 11px; background:var(--bg-raise); border:1px solid var(--line); border-radius:7px; color:var(--ink); cursor:pointer; }button:disabled { opacity:.5; cursor:default; }button:hover { border-color:var(--ink-3); }button:focus-visible,input:focus-visible { outline:2px solid var(--amber); outline-offset:2px; }.primary { background:var(--amber); color:var(--btn-ok-text); border-color:transparent; }.entry { border-top:1px solid var(--line); padding-top:14px; margin-top:14px; }.row strong { font-size:13px; }.tag { color:var(--amber); border:1px solid var(--line); padding:3px 7px; border-radius:5px; font-size:11px; }.actions { justify-content:flex-end; }.detail { background:var(--bg); padding:16px; border-radius:8px; margin-top:16px; }.detail ol { padding-left:20px; font-size:12px; }.detail li { line-height:1.8; padding:8px 0; }.detail li span { display:block; color:var(--amber); }.error { color:var(--terra); white-space:pre-wrap; }.notice { color:var(--amber); }.history-toggle { margin-top:14px; }
@media(max-width:700px) { .followups { padding:14px; } }
</style>
