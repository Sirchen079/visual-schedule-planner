<script setup>
import { computed } from 'vue'

const props = defineProps({
  tasks: { type: Array, required: true },
})
const emit = defineEmits(['open'])

function startOfDay(d) {
  const x = new Date(d)
  x.setHours(0, 0, 0, 0)
  return x
}

const now = new Date()
const todayStart = startOfDay(now)
const todayEnd = new Date(todayStart)
todayEnd.setHours(23, 59, 59, 999)
// 本周末（周日 23:59:59）
const weekEnd = new Date(todayStart)
const daysToSunday = 7 - (now.getDay() || 7) + 1
weekEnd.setDate(weekEnd.getDate() + daysToSunday - 1)
weekEnd.setHours(23, 59, 59, 999)

const active = computed(() => props.tasks.filter((t) => t.status !== '完成'))
const todayDue = computed(
  () =>
    active.value.filter((t) => {
      if (!t.due_date) return false
      const d = new Date(t.due_date)
      return d >= todayStart && d <= todayEnd
    })
)
const weekDue = computed(
  () =>
    active.value.filter((t) => {
      if (!t.due_date) return false
      const d = new Date(t.due_date)
      return d > todayEnd && d <= weekEnd
    })
)
const overdue = computed(
  () =>
    active.value.filter((t) => {
      if (!t.due_date) return false
      return new Date(t.due_date) < todayStart
    })
)

const statusCount = computed(() => ({
  待办: props.tasks.filter((t) => t.status === '待办').length,
  进行中: props.tasks.filter((t) => t.status === '进行中').length,
  完成: props.tasks.filter((t) => t.status === '完成').length,
}))
const doneRate = computed(() => {
  if (!props.tasks.length) return 0
  return Math.round((statusCount.value.完成 / props.tasks.length) * 100)
})
</script>

<template>
  <div class="overview">
    <div class="top">
      <div class="stat card">
        <div class="num">{{ todayDue.length }}</div>
        <div class="label">今日到期</div>
      </div>
      <div class="stat card">
        <div class="num">{{ weekDue.length }}</div>
        <div class="label">本周截止</div>
      </div>
      <div class="stat card" :class="{ alert: overdue.length }">
        <div class="num">{{ overdue.length }}</div>
        <div class="label">{{ overdue.length ? '⚠️ 逾期' : '逾期' }}</div>
      </div>
      <div class="stat card">
        <div class="num">{{ doneRate }}%</div>
        <div class="label">完成率</div>
      </div>
    </div>

    <div class="section card" v-if="overdue.length">
      <h3>⚠️ 逾期未完成（优先处理）</h3>
      <div class="task-list">
        <div class="li" v-for="t in overdue" :key="t.id" @click="emit('open', t)">
          {{ t.title }}
          <span class="muted">· {{ new Date(t.due_date).toLocaleDateString() }}</span>
        </div>
      </div>
    </div>

    <div class="section card" v-if="todayDue.length">
      <h3>今日到期</h3>
      <div class="task-list">
        <div class="li" v-for="t in todayDue" :key="t.id" @click="emit('open', t)">
          {{ t.title }}
        </div>
      </div>
    </div>

    <div class="section card" v-if="weekDue.length">
      <h3>本周截止</h3>
      <div class="task-list">
        <div class="li" v-for="t in weekDue" :key="t.id" @click="emit('open', t)">
          {{ t.title }}
          <span class="muted">· {{ new Date(t.due_date).toLocaleDateString() }}</span>
        </div>
      </div>
    </div>

    <div class="section card">
      <h3>状态分布</h3>
      <div class="bars">
        <span class="tag">待办 {{ statusCount.待办 }}</span>
        <span class="tag">进行中 {{ statusCount.进行中 }}</span>
        <span class="tag">完成 {{ statusCount.完成 }}</span>
        <span class="muted">共 {{ tasks.length }} 项</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.overview {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 760px;
}
.top {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}
.stat {
  text-align: center;
}
.stat .num {
  font-size: 30px;
  font-weight: 700;
  color: var(--accent);
}
.stat .label {
  color: var(--text-soft);
  font-size: 13px;
  margin-top: 2px;
}
.stat.alert .num {
  color: var(--pri-high);
}
.section h3 {
  margin: 0 0 10px;
  font-size: 15px;
}
.task-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.li {
  padding: 7px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
}
.li:hover {
  background: var(--surface-2);
}
.bars {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
</style>
