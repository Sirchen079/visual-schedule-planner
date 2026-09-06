<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import * as api from '../api/researchWatch'
import { materialTarget } from '../api/materials'
const props = defineProps<{ projectId: number; parentBusy: boolean }>()
const emit = defineEmits<{ updated: [] }>()
const state = ref<api.Watch>(), draft = ref<api.Config>(), queryText = ref('')
const editing = ref(false), saving = ref(false), running = ref(false), error = ref(''), notice = ref('')
const expanded = ref(false), rows = ref<api.Run[]>([]), before = ref<number | null>(null)
const moreBusy = ref(false)
let alive = true, generation = 0, timer: ReturnType<typeof setInterval> | undefined
const disabled = computed(() => saving.value || props.parentBusy)
const isRunning = computed(() => running.value || !!state.value?.running)
const labels: Record<string, string> = { running:'正在检索', updated:'资料有更新', unchanged:'暂无变化', partial:'部分完成', failed:'未完成', stopped:'已停止', interrupted:'执行中断' }
const weekdays = ['周一','周二','周三','周四','周五','周六','周日']
const time = (v?: string | null) => v ? v.replace('T',' ').slice(0,16) : ''
const summary = computed(() => {
  const c = state.value?.config
  return c ? `${c.frequency === 'daily' ? '每天' : `每${weekdays[c.weekday ?? 0]}`} ${c.time} · 每次最多 ${c.max_sources} 份` : ''
})
function edit() {
  if (!state.value) return
  draft.value = JSON.parse(JSON.stringify(state.value.config)) as api.Config
  queryText.value = (draft.value.queries ?? []).join('\n')
  editing.value = true; notice.value = ''; error.value = ''
}
async function load() {
  const g = ++generation
  try {
    const value = await api.readWatch(props.projectId)
    if (!alive || g !== generation) return
    const previous = state.value?.runs[0]
    state.value = value
    const extra = rows.value.filter(r => !value.runs.some(n => n.id === r.id) && r.id < (value.runs[value.runs.length-1]?.id ?? Infinity))
    rows.value = [...value.runs, ...extra]
    if (!extra.length) before.value = value.next_before ?? null
    const latest = value.runs[0]
    if (previous && latest && latest.status !== 'running' && (previous.id !== latest.id || previous.status !== latest.status)) emit('updated')
  } catch (e) { if (alive && g === generation) error.value = e instanceof Error ? e.message : String(e) }
}
async function save(config?: api.Config) {
  if (disabled.value || !state.value) return
  const value = config ?? { ...draft.value!, queries:queryText.value.split('\n').map(s => s.trim()).filter(Boolean) }
  if (value.enabled && !(value.queries?.length)) { error.value = '请填写至少一条公开主题检索词。'; return }
  if ((value.queries?.length ?? 0) > 3) { error.value = '最多填写三条检索词，每行一条。'; return }
  saving.value = true; error.value = ''; notice.value = ''
  try {
    const saved = await api.saveWatch(props.projectId, { ...value, version:state.value.version })
    if (!alive) return
    state.value = saved; editing.value = false
    notice.value = saved.config.enabled ? '已保存，将按设定时间检索。也可以立即检查一次。' : '定期资料检索已暂停。正在读取的单个网页完成后会停止后续检索。'
    await load()
  } catch (e) { if (alive) { error.value = e instanceof Error ? e.message : String(e); await load() } }
  finally { if (alive) saving.value = false }
}
async function runNow() {
  if (disabled.value || isRunning.value) return
  running.value = true; error.value = ''; notice.value = ''
  try {
    const result = await api.runWatch(props.projectId)
    if (!alive) return
    notice.value = `${labels[result.status] ?? result.status}，详细结果已保存在执行记录。`
    await load(); emit('updated')
  } catch (e) { if (alive) { error.value = e instanceof Error ? e.message : String(e); await load() } }
  finally { if (alive) running.value = false }
}
async function more() {
  if (!before.value || moreBusy.value) return
  moreBusy.value = true
  try {
    const page = await api.readWatch(props.projectId, before.value)
    if (!alive) return
    rows.value = [...rows.value, ...page.runs.filter(r => !rows.value.some(old => old.id === r.id))]
    before.value = page.next_before ?? null
  } catch (e) { if (alive) error.value = e instanceof Error ? e.message : String(e) }
  finally { if (alive) moreBusy.value = false }
}
onMounted(() => { void load(); timer = setInterval(() => { if (!document.hidden && !saving.value) void load() },15000) })
onUnmounted(() => { alive = false; generation++; if (timer) clearInterval(timer) })
</script>

