<script setup lang="ts">
import ReminderFields from './calendar/ReminderFields.vue'
import { computed } from 'vue'
import type { InboxProposal } from '../api/inbox'
import { currencies } from '../api/ledger'
const proposal = defineModel<InboxProposal>({ required: true })
const dueDate = computed({
  get: () => proposal.value.kind === 'task' ? proposal.value.data.due_date?.slice(0, 10) ?? '' : '',
  set: value => { if (proposal.value.kind === 'task') proposal.value.data.due_date = value ? `${value}T00:00:00` : null },
})
</script>
<template>
  <div class="draft-fields">
    <template v-if="proposal.kind === 'task'">
      <label class="wide">待办名称<input v-model="proposal.data.title" required maxlength="200"></label>
      <label>截止日期<input type="date" v-model="dueDate"></label>
      <label>截止时间<input type="time" :value="proposal.data.due_time ?? ''" @input="proposal.data.due_time = ($event.target as HTMLInputElement).value || null"></label>
      <label>优先级<select v-model="proposal.data.priority"><option value="high">高</option><option value="medium">中</option><option value="low">低</option></select></label>
      <label>预计用时（分钟）<input type="number" min="1" :value="proposal.data.estimated_minutes" @input="proposal.data.estimated_minutes = ($event.target as HTMLInputElement).value ? Number(($event.target as HTMLInputElement).value) : null"></label>
    </template>
    <template v-else-if="proposal.kind === 'event'">
      <label class="wide">日程名称<input v-model="proposal.data.title" required maxlength="200"></label>
      <label>日期<input type="date" v-model="proposal.data.date" required></label>
      <label>地点<input v-model="proposal.data.location" placeholder="可留空"></label>
      <label>开始时间<input type="time" :value="proposal.data.start_time ?? ''" @input="proposal.data.start_time = ($event.target as HTMLInputElement).value || null"></label>
      <label>结束时间<input type="time" :value="proposal.data.end_time ?? ''" @input="proposal.data.end_time = ($event.target as HTMLInputElement).value || null"></label>
      <ReminderFields class="wide" v-model:offsets="proposal.data.remind_offsets" v-model:reminder-time="proposal.data.reminder_time" :start-time="proposal.data.start_time" />
      <p class="wide hint">起止时间均留空表示全天；跨天事项请分日整理。</p>
    </template>
    <template v-else>
      <label>收支<select v-model="proposal.data.direction"><option value="expense">支出</option><option value="income">收入</option></select></label>
      <label>记账日期<input type="date" v-model="proposal.data.day" required></label>
      <label>金额<input v-model="proposal.data.amount" inputmode="decimal" required placeholder="实际金额"></label>
      <label>币种<select v-model="proposal.data.currency"><option v-for="c in currencies" :key="c">{{ c }}</option></select></label>
      <label>分类<input v-model="proposal.data.category" maxlength="50" required></label>
      <label>账户<input v-model="proposal.data.account" maxlength="80" required></label>
      <label class="wide">商户 / 对方<input v-model="proposal.data.payee" maxlength="200"></label>
    </template>
    <label class="wide">备注<textarea v-model="proposal.data.notes" rows="2" maxlength="10000"></textarea></label>
    <p v-if="proposal.kind !== 'ledger' && proposal.data.recur_rrule" class="wide hint">此候选含重复安排，保存时会保留原有重复规则。</p>
  </div>
</template>
<style scoped>
.draft-fields { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 12px; }
.wide { grid-column: 1 / -1; } label { display: flex; flex-direction: column; gap: 6px; font-size: 12px; color: var(--ink-3); }
input,select,textarea { width: 100%; min-width: 0; padding: 10px; font: inherit; color: var(--ink); background: var(--bg-raise); border: 1px solid var(--line); border-radius: 7px; }
input:focus-visible,select:focus-visible,textarea:focus-visible { outline: 2px solid var(--amber); outline-offset: 2px; }
.hint { margin: 0; font-size: 12px; color: var(--ink-3); line-height: 1.7; }
</style>
