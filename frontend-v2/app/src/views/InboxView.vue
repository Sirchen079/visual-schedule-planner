<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import InboxDraftFields from '../components/InboxDraftFields.vue'
import { useRunStore } from '../stores/run'
import { listInbox, readInbox, captureInbox, reviseInbox, applyInbox, rejectInbox, describeProposal,
  type InboxItem, type InboxProposal, type InboxStatus } from '../api/inbox'

const status = ref<InboxStatus>('pending')
const rows = ref<InboxItem[]>([])
const total = ref(0)
const offset = ref(0)
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const editing = ref<InboxItem | null>(null)
const formOpen = ref(false)
const proposal = ref<InboxProposal>({ kind: 'task', data: { title: '', priority: 'medium' } })
const source = ref('')
const uncertainty = ref('')
const token = ref(crypto.randomUUID())
const labels = { task: '待办', event: '日程', ledger: '收支' }
const tabs: { value: InboxStatus; label: string }[] = [
  { value: 'pending', label: '待确认' }, { value: 'applied', label: '已落实' }, { value: 'rejected', label: '已忽略' },
]
let generation = 0
async function load() {
  const current = ++generation
  loading.value = true; error.value = ''
  try {
    const page = await listInbox(status.value, offset.value)
    if (current !== generation) return
    rows.value = page.items; total.value = page.total
    if (offset.value > 0 && !page.items.length) { offset.value = Math.max(0, offset.value - 30); return }
  } catch (e) { if (current === generation) error.value = e instanceof Error ? e.message : String(e) }
  finally { if (current === generation) loading.value = false }
}
function chooseKind(kind: InboxProposal['kind']) {
  proposal.value = kind === 'task' ? { kind, data: { title: '', priority: 'medium' } }
    : kind === 'event' ? { kind, data: { title: '', date: '', location: '' } }
    : { kind, data: { day: '', direction: 'expense', amount: '', currency: 'CNY', category: '未分类', account: '默认账户' } }
}
function blank() {
  editing.value = null; source.value = ''; uncertainty.value = ''; token.value = crypto.randomUUID()
  chooseKind('task'); formOpen.value = true; notice.value = ''
}
async function edit(row: InboxItem) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    const fresh = await readInbox(row.id)
    if (fresh.status === 'applied') throw new Error('此条目已落实，请到对应页面修改实际记录。')
    editing.value = fresh; proposal.value = structuredClone(fresh.proposal)
    source.value = fresh.source_excerpt; uncertainty.value = fresh.uncertainty; formOpen.value = true
  } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { busy.value = false }
}
async function save() {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    if (editing.value) await reviseInbox(editing.value.id, {
      version: editing.value.version, proposal: proposal.value, uncertainty: uncertainty.value,
    })
    else await captureInbox({ capture_key: token.value, items: [{ item_key: 'manual', source_excerpt: source.value,
      uncertainty: uncertainty.value, proposal: proposal.value }] })
    formOpen.value = false; editing.value = null; status.value = 'pending'; offset.value = 0
    await load(); notice.value = '已保存候选。核对后点“确认落实”，才会加入实际安排或账本。'
  } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { busy.value = false }
}
async function act(row: InboxItem, action: 'apply' | 'reject') {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const saved = await (action === 'apply' ? applyInbox(row) : rejectInbox(row))
    if (editing.value?.id === row.id) { editing.value = null; formOpen.value = false }
    await load()
    notice.value = action === 'reject' ? '已忽略，原文和处理记录会保留。'
      : saved.target_state === 'active' ? `已加入${labels[saved.proposal.kind] === '收支' ? '账本' : labels[saved.proposal.kind]}。可在“已落实”中查看来源。`
      : '这条材料此前已落实，目标后来被删除；本次没有重复创建。'
    if (action === 'apply') window.dispatchEvent(new Event('zhishi:tasks-changed'))
  } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { busy.value = false }
}
watch(status, () => { offset.value = 0; void load() })
watch(offset, () => { void load() })
const run = useRunStore()
watch(() => run.phase, phase => { if (phase === 'completed' || phase === 'cancelled' || phase === 'awaiting_approval') void load() })
onMounted(() => { void load(); window.addEventListener('focus', load) })
onUnmounted(() => { generation++; window.removeEventListener('focus', load) })
</script>