<template>
  <article class="research-watch" aria-label="定期资料检索">
    <header><div><h2>持续补充资料</h2><p class="hint">让知时按主题查找资料，把变化保留下来。</p></div><span class="tag">{{ !state ? '加载中…' : !state.project_active ? '项目已归档' : state.config.enabled ? '已开启' : '未开启' }}</span></header>
    <p v-if="error" role="alert" class="error">{{ error }} <button type="button" @click="load">刷新状态</button></p>
    <p v-if="notice" role="status" class="notice">{{ notice }}</p>
    <template v-if="state">
      <template v-if="!editing">
        <p v-if="state.config.queries?.length" class="queries">{{ state.config.queries.join(' / ') }}</p>
        <p v-if="state.config.enabled" class="hint">{{ summary }}<br>{{ isRunning ? '正在执行；结果会陆续保存。' : state.project_active ? `下次检查：${time(state.next_run_at)}` : '归档期间暂停执行，恢复项目后按原设置继续。' }}</p>
        <div class="actions"><button v-if="state.project_active" data-watch-edit @click="edit" :disabled="disabled">{{ state.config.enabled ? '修改设置' : '设置定期检索' }}</button><button v-if="state.config.enabled && state.project_active" data-watch-run @click="runNow" :disabled="disabled || isRunning">{{ isRunning ? '检索中…' : '立即检查' }}</button><button v-if="state.config.enabled" data-watch-pause @click="save({ ...state.config, enabled:false })" :disabled="disabled">暂停检索</button></div>
      </template>
      <form v-else-if="draft" @submit.prevent="save()">
        <label class="check"><input v-model="draft.enabled" data-watch-enabled type="checkbox" :disabled="disabled">开启此项目的定期资料检索</label>
        <label>公开主题检索词<textarea v-model="queryText" data-watch-queries rows="3" placeholder="每行一条，最多三条，例如：Python 官方教程 更新" :disabled="disabled" /></label>
        <p class="hint">这些检索词会发送给设置中选定的网页服务，请只填写公开主题关键词。</p>
        <div class="fields"><label>频率<select v-model="draft.frequency" data-watch-frequency :disabled="disabled"><option value="daily">每天</option><option value="weekly">每周</option></select></label><label v-if="draft.frequency === 'weekly'">星期<select v-model.number="draft.weekday" data-watch-weekday :disabled="disabled"><option v-for="(day,i) in weekdays" :key="day" :value="i">{{ day }}</option></select></label><label>本机时间<input v-model="draft.time" data-watch-time type="time" required :disabled="disabled"></label><label>每次数量<input v-model.number="draft.max_sources" data-watch-limit type="number" min="1" max="6" required :disabled="disabled"></label></div>
        <label class="check"><input v-model="draft.refresh_existing" type="checkbox" :disabled="disabled">重新读取搜索结果中已保存的网页，检查内容更新</label>
        <div class="actions"><button type="button" @click="editing = false" :disabled="disabled">取消</button><button type="submit" class="primary" data-watch-save :disabled="disabled">{{ saving ? '保存中…' : '保存设置' }}</button></div>
      </form>
      <p class="hint boundary">知时运行期间执行；退出后重开会补查一次，异常中断最多等待20分钟恢复。有新增或更新资料、出现新的失败时才通知。资料只代表已取得正文，学习方案可在阅读后继续调整。</p>
      <div v-if="rows.length" class="history">
        <button type="button" class="history-toggle" @click="expanded = !expanded">{{ expanded ? '收起执行记录' : '查看执行记录' }}</button>
        <template v-for="r in (expanded ? rows : rows.slice(0,1))" :key="r.id"><details class="run" :data-watch-run-id="r.id"><summary><strong>{{ labels[r.status] ?? r.status }}</strong><span>{{ time(r.started_at) }}</span><span>{{ r.sources.filter(s => s.changed).length }} 份更新</span></summary><p class="hint">检索词：{{ r.config.queries?.join(' / ') }}</p><ul><li v-for="s in r.sources" :key="s.source_id"><RouterLink v-if="s.library_file_id" :to="materialTarget(s.library_file_id)">{{ s.title }}</RouterLink><span v-else>{{ s.title }}</span><span class="hint"> · {{ s.changed ? '新增或更新' : s.status === 'verified' ? '沿用已保存版本' : '未取得正文' }}</span></li></ul><p v-for="(reason,i) in r.errors" :key="i" class="error">{{ reason }}</p><p v-if="!r.sources.length && r.status === 'running'" class="hint">正在查找资料，稍后自动更新。</p></details></template>
        <button v-if="expanded && before" @click="more" :disabled="moreBusy">{{ moreBusy ? '加载中…' : '更早记录' }}</button>
      </div>
    </template>
  </article>
