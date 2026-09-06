<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import BillManager from '../components/BillManager.vue'
import { useRunStore } from '../stores/run'
import { toIsoDate } from '../utils/date'
import { currencies, monthRange, listLedger, ledgerSummary, readEntry, createEntry,
  replaceEntry, deleteEntry, restoreEntry, type LedgerEntry, type LedgerInput,
  type LedgerCurrency, type LedgerSummary } from '../api/ledger'

const today = () => toIsoDate(new Date())
const month = ref(today().slice(0, 7))
const currency = ref<LedgerCurrency>('CNY')
const account = ref('')
const search = ref('')
const deleted = ref(false)
const offset = ref(0)
const rows = ref<LedgerEntry[]>([])
const total = ref(0)
const summary = ref<LedgerSummary | null>(null)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const notice = ref('')
const editing = ref<LedgerEntry | null>(null)
const showForm = ref(false)
const undoEntry = ref<LedgerEntry | null>(null)
const token = ref(crypto.randomUUID())
const draft = reactive<LedgerInput>({ day: today(), direction: 'expense', amount: '', currency: 'CNY',
  category: '餐饮', account: '默认账户', payee: '', notes: '', source_file_id: null, source_excerpt: '' })
const totals = computed(() => summary.value?.currencies.find(c => c.currency === currency.value))
const zero = computed(() => currency.value === 'JPY' ? '0' : '0.00')
let generation = 0

async function load() {
  const current = ++generation
  loading.value = true; error.value = ''
  try {
    const range = { ...monthRange(month.value), currency: currency.value, account: account.value || undefined }
    const [page, report] = await Promise.all([
      listLedger({ ...range, query: search.value, deleted: deleted.value, offset: offset.value }),
      ledgerSummary(range),
    ])
    if (current !== generation) return
    rows.value = page.items; total.value = page.total; summary.value = report
  } catch (e) { if (current === generation) error.value = e instanceof Error ? e.message : String(e) }
  finally { if (current === generation) loading.value = false }
}
function blank() {
  editing.value = null; token.value = crypto.randomUUID()
  Object.assign(draft, { day: today(), direction: 'expense', amount: '', currency: currency.value,
    category: '餐饮', account: account.value || '默认账户', payee: '', notes: '', source_file_id: null, source_excerpt: '' })
  showForm.value = true; notice.value = ''
}
async function edit(row: LedgerEntry) {
  if (saving.value) return
  error.value = ''
  try {
    const fresh = await readEntry(row.id)
    if (fresh.deleted_at) throw new Error('这笔账已在回收站，请恢复后编辑')
    editing.value = fresh
    for (const field of ['day', 'direction', 'amount', 'currency', 'category', 'account', 'payee', 'notes', 'source_file_id', 'source_excerpt'] as const) {
      Object.assign(draft, { [field]: fresh[field] })
    }
    showForm.value = true
  } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
}
async function save() {
  if (saving.value) return
  saving.value = true; error.value = ''; notice.value = ''
  try {
    const input = { ...draft }
    let saved: LedgerEntry
    if (editing.value) saved = await replaceEntry(editing.value.id, { ...input, version: editing.value.version })
    else saved = await createEntry({ ...input, idempotency_key: token.value })
    showForm.value = false; editing.value = null; token.value = crypto.randomUUID()
    month.value = saved.day.slice(0, 7); currency.value = saved.currency
    account.value = ''; search.value = ''; deleted.value = false; offset.value = 0
    await load()
    notice.value = saved.deleted_at ? '此请求此前已记账且现已删除，可在回收站查看。' : '已保存到账本。'
  } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { saving.value = false }
}
async function remove(row: LedgerEntry) {
  if (saving.value) return
  saving.value = true; error.value = ''
  try { undoEntry.value = await deleteEntry(row); await load(); notice.value = '已移入账本回收站。' }
  catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { saving.value = false }
}
async function restore(row: LedgerEntry) {
  if (saving.value) return
  saving.value = true; error.value = ''
  try { await restoreEntry(row); undoEntry.value = null; await load(); notice.value = '已恢复，重新计入收支汇总。' }
  catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { saving.value = false }
}
function filter() { offset.value = 0; void load() }
watch([month, currency, deleted], filter)
watch(offset, () => { void load() })
const run = useRunStore()
watch(() => run.phase, phase => { if (phase === 'completed' || phase === 'cancelled') void load() })
onMounted(() => { void load(); window.addEventListener('focus', load) })
onUnmounted(() => { generation++; window.removeEventListener('focus', load) })
</script>

