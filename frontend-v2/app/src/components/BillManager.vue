<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useRunStore } from '../stores/run'
import { toIsoDate } from '../utils/date'
import { currencies } from '../api/ledger'
import { billHistory, createBill, listBills, payBill, readBill, readOccurrence, skipBill, updateBill,
  type Bill, type BillInput, type Occurrence, type Payment } from '../api/bills'

const emit = defineEmits<{ updated: [] }>()
const route = useRoute()
const run = useRunStore()
const today = () => toIsoDate(new Date())
const rows = ref<Bill[]>([]), total = ref(0), offset = ref(0)
const selected = ref<Bill | null>(null), history = ref<Occurrence[]>([]), before = ref<number | null>(null)
const busy = ref(false), loading = ref(false), error = ref(''), notice = ref('')
const editing = ref<Bill | null>(null), showForm = ref(false), paying = ref<Occurrence | null>(null), skipping = ref<Occurrence | null>(null)
const reason = ref(''), entryId = ref('')
const blank = (): BillInput => ({ title: '', amount: null, currency: 'CNY', category: '居住', account: '默认账户',
  payee: '', notes: '', enabled: true, remind_days: 3, first_due: today(), cycle: 'monthly', request_key: crypto.randomUUID() })
const draft = reactive<BillInput>(blank())
const payment = reactive<Payment>({ version: 1, day: today(), amount: '', account: '默认账户' })
const cycles: Record<string, string> = { once: '一次性', weekly: '每周', monthly: '每月', yearly: '每年' }
let alive = true, generation = 0, selection = 0

async function load() {
  const epoch = ++generation
  loading.value = true
  try {
    const page = await listBills(offset.value)
    if (!alive || epoch !== generation) return
    rows.value = page.items; total.value = page.total
  } catch (e) { if (alive && epoch === generation) error.value = String(e instanceof Error ? e.message : e) }
  finally { if (alive && epoch === generation) loading.value = false }
}
async function open(id: number) {
  const epoch = ++selection
  error.value = ''
  try {
    const [bill, periods] = await Promise.all([readBill(id), billHistory(id)])
    if (!alive || epoch !== selection) return
    selected.value = bill; history.value = periods.items; before.value = periods.next_before
  } catch (e) { if (alive && epoch === selection) error.value = String(e instanceof Error ? e.message : e) }
}
async function act(fn: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { await fn(); if (alive) { await load(); emit('updated') } }
  catch (e) { if (alive) error.value = String(e instanceof Error ? e.message : e) }
  finally { if (alive) busy.value = false }
}
function add() { editing.value = null; Object.assign(draft, blank()); showForm.value = true; paying.value = null; skipping.value = null }
async function edit(id: number) {
  await act(async () => {
    const bill = await readBill(id)
    if (!alive) return
    editing.value = bill
    Object.assign(draft, blank(), bill.details, { first_due: bill.first_due, cycle: bill.cycle })
    showForm.value = true; paying.value = null; skipping.value = null
  })
}
async function save() {
  await act(async () => {
    const { first_due, cycle, request_key, ...details } = { ...draft, amount: draft.amount === '' ? null : draft.amount }
    const bill = editing.value
      ? await updateBill(editing.value.id, { ...details, version: editing.value.version })
      : await createBill({ ...details, first_due, cycle, request_key })
    if (!alive) return
    showForm.value = false; notice.value = '已保存待办账单，尚未计入支出。'; await open(bill.id)
  })
}
async function toggle(row: Bill) {
  await act(async () => {
    const bill = await updateBill(row.id, { ...row.details, enabled: !row.details.enabled, version: row.version })
    notice.value = bill.details.enabled ? '已恢复到期提醒。' : '已暂停到期提醒，待支付与历史记录保留。'
    if (selected.value?.id === bill.id) await open(bill.id)
  })
}
async function beginPay(row: Occurrence) {
  // Always use a fresh version; historical skipped periods keep their original amount/currency.
  await act(async () => {
    const fresh = await readOccurrence(row.id)
    if (fresh.status === 'paid') throw new Error('这期账单已处理，请重新读取历史记录。')
    if (!alive) return
    paying.value = fresh; skipping.value = null; showForm.value = false; entryId.value = ''
    Object.assign(payment, { version: fresh.version, day: today(), amount: fresh.details.amount ?? '',
      account: fresh.details.account, existing_entry_id: null, source_file_id: null, source_excerpt: '' })
  })
}
async function confirmPayment() {
  const row = paying.value
  if (!row) return
  await act(async () => {
    const id = entryId.value.trim() ? Number(entryId.value) : null
    if (id !== null && (!Number.isSafeInteger(id) || id <= 0)) throw new Error('请输入有效的已记账编号。')
    const paid = await payBill(row.id, { ...payment, existing_entry_id: id })
    if (!alive) return
    paying.value = null
    notice.value = `已确认支付，关联账目 #${paid.ledger_entry?.id}。`
    await open(row.bill_id)
  })
}
async function confirmSkip() {
  const row = skipping.value
  if (!row) return
  await act(async () => {
    await skipBill(row.id, row.version, reason.value)
    if (!alive) return
    skipping.value = null; notice.value = '已跳过本期并保留原因，没有产生支出。'; await open(row.bill_id)
  })
}
async function more() {
  const id = selected.value?.id, cursor = before.value, epoch = selection
  if (!id || !cursor) return
  await act(async () => {
    const page = await billHistory(id, cursor)
    if (!alive || epoch !== selection) return
    history.value.push(...page.items); before.value = page.next_before
  })
}
function refresh() { void load(); if (selected.value) void open(selected.value.id) }
function fromRoute() {
  const value = route.query.bill
  if (typeof value === 'string' && /^[1-9]\d*$/.test(value) && Number.isSafeInteger(Number(value))) void open(Number(value))
}
watch(() => route.query.bill, fromRoute)
watch(() => run.phase, p => { if (p === 'completed' || p === 'cancelled') refresh() })
watch(offset, () => { void load() })
onMounted(() => { refresh(); fromRoute(); window.addEventListener('focus', refresh) })
onUnmounted(() => { alive = false; generation++; selection++; window.removeEventListener('focus', refresh) })
</script>