</template>

<style scoped>
.research-watch { margin:14px 0; border:1px solid var(--line); border-radius:12px; background:var(--bg-raise); color:var(--ink); padding:20px; }
header,.actions,.fields,summary { display:flex; gap:12px; align-items:center; flex-wrap:wrap; }header { justify-content:space-between; }h2 { margin:0; font-size:17px; }p { font-size:13px; line-height:1.8; overflow-wrap:anywhere; }.hint { color:var(--ink-3); font-size:12px; }.tag { font-size:12px; padding:4px 8px; border:1px solid var(--line); border-radius:6px; color:var(--amber); }.queries { font-weight:500; }.actions { justify-content:flex-end; margin-top:12px; }button { padding:8px 12px; background:var(--bg-raise); color:var(--ink); border:1px solid var(--line); border-radius:7px; font:inherit; font-size:12px; cursor:pointer; }button:disabled { opacity:.5; cursor:default; }.primary { background:var(--amber); color:var(--btn-ok-text); border-color:transparent; }form label { display:flex; flex-direction:column; gap:7px; font-size:12px; margin:12px 0; }form .check { flex-direction:row; align-items:center; justify-content:flex-start; }.fields { align-items:stretch; }.fields label { flex:1; min-width:100px; }.research-watch input,.research-watch select,.research-watch textarea { box-sizing:border-box; max-width:100%; border:1px solid var(--line); border-radius:6px; padding:9px; background:var(--bg-raise); color:var(--ink); font:inherit; font-size:13px; }.research-watch textarea { width:100%; resize:vertical; }.research-watch input[type=checkbox] { width:auto; accent-color:var(--amber); }.research-watch :is(button,input,select,textarea):focus-visible { outline:2px solid var(--amber); outline-offset:2px; }.error { color:var(--terra); }.notice { color:var(--amber); }.boundary { padding-top:10px; border-top:1px solid var(--line); }.run { margin-top:12px; padding-top:12px; border-top:1px solid var(--line); }summary { cursor:pointer; font-size:12px; }summary span { color:var(--ink-3); }.run ul { padding-left:20px; font-size:12px; line-height:1.9; overflow-wrap:anywhere; }.run a { color:var(--amber); }@media(max-width:700px) { .research-watch { padding:14px; } }
</style>