<template>
  <section class="ledger-view" aria-label="个人账本">
    <div class="intro"><div><p class="eyebrow">把日子过得心中有数</p><h1>个人账本</h1><p class="hint">对话记下每笔收支，也可以把收据交给知时。</p></div><button class="primary" @click="blank" :disabled="saving">＋ 记一笔</button></div>
    <BillManager @updated="load" />
    <div class="filters">
      <label>月份<input type="month" v-model="month" required aria-label="账本月份"></label>
      <label>币种<select v-model="currency" aria-label="汇总币种"><option v-for="c in currencies" :key="c">{{ c }}</option></select></label>
      <label>账户<input v-model="account" placeholder="全部账户" @change="filter" @keyup.enter="filter" aria-label="筛选账户"></label>
      <button @click="load" :disabled="loading">{{ loading ? '更新中…' : '刷新' }}</button>
    </div>
    <div v-if="error" class="error" role="alert">{{ error }} <button @click="load">重新读取列表</button><button v-if="editing" @click="edit(editing)">重新读取正在编辑的账目</button></div>
    <div class="totals" :aria-busy="loading">
      <article><span>本月收入 · {{ currency }}</span><strong>{{ loading || error ? '—' : totals?.income ?? zero }}</strong></article>
      <article><span>本月支出 · {{ currency }}</span><strong>{{ loading || error ? '—' : totals?.expense ?? zero }}</strong></article>
      <article><span>净收支 · {{ currency }}</span><strong>{{ loading || error ? '—' : totals?.net ?? zero }}</strong></article>
    </div>
    <p class="hint">按所选月份、账户和币种汇总；不同币种分别记账，回收站条目不计入。</p>
    <form v-if="showForm" class="entry-form" @submit.prevent="save">
      <div class="form-head"><h2>{{ editing ? '修正账目' : '记下一笔收支' }}</h2><button type="button" @click="showForm = false" :disabled="saving">取消</button></div>
      <div class="fields">
        <label>收支<select v-model="draft.direction"><option value="expense">支出</option><option value="income">收入</option></select></label>
        <label>日期<input type="date" v-model="draft.day" required></label>
        <label>金额<input v-model="draft.amount" inputmode="decimal" placeholder="0.00" required aria-label="记账金额"></label>
        <label>币种<select v-model="draft.currency"><option v-for="c in currencies" :key="c">{{ c }}</option></select></label>
        <label>分类<input v-model="draft.category" list="ledger-categories" maxlength="50" required></label>
        <label>账户<input v-model="draft.account" maxlength="80" required></label>
      </div>
      <datalist id="ledger-categories"><option v-for="c in ['餐饮','交通','购物','居住','学习','健康','娱乐','工资','其他','未分类']" :key="c">{{ c }}</option></datalist>
      <label>商户 / 对方<input v-model="draft.payee" maxlength="200" placeholder="例如：楼下咖啡店"></label>
      <label>备注<textarea v-model="draft.notes" rows="2" maxlength="10000" placeholder="补充这笔收支的用途"></textarea></label>
      <p v-if="draft.source_file_id || draft.source_excerpt" class="source">来源附件 #{{ draft.source_file_id ?? '已移除' }} · {{ draft.source_excerpt }}</p>
      <button class="primary" type="submit" :disabled="saving">{{ saving ? '保存中…' : '保存账目' }}</button>
    </form>
    <div v-if="notice" class="notice" role="status">{{ notice }} <button v-if="undoEntry" @click="restore(undoEntry)" :disabled="saving">撤销删除</button></div>
    <div class="list-head"><h2>{{ deleted ? '账本回收站' : '收支明细' }} <small>{{ total }} 笔</small></h2><label class="check"><input type="checkbox" v-model="deleted">回收站</label></div>
    <div class="search"><input v-model="search" placeholder="搜索分类、商户或备注" @keyup.enter="filter" aria-label="搜索账目"><button @click="filter">搜索</button></div>
    <p v-if="!loading && !error && !rows.length" class="empty">{{ deleted ? '这个月份的回收站是空的。' : '还没有符合条件的账目。记下第一笔，或试着对知时说“今天午饭花了 28 元”。' }}</p>
    <ul v-if="!loading && !error" class="entries">
      <li v-for="row in rows" :key="row.id">
        <div class="entry-info"><strong>{{ row.category }}<span v-if="row.payee"> · {{ row.payee }}</span></strong><p>{{ row.day }} · {{ row.account }}</p><p v-if="row.notes">{{ row.notes }}</p><p v-if="row.source_file_id || row.source_excerpt" class="source">凭据 #{{ row.source_file_id ?? '已移除' }} · {{ row.source_excerpt }}</p></div>
        <div class="entry-actions"><strong class="money" :class="row.direction">{{ row.direction === 'income' ? '+' : '−' }}{{ row.amount }} <small>{{ row.currency }}</small></strong><div><button v-if="!deleted" @click="edit(row)" :disabled="saving">编辑</button><button v-if="!deleted" @click="remove(row)" :disabled="saving">移入回收站</button><button v-else @click="restore(row)" :disabled="saving">恢复</button></div></div>
      </li>
    </ul>
    <div class="pager"><button @click="offset = Math.max(0, offset - 50)" :disabled="offset === 0 || loading">上一页</button><span>{{ Math.floor(offset / 50) + 1 }} / {{ Math.max(1, Math.ceil(total / 50)) }}</span><button @click="offset += 50" :disabled="offset + 50 >= total || loading">下一页</button></div>
    <details v-if="totals?.categories.length"><summary>本月分类汇总</summary><div v-for="c in totals.categories" :key="c.direction + c.category" class="category"><span>{{ c.direction === 'income' ? '收入' : '支出' }} · {{ c.category }}（{{ c.count }} 笔）</span><strong>{{ c.amount }} {{ currency }}</strong></div></details>
  </section>