<template>
  <section class="inbox-view" aria-label="材料收件箱">
    <header><div><p class="eyebrow">材料交给知时，安排由你掌握</p><h1>收件箱</h1><p class="hint">把文件、图片交给左侧对话，说“帮我整理”。在这里核对待办、日程和收支。</p></div><button @click="blank" :disabled="busy">＋ 手动整理</button></header>
    <div class="workflow"><span>交给知时</span><span>→</span><strong>核对候选</strong><span>→</span><span>落实安排</span></div>
    <div v-if="error" class="error" role="alert">{{ error }} <button @click="load">刷新列表</button><button v-if="editing" @click="edit(editing)" :disabled="busy">重新读取候选</button></div>
    <div v-if="notice" class="notice" role="status">{{ notice }}</div>
    <form v-if="formOpen" @submit.prevent="save" class="editor">
      <div class="row-head"><h2>{{ editing ? '核对与修正' : '整理一条材料' }}</h2><button type="button" @click="formOpen = false" :disabled="busy">取消</button></div>
      <label>整理为<select :value="proposal.kind" @change="chooseKind(($event.target as HTMLSelectElement).value as InboxProposal['kind'])"><option value="task">待办</option><option value="event">日程</option><option value="ledger">收支</option></select></label>
      <label>原文依据<textarea v-model="source" rows="3" required maxlength="8000" :readonly="!!editing" placeholder="粘贴通知、收据或你的原始想法"></textarea></label>
      <InboxDraftFields v-model="proposal" />
      <label>待澄清的问题<textarea v-model="uncertainty" rows="2" maxlength="2000" placeholder="还有哪些信息不确定？解决后清空，即可确认落实。"></textarea></label>
      <p class="hint">请按原文或你确认的信息修正。候选仍有疑问时，系统会暂停落实。</p>
      <button class="primary" :disabled="busy">{{ busy ? '保存中…' : editing?.status === 'rejected' ? '保存并放回待确认' : '保存候选' }}</button>
    </form>
    <nav class="tabs" aria-label="收件箱状态"><button v-for="tab in tabs" :key="tab.value" :aria-pressed="status === tab.value" :class="{ active: status === tab.value }" @click="status = tab.value">{{ tab.label }}</button><button @click="load" :disabled="loading" class="refresh">{{ loading ? '读取中…' : '刷新' }}</button></nav>
    <p v-if="!loading && !error" class="hint">{{ total }} 条{{ tabs.find(t => t.value === status)?.label }}材料</p>
    <div v-if="!loading && !error && !rows.length" class="empty"><h2>{{ status === 'pending' ? '眼前已理清，随时接收新材料' : '这里还没有处理记录' }}</h2><p>一张收据、一份通知，或一个待办想法，都可以交给知时整理。</p><p class="hint">知时提取的候选会保留原文；相同文件重传时，可查到此前的处理结果。</p></div>
    <div v-if="!loading && !error" class="cards">
      <article v-for="item in rows" :key="item.id">
        <div class="row-head"><span class="badge">{{ labels[item.proposal.kind] }}</span><span class="hint">{{ item.source_name }}</span></div>
        <h2>{{ describeProposal(item.proposal).title }}</h2><p class="hint">{{ describeProposal(item.proposal).detail }}</p>
        <p v-if="item.proposal.data.notes" class="notes">{{ item.proposal.data.notes }}</p>
        <div v-if="item.uncertainty" class="question"><strong>需要核对</strong><p>{{ item.uncertainty }}</p></div>
        <details><summary>查看原文依据</summary><blockquote>{{ item.source_excerpt }}</blockquote></details>
        <div v-if="item.status === 'pending'" class="actions"><button @click="edit(item)" :disabled="busy">核对 / 编辑</button><button @click="act(item, 'reject')" :disabled="busy">忽略</button><button class="primary" @click="act(item, 'apply')" :disabled="busy || !!item.uncertainty.trim()">确认落实</button></div>
        <div v-else-if="item.status === 'rejected'" class="actions"><button @click="edit(item)" :disabled="busy">修正并重新整理</button></div>
        <div v-else class="applied"><span>{{ item.target_state === 'active' ? '已落实' : '原记录已删除，保留处理历史' }}</span><RouterLink :to="item.proposal.kind === 'ledger' ? '/ledger' : item.proposal.kind === 'event' ? `/calendar?date=${item.proposal.data.date}&event=${item.target_id}` : '/board'">打开{{ item.proposal.kind === 'ledger' ? '账本' : item.proposal.kind === 'event' ? '日历' : '看板' }} →</RouterLink></div>
      </article>
    </div>
    <div v-if="total > 30" class="pager"><button @click="offset = Math.max(0, offset - 30)" :disabled="loading || offset === 0">上一页</button><span>{{ Math.floor(offset / 30) + 1 }} / {{ Math.ceil(total / 30) }}</span><button @click="offset += 30" :disabled="loading || offset + 30 >= total">下一页</button></div>
  </section>