<template>
  <section class="bills" aria-label="待办账单">
    <div class="head"><div><h2>待办账单</h2><p>让房租、订阅和周期费用按时被记起。</p></div><button data-bill-add class="primary" @click="add" :disabled="busy">＋ 添加账单</button></div>
    <p class="hint">这里的金额是待支付估计，确认已支付后才计入账本。提醒在本机 09:00 触发；关闭应用期间的到期账单，重新打开后补发一次。</p>
    <p v-if="error" class="error" role="alert">{{ error }} <button @click="refresh">重新读取账单</button><button v-if="editing" @click="edit(editing.id)" :disabled="busy">重新读取编辑内容</button></p>
    <p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <form v-if="showForm" class="panel" @submit.prevent="save">
      <div class="head"><h3>{{ editing ? '修改账单' : '添加待办账单' }}</h3><button type="button" @click="showForm = false" :disabled="busy">取消</button></div>
      <label>账单名称<input v-model="draft.title" data-bill-title maxlength="200" required placeholder="例如：房租、云盘年费"></label>
      <div class="fields">
        <label>首次到期<input v-model="draft.first_due" data-bill-due type="date" required :disabled="!!editing"></label>
        <label>重复周期<select v-model="draft.cycle" data-bill-cycle :disabled="!!editing"><option v-for="(label, value) in cycles" :value="value" :key="value">{{ label }}</option></select></label>
        <label>预估金额<input v-model="draft.amount" data-bill-amount inputmode="decimal" placeholder="不确定可留空"></label>
        <label>币种<select v-model="draft.currency" data-bill-currency><option v-for="c in currencies" :key="c">{{ c }}</option></select></label>
        <label>分类<input v-model="draft.category" maxlength="50" required></label>
        <label>账户<input v-model="draft.account" maxlength="80" required></label>
        <label>提前提醒（天）<input v-model.number="draft.remind_days" type="number" min="0" max="30" required></label>
        <label class="check"><input v-model="draft.enabled" type="checkbox">启用到期提醒</label>
      </div>
      <p class="hint">每月按首次到期日重复，遇短月按月底计算。修改仅影响当前未处理期及未来；如需更换到期日或周期，请暂停原账单后新建。</p>
      <label>收款方<input v-model="draft.payee" maxlength="200"></label><label>备注<textarea v-model="draft.notes" maxlength="2000" rows="2"></textarea></label>
      <button class="primary" data-bill-save :disabled="busy">{{ busy ? '保存中…' : '保存待办账单' }}</button>
    </form>
    <p v-if="!loading && !rows.length" class="hint">还没有待办账单。添加一次，后续各期会接着提醒。</p>
    <div class="cards" :aria-busy="loading">
      <article v-for="row in rows" :key="row.id" :data-bill-id="row.id" :class="{ chosen: selected?.id === row.id }">
        <div class="head"><h3>{{ row.details.title }}</h3><span>{{ row.details.enabled ? cycles[row.cycle] : '已暂停' }}</span></div>
        <template v-if="row.pending"><p :class="{ overdue: row.pending.due < today() }">{{ row.pending.due < today() ? '待核对逾期账单' : '下期待支付' }} · {{ row.pending.due }}</p><strong>{{ row.pending.details.amount ?? '金额待确认' }} <small v-if="row.pending.details.amount">{{ row.pending.details.currency }}</small></strong></template>
        <p v-else class="hint">本账单已处理完毕</p>
        <div class="actions"><button v-if="row.pending" data-bill-pay @click="beginPay(row.pending)" :disabled="busy">确认已支付</button><button @click="open(row.id)" :disabled="busy">查看记录</button><button @click="edit(row.id)" :disabled="busy">修改</button><button data-bill-toggle @click="toggle(row)" :disabled="busy">{{ row.details.enabled ? '暂停' : '恢复提醒' }}</button></div>
      </article>
    </div>
    <div v-if="total > 20" class="actions"><button @click="offset = Math.max(0, offset - 20)" :disabled="offset === 0 || loading">上一页</button><span>{{ offset + 1 }}–{{ Math.min(offset + 20, total) }} / {{ total }}</span><button @click="offset += 20" :disabled="offset + 20 >= total || loading">下一页</button></div>
    <form v-if="paying" class="panel" @submit.prevent="confirmPayment">
      <div class="head"><h3>确认已支付 · {{ paying.details.title }}</h3><button type="button" @click="paying = null" :disabled="busy">取消</button></div>
      <p class="hint">核对到期 {{ paying.due }} 的这期账单。这里只登记支付结果，不会发起扣款。</p>
      <div class="fields"><label>实际支付日期<input v-model="payment.day" data-payment-day type="date" :max="today()" required></label><label>实际金额 · {{ paying.details.currency }}<input v-model="payment.amount" data-payment-amount inputmode="decimal" required></label><label>支付账户<input v-model="payment.account" required maxlength="80"></label><label>已记过账？关联账目编号<input v-model="entryId" inputmode="numeric" placeholder="未记账则留空"></label></div>
      <p class="hint">填写账目编号将关联已有支出，避免重复记账。关联时核对日期、金额、币种和账户。</p>
      <button class="primary" data-payment-confirm :disabled="busy">{{ busy ? '保存中…' : '确认已支付并关联账本' }}</button>
    </form>
    <section v-if="selected" class="panel" data-bill-history>
      <div class="head"><h3>{{ selected.details.title }} · 每期记录</h3><button @click="selected = null; selection++" :disabled="busy">收起</button></div>
      <p class="hint">逐期处理最早未确认的账单；支付或跳过后出现下一期。跳过的期次仍可补记支付。</p>
      <article v-for="row in history" :key="row.id" class="period">
        <div><strong>{{ row.due }} · {{ row.status === 'paid' ? '已确认支付' : row.status === 'skipped' ? '已跳过' : '待支付' }}</strong><p>{{ row.details.title }} · {{ row.details.amount ?? '金额待确认' }} {{ row.details.currency }}</p>
          <p v-if="row.resolution?.reason">原因：{{ row.resolution.reason }}</p>
          <p v-if="row.ledger_entry">账目 #{{ row.ledger_entry.id }} · {{ row.ledger_entry.day }} · {{ row.ledger_entry.amount }} {{ row.ledger_entry.currency }} · {{ row.ledger_entry.account }}<strong v-if="row.ledger_entry.deleted_at"> · 已在账本回收站</strong></p>
        </div>
        <div class="actions"><button v-if="row.status !== 'paid'" @click="beginPay(row)" :disabled="busy">{{ row.status === 'skipped' ? '补记支付' : '确认已支付' }}</button><button v-if="row.status === 'pending'" data-bill-skip @click="skipping = row; paying = null; reason = ''" :disabled="busy">本期无需支付</button></div>
      </article>
      <button v-if="before" @click="more" :disabled="busy">更早记录</button>
    </section>
    <form v-if="skipping" class="panel" @submit.prevent="confirmSkip"><h3>跳过 {{ skipping.due }} · {{ skipping.details.title }}</h3><label>本期无需支付的原因<input v-model="reason" data-skip-reason required maxlength="500" placeholder="例如：本月免租"></label><div class="actions"><button class="primary" data-skip-confirm :disabled="busy">保存原因并跳过</button><button type="button" @click="skipping = null" :disabled="busy">取消</button></div></form>
  </section>