</template>

<style scoped>
.ledger-view { padding: 24px; color: var(--ink); max-width: 1100px; margin: auto; width: 100%; }
.intro,.form-head,.list-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.eyebrow { color: var(--ink-3); font-size: 12px; margin: 0 0 6px; }
h1 { font-size: 28px; margin: 0; font-family: var(--font-serif); } h2 { font-size: 16px; margin: 0; } small { font-size: 11px; font-weight: normal; }
.hint { font-size: 12px; color: var(--ink-3); line-height: 1.7; }
.filters { display: flex; gap: 12px; flex-wrap: wrap; align-items: end; margin: 22px 0; }
label { display: flex; flex-direction: column; gap: 6px; font-size: 12px; color: var(--ink-3); }
input,select,textarea,button { font: inherit; color: var(--ink); }
input,select,textarea { border: 1px solid var(--line); border-radius: 7px; background: var(--bg-raise); padding: 9px 10px; min-width: 0; width: 100%; }
input::placeholder,textarea::placeholder { color: var(--ink-faint); }
button { padding: 8px 11px; border: 1px solid var(--line); border-radius: 7px; background: var(--bg-raise); cursor: pointer; white-space: nowrap; }
button:hover { border-color: var(--ink-3); } button:disabled { opacity: .55; cursor: default; }
.primary { background: var(--amber); color: var(--btn-ok-text); font-weight: 600; border-color: transparent; }
button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible { outline: 2px solid var(--amber); outline-offset: 2px; }
.totals { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 12px; }
.totals article { border: 1px solid var(--line); padding: 16px; border-radius: 11px; background: var(--bg-raise); }
.totals span { display: block; font-size: 11px; color: var(--ink-3); }.totals strong { display: block; font-size: clamp(17px,2vw,26px); margin-top: 10px; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.entry-form { border: 1px solid var(--line); border-radius: 12px; padding: 18px; display: grid; gap: 14px; margin: 20px 0; background: var(--bg-raise); }
.fields { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 12px; }
.error,.notice { padding: 12px; border: 1px solid var(--line); border-radius: 8px; margin: 12px 0; line-height: 1.7; }
.error { color: var(--terra); }.notice { color: var(--amber); }
.check { flex-direction: row; align-items: center; }.check input { width: auto; }
.list-head { margin-top: 26px; }.search { display: flex; gap: 8px; margin: 14px 0; }
.entries { margin: 0; padding: 0; list-style: none; }.entries li { display: flex; gap: 14px; border-bottom: 1px solid var(--line); padding: 18px 0; justify-content: space-between; }
.entry-info { min-width: 0; overflow-wrap: anywhere; }.entry-info p { color: var(--ink-3); font-size: 12px; margin: 7px 0 0; }.entry-info strong { font-size: 14px; }
.source { font-size: 11px; color: var(--ink-3); white-space: pre-wrap; overflow-wrap: anywhere; max-height: 100px; overflow: auto; }
.entry-actions { text-align: right; flex-shrink: 0; }.entry-actions button { margin: 8px 0 0 5px; padding: 5px 7px; font-size: 11px; }
.money { font-size: 17px; font-variant-numeric: tabular-nums; }.income { color: var(--ok); }.expense { color: var(--ink); }
.empty { color: var(--ink-3); line-height: 1.9; padding: 24px 0; }.pager { display: flex; justify-content: center; align-items: center; gap: 15px; margin: 20px 0; font-size: 12px; }
details { border-top: 1px solid var(--line); padding-top: 16px; }summary { cursor: pointer; font-size: 13px; }.category { display: flex; justify-content: space-between; gap: 12px; font-size: 12px; padding: 10px 0; }
@media(max-width:700px) { .ledger-view { padding: 16px; }.fields { grid-template-columns: repeat(2,minmax(0,1fr)); }.entries li { flex-wrap: wrap; }.entry-actions { width: 100%; display: flex; justify-content: space-between; align-items: center; }.intro { align-items: start; }.totals { gap: 6px; }.totals article { padding: 10px; } }
</style>