</template>

<style scoped>
.inbox-view { padding: 24px; max-width: 1000px; width: 100%; margin: auto; color: var(--ink); }
header,.row-head,.actions,.tabs,.applied,.pager { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
header { align-items: flex-start; }.eyebrow { font-size: 12px; color: var(--ink-3); margin: 0 0 7px; }
h1 { font-size: 28px; font-family: var(--serif); margin: 0; } h2 { margin: 0; font-size: 16px; line-height: 1.6; overflow-wrap: anywhere; }
.hint { font-size: 12px; color: var(--ink-3); line-height: 1.8; }.workflow { display: flex; gap: 16px; padding: 15px 0 22px; font-size: 12px; color: var(--ink-3); }.workflow strong { color: var(--amber); }
button,input,textarea,select { font: inherit; color: var(--ink); } button { border: 1px solid var(--line); border-radius: 7px; padding: 8px 11px; background: var(--bg-raise); cursor: pointer; white-space: nowrap; font-size: 12px; }
button:hover { border-color: var(--ink-3); }button:disabled { opacity: .5; cursor: default; }.primary { background: var(--amber); color: var(--btn-ok-text); border-color: transparent; font-weight: 600; }
button:focus-visible,textarea:focus-visible,select:focus-visible,a:focus-visible,summary:focus-visible { outline: 2px solid var(--amber); outline-offset: 2px; }
.tabs { justify-content: flex-start; padding-bottom: 14px; border-bottom: 1px solid var(--line); }.tabs .active { color: var(--amber); border-color: var(--amber); }.refresh { margin-left: auto; }
.cards { display: grid; gap: 14px; }.cards article,.editor { padding: 18px; border: 1px solid var(--line); border-radius: 12px; background: var(--bg-raise); }.row-head { margin-bottom: 12px; }.row-head .hint { overflow-wrap: anywhere; min-width: 0; }.badge { padding: 3px 7px; font-size: 11px; border: 1px solid var(--line); border-radius: 5px; color: var(--amber); white-space: nowrap; }
.notes,.question p,blockquote { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 12px; line-height: 1.8; }.question { padding: 12px; border-left: 3px solid var(--amber); margin: 12px 0; }.question strong { color: var(--amber); font-size: 12px; }.question p { margin: 6px 0 0; }
details { margin: 15px 0; }summary { font-size: 12px; color: var(--ink-3); cursor: pointer; }blockquote { margin: 12px 0 0; padding-left: 12px; border-left: 2px solid var(--line); max-height: 220px; overflow: auto; color: var(--ink-3); }
.actions { justify-content: flex-end; flex-wrap: wrap; padding-top: 10px; }.applied { color: var(--ok); font-size: 12px; padding-top: 12px; border-top: 1px solid var(--line); }.applied a { color: var(--amber); }
.editor { display: grid; gap: 12px; margin-bottom: 24px; }.editor .row-head { margin: 0; }label { display: flex; flex-direction: column; gap: 6px; font-size: 12px; color: var(--ink-3); }textarea,select { padding: 10px; border: 1px solid var(--line); border-radius: 7px; background: var(--bg-raise); width: 100%; }textarea:read-only { color: var(--ink-3); }
.error,.notice { padding: 12px; border: 1px solid var(--line); border-radius: 8px; margin-bottom: 16px; line-height: 1.8; font-size: 12px; }.error { color: var(--terra); }.notice { color: var(--amber); }
.empty { padding: 40px 12px; text-align: center; color: var(--ink-3); }.empty p { font-size: 13px; line-height: 1.8; }.pager { justify-content: center; padding: 22px 0; font-size: 12px; }
@media(max-width:700px) { .inbox-view { padding: 16px; }header { flex-wrap: wrap; }.workflow { gap: 10px; }.cards article { padding: 14px; } }
</style>
