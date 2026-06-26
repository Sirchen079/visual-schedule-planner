<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  tasks: { type: Array, required: true },
})
const emit = defineEmits(['open', 'create'])

const today = new Date()
const cursor = ref(new Date(today.getFullYear(), today.getMonth(), 1))

const WEEKS = ['一', '二', '三', '四', '五', '六', '日']
const MONTH_LABEL = ['1 月', '2 月', '3 月', '4 月', '5 月', '6 月', '7 月', '8 月', '9 月', '10 月', '11 月', '12 月']

const cursorLabel = computed(
  () => `${cursor.value.getFullYear()} 年 ${MONTH_LABEL[cursor.value.getMonth()]}`
)

const PRI_HEX = { 高: '#f26b7a', 中: '#fbbf7a', 低: '#74e69c' }

// 优先用任务第一个标签的颜色，无标签则按优先级（设计：日历按分类着色）
function colorOf(t) {
  return (t.tags && t.tags.length ? t.tags[0].color : PRI_HEX[t.priority]) || PRI_HEX['中']
}
function bgOf(c) {
  return c + '22'
}
function taskHint(t) {
  const tag = t.tags && t.tags.length ? t.tags[0].name : ''
  return tag ? `${t.title}（${tag}）` : `${t.title}（${t.priority}）`
}

function sameDay(a, b) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
}

const cells = computed(() => {
  const year = cursor.value.getFullYear()
  const month = cursor.value.getMonth()
  const first = new Date(year, month, 1)
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
  return props.tasks.filter(
    (t) => t.due_date && new Date(t.due_date).getFullYear() === year && new Date(t.due_date).getMonth() === month && t.status !== '完成'
  ).length
})
</script>

<template>
  <div class="calendar">
    <div class="cal-head">
      <div class="cal-title">
        <h2 class="page-title">
          <span class="page-title-icon float">📅</span>
          <span class="gradient-text">日历视图</span>
        </h2>
        <p class="muted">按截止日期看任务分布，一眼发现哪天扎堆。</p>
      </div>
      <div class="cal-actions">
        <div class="cal-nav">
          <button class="ghost nav-btn" @click="prevMonth">‹</button>
          <span class="cursor">{{ cursorLabel }}</span>
          <button class="ghost nav-btn" @click="nextMonth">›</button>
        </div>
        <button class="ghost today-btn" @click="goToday">今天</button>
        <button class="create-btn" @click="emit('create')">
          <span class="btn-icon">＋</span>
          <span>新建</span>
        </button>
      </div>
    </div>

    <div class="month-stat">
      <span class="stat-bubble">{{ monthStats }}</span>
      <span class="muted">本月待完成任务</span>
    </div>

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
        <div class="day-bar">
          <span class="day-num">{{ d.getDate() }}</span>
          <span v-if="tasksOn(d).length" class="day-count">{{ tasksOn(d).length }}</span>
        </div>
        <div class="tasks">
          <div
            v-for="t in tasksOn(d)"
            :key="t.id"
            class="chip"
            :style="{ background: bgOf(colorOf(t)), color: colorOf(t), borderColor: colorOf(t) + '55' }"
            :title="taskHint(t)"
            @click="emit('open', t)"
          >
            <span class="chip-dot" :style="{ background: colorOf(t) }"></span>
            <span class="chip-text">{{ t.title }}</span>
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
  gap: 16px;
  height: 100%;
  max-width: 1200px;
  margin: 0 auto;
}

.cal-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-shrink: 0;
}

.cal-title h2 {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: 0.5px;
  white-space: nowrap;
}

.cal-title p {
  margin: 6px 0 0;
  font-size: 14px;
}

.cal-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.cal-nav {
  display: flex;
  align-items: center;
  gap: 4px;
  background: var(--surface-2);
  padding: 4px;
  border-radius: var(--radius-pill);
  box-shadow: var(--shadow-inset);
}

.nav-btn {
  width: 32px;
  height: 32px;
  padding: 0;
  border-radius: 50%;
  font-size: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.cursor {
  font-size: 15px;
  font-weight: 700;
  min-width: 110px;
  text-align: center;
  color: var(--text);
  padding: 0 6px;
}

.today-btn {
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 600;
}

.create-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 10px 18px;
  font-size: 14px;
  font-weight: 600;
}

.btn-icon {
  display: inline-block;
  font-size: 16px;
  transition: transform 0.3s ease;
}

.create-btn:hover .btn-icon {
  transform: rotate(90deg);
}

.month-stat {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  align-self: flex-start;
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 6px 14px;
  border-radius: var(--radius-pill);
  box-shadow: var(--shadow-xs), var(--shadow-inset);
}

.stat-bubble {
  background: var(--accent);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  min-width: 22px;
  height: 22px;
  line-height: 22px;
  text-align: center;
  border-radius: 50%;
}

.weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 10px;
  text-align: center;
}

.weekday {
  font-size: 13px;
  color: var(--text-soft);
  font-weight: 700;
  padding: 6px 0;
}

.grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 10px;
  flex: 1;
  min-height: 0;
}

.cell {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 8px;
  min-height: 96px;
  box-shadow: var(--shadow-xs), var(--shadow-inset);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 6px;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.cell:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm), var(--shadow-inset);
  border-color: var(--border-strong);
}

.cell.muted {
  opacity: 0.42;
  background: var(--surface-2);
}

.cell.today {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-glow), var(--shadow-sm), var(--shadow-inset);
}

.cell.today:hover {
  box-shadow: 0 0 0 4px var(--accent-glow), var(--shadow-md), var(--shadow-inset);
}

.day-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.day-num {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-soft);
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
}

.cell.today .day-num {
  background: var(--accent);
  color: #fff;
  box-shadow: 0 2px 8px var(--accent-glow);
}

.day-count {
  font-size: 11px;
  font-weight: 700;
  color: var(--accent);
  background: var(--accent-soft);
  padding: 2px 7px;
  border-radius: var(--radius-pill);
}

.tasks {
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow: hidden;
}

.chip {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  padding: 4px 7px;
  border-radius: 8px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.chip:hover {
  transform: translateX(2px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.chip-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.chip-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 760px) {
  .cal-head {
    align-items: center;
  }
  .cal-title p {
    display: none;
  }
  .cal-actions {
    gap: 6px;
  }
  .today-btn span,
  .create-btn span:last-child {
    display: none;
  }
  .cursor {
    min-width: 90px;
    font-size: 13px;
  }
  .grid {
    gap: 6px;
  }
  .cell {
    min-height: 72px;
    padding: 5px;
    border-radius: 12px;
  }
  .weekdays {
    gap: 6px;
  }
  .weekday {
    font-size: 12px;
  }
  .chip-text {
    display: none;
  }
  .chip {
    padding: 4px;
    justify-content: center;
  }
  .chip-dot {
    width: 7px;
    height: 7px;
  }
}
</style>