</template>

<style scoped>
.bills { margin: 22px 0; padding: 20px; border: 1px solid var(--line); border-radius: 12px; background: var(--bg-raise); color: var(--ink); }
.head,.actions,.period { display: flex; justify-content: space-between; align-items: center; gap: 10px; }.actions { justify-content: flex-start; flex-wrap: wrap; margin-top: 12px; }
h2,h3,p { margin: 0; }h2 { font: 20px var(--font-serif); }h3 { font-size: 14px; overflow-wrap: anywhere; }.head p,p.hint,.period p,article > p { font-size: 12px; color: var(--ink-3); line-height: 1.7; margin-top: 7px; }
.head span,small { font-size: 11px; color: var(--ink-3); }.head span { white-space: nowrap; }.hint { margin: 12px 0 !important; }
.cards,.fields { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 12px; }.cards > article { border: 1px solid var(--line); padding: 15px; border-radius: 9px; }.cards > article.chosen { border-color: var(--amber); }.cards strong { display: block; margin: 8px 0; font-size: 20px; }
.panel { margin-top: 16px; border: 1px solid var(--line); padding: 16px; border-radius: 10px; display: grid; gap: 12px; }.period { border-top: 1px solid var(--line); padding: 12px 0; align-items: flex-start; }.period > div { min-width: 0; overflow-wrap: anywhere; }.period .actions { flex-shrink: 0; }.period strong { font-size: 12px; }
label { display: flex; flex-direction: column; gap: 6px; font-size: 12px; color: var(--ink-3); min-width: 0; }.check { flex-direction: row; align-items: center; }.check input { width: auto; }
input,select,textarea,button { font: inherit; color: var(--ink); border: 1px solid var(--line); border-radius: 7px; background: var(--bg-raise); padding: 8px 10px; min-width: 0; }input,select,textarea { width: 100%; }button { cursor: pointer; font-size: 12px; }button:disabled { opacity: .55; cursor: default; }.primary { background: var(--amber); color: var(--btn-ok-text); border-color: transparent; font-weight: 600; }
button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible { outline: 2px solid var(--amber); outline-offset: 2px; }.error,.overdue { color: var(--red, #bd453b) !important; }.notice { color: var(--ink); margin-top: 10px; font-size: 12px; }
@media (max-width: 700px) { .bills { padding: 13px; }.cards,.fields { grid-template-columns: 1fr; }.period { flex-direction: column; }.head { flex-wrap: wrap; } }
</style>
