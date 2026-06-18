<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  tasks: { type: Array, required: true },
})
const emit = defineEmits(['open', 'create'])

const today = new Date()
const cursor = ref(new Date(today.getFullYear(), today.getMonth(), 1))

const WEEKS = ['一', '二', '三', '四', '五', '六', '日']
const MONTH_LABEL = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']

const cursorLabel = computed(
  () => `${cursor.value.getFullYear()} 年 ${MONTH_LABEL[cursor.value.getMonth()]}`
)

const priColor = (p) =>
  ({ 高: 'var(--pri-high)', 中: 'var(--pri-mid)', 低: 'var(--pri-low)' }[p] || 'var(--pri-mid)')

function sameDay(a, b) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
}

// 计算月视图的格子（含上月末/下月初补齐），按周一起始
const cells = computed(() => {
  const year = cursor.value.getFullYear()
  const month = cursor.value.getMonth()
  const first = new Date(year, month, 1)
  // 周一为起始：getDay() 周日=0 → 6，周一=1 → 0
  const offset = (first.getDay() + 6) % 7
  const start = new Date(year, month, 1 - offset)
  const days = []
  for (let i = 0; i < 42; i++) {
    const d = new Date(start)
    d.setDate(start.getDate() + i)
    days.push(d)
  }
  return days
})

function tasksOn(day) {
  return props.tasks.filter(
    (t) => t.due_date && sameDay(new Date(t.due_date), day) && t.status !== '完成'
  )
}

function prevMonth() {
  cursor.value = new Date(cursor.value.getFullYear(), cursor.value.getMonth() - 1, 1)
}
function nextMonth() {
  cursor.value = new Date(cursor.value.getFullYear(), cursor.value.getMonth() + 1, 1)
}
function goToday() {
  cursor.value = new Date(today.getFullYear(), today.getMonth(), 1)
}
function isToday(d) {
  return sameDay(d, today)
}
function inThisMonth(d) {
  return d.getMonth() === cursor.value.getMonth()
}

const monthStats = computed(() => {
  const year = cursor.value.getFullYear()
  const month = cursor.value.getMonth()
  const list = props.tasks.filter(
    (t) => t.due_date && new Date(t.due_date).getFullYear() === year && new Date(t.due_date).getMonth() === month && t.status !== '完成'
  )
  return list.length
})
</script>

<template>
  <div class="calendar">
    <div class="cal-head">
      <div>
        <h2 class="gradient-text">日历视图</h2>
        <p class="muted">按截止日期看任务分布，一眼发现哪天扎堆。完成的不显示。</p>
      </div>
      <div class="cal-nav">
        <button class="ghost" @click="prevMonth">‹</button>
        <span class="cursor">{{ cursorLabel }}</span>
        <button class="ghost" @click="nextMonth">›</button>
        <button class="ghost today-btn" @click="goToday">今天</button>
      </div>
    </div>

    <div class="month-stat muted">本月未完成 · {{ monthStats }} 项</div>

    <div class="weekdays">
      <div v-for="w in WEEKS" :key="w" class="weekday">{{ w }}</div>
    </div>

    <div class="grid">
      <div
        v-for="(d, i) in cells"
        :key="i"
        class="cell"
        :class="{ today: isToday(d), muted: !inThisMonth(d) }"
      >
        <div class="day">
          {{ d.getDate() }}
        </div>
        <div class="tasks">
          <div
            v-for="t in tasksOn(d)"
            :key="t.id"
            class="chip"
            :style="{ borderLeftColor: priColor(t.priority) }"
            :title="`${t.title}（${t.priority}）`"
            @click="emit('open', t)"
          >
            {{ t.title }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.calendar {
  display: flex;
  flex-direction: column;
  gap: 14px;
  height: 100%;
}
.cal-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}
h2 {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
}
p {
  margin: 6px 0 0;
  font-size: 14px;
}
.cal-nav {
  display: flex;
  align-items: center;
  gap: 6px;
}
.cal-nav button {
  width: 34px;
  height: 34px;
  padding: 0;
  border-radius: var(--radius-pill);
}
.today-btn {
  width: auto;
  padding: 0 14px;
  font-size: 13px;
}
.cursor {
  font-size: 16px;
  font-weight: 700;
  min-width: 120px;
  text-align: center;
}
.month-stat {
  font-size: 13px;
}
.weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 8px;
  text-align: center;
}
.weekday {
  font-size: 13px;
  color: var(--text-soft);
  font-weight: 600;
  padding: 4px 0;
}
.grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 8px;
  flex: 1;
  min-height: 0;
}
.cell {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 6px 8px;
  min-height: 88px;
  box-shadow: var(--shadow-xs), var(--shadow-inset);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cell.muted {
  opacity: 0.45;
}
.cell.today {
  border: 1.5px solid var(--accent);
  box-shadow: 0 0 0 3px var(--accent-glow);
}
.day {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-soft);
}
.cell.today .day {
  color: var(--accent);
}
.tasks {
  display: flex;
  flex-direction: column;
  gap: 3px;
  overflow: hidden;
}
.chip {
  font-size: 12px;
  padding: 3px 6px;
  border-radius: 8px;
  background: var(--surface-2);
  border-left: 3px solid var(--pri-mid);
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: transform 0.15s ease, background 0.2s ease;
}
.chip:hover {
  background: var(--surface-3);
  transform: translateX(2px);
}
@media (max-width: 720px) {
  .weekday:nth-child(n+6),
  .cell {
    font-size: 11px;
  }
  .chip {
    font-size: 0;
    padding: 4px;
    border-left-width: 4px;
    border-radius: 4px;
  }
}
</style>
