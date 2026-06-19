<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'

const props = defineProps({
  tasks: { type: Array, required: true },
})
const emit = defineEmits(['open'])

function startOfDay(d) {
  const x = new Date(d)
  x.setHours(0, 0, 0, 0)
  return x
}

// 跨天后自动刷新日期边界，避免总览"卡在昨天"
const todayMarker = ref(new Date())
let dateTimer = null
onMounted(() => {
  dateTimer = setInterval(() => {
    const n = new Date()
    if (n.toDateString() !== todayMarker.value.toDateString()) todayMarker.value = n
  }, 60000)
})
onUnmounted(() => {
  if (dateTimer) clearInterval(dateTimer)
})

const todayStart = computed(() => startOfDay(todayMarker.value))
const todayEnd = computed(() => {
  const e = new Date(todayStart.value)
  e.setHours(23, 59, 59, 999)
  return e
})
const weekEnd = computed(() => {
  const w = new Date(todayStart.value)
  const daysToSunday = 7 - (todayMarker.value.getDay() || 7) + 1
  w.setDate(w.getDate() + daysToSunday - 1)
  w.setHours(23, 59, 59, 999)
  return w
})

const active = computed(() => props.tasks.filter((t) => t.status !== '完成'))
const todayDue = computed(() =>
  active.value.filter((t) => {
    if (!t.due_date) return false
    const d = new Date(t.due_date)
    return d >= todayStart.value && d <= todayEnd.value
  })
)
const weekDue = computed(() =>
  active.value.filter((t) => {
    if (!t.due_date) return false
    const d = new Date(t.due_date)
    return d > todayEnd.value && d <= weekEnd.value
  })
)
const overdue = computed(() =>
  active.value.filter((t) => {
    if (!t.due_date) return false
    return new Date(t.due_date) < todayStart.value
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

const stats = computed(() => [
  { label: '今日到期', value: todayDue.value.length, icon: '🐚', tone: 'calm' },
  { label: '本周截止', value: weekDue.value.length, icon: '🌊', tone: 'calm' },
  { label: overdue.value.length ? '已逾期' : '无逾期', value: overdue.value.length, icon: overdue.value.length ? '⛈️' : '☀️', tone: overdue.value.length ? 'alert' : 'calm' },
  { label: '完成率', value: `${doneRate.value}%`, icon: '✨', tone: 'calm' },
])
</script>

<template>
  <div class="overview">
    <div class="overview-head">
      <h2 class="gradient-text">日程总览</h2>
      <p class="muted">像俯瞰一片海湾，看清每颗贝壳的位置。</p>
    </div>

    <div class="stats-grid">
      <div
        class="stat card"
        v-for="(s, i) in stats"
        :key="s.label"
        :class="[s.tone, 'animate-in']"
        :style="{ animationDelay: `${i * 0.08}s` }"
      >
        <div class="stat-icon float-slow">{{ s.icon }}</div>
        <div class="stat-main">
          <div class="num">{{ s.value }}</div>
          <div class="label">{{ s.label }}</div>
        </div>
      </div>
    </div>

    <div class="sections">
      <div class="section card" v-if="overdue.length">
        <h3><span class="section-icon">⛈️</span>逾期未完成</h3>
        <div class="task-list">
          <div class="li" v-for="t in overdue" :key="t.id" @click="emit('open', t)">
            <span class="li-title">{{ t.title }}</span>
            <span class="muted">{{ new Date(t.due_date).toLocaleDateString() }}</span>
          </div>
        </div>
      </div>

      <div class="section card" v-if="todayDue.length">
        <h3><span class="section-icon">🐚</span>今日到期</h3>
        <div class="task-list">
          <div class="li" v-for="t in todayDue" :key="t.id" @click="emit('open', t)">
            <span class="li-title">{{ t.title }}</span>
            <span class="tag today">今天</span>
          </div>
        </div>
      </div>

      <div class="section card" v-if="weekDue.length">
        <h3><span class="section-icon">🌊</span>本周截止</h3>
        <div class="task-list">
          <div class="li" v-for="t in weekDue" :key="t.id" @click="emit('open', t)">
            <span class="li-title">{{ t.title }}</span>
            <span class="muted">{{ new Date(t.due_date).toLocaleDateString() }}</span>
          </div>
        </div>
      </div>

      <div class="section card status-section">
        <h3><span class="section-icon">🗺️</span>状态分布</h3>
        <div class="status-grid">
          <div class="status-item" v-for="(count, status) in statusCount" :key="status">
            <span class="status-dot" :class="status"></span>
            <span class="status-name">{{ status }}</span>
            <span class="status-num">{{ count }}</span>
          </div>
        </div>
        <div class="progress-track">
          <div
            class="progress-bar done"
            :style="{ width: `${(statusCount['完成'] / Math.max(props.tasks.length, 1)) * 100}%` }"
          ></div>
          <div
            class="progress-bar doing"
            :style="{ width: `${(statusCount['进行中'] / Math.max(props.tasks.length, 1)) * 100}%` }"
          ></div>
        </div>
        <p class="muted total">共 {{ tasks.length }} 项任务 · 完成率 {{ doneRate }}%</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.overview {
  display: flex;
  flex-direction: column;
  gap: 22px;
  max-width: 860px;
  margin: 0 auto;
}

.overview-head h2 {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: 0.5px;
  white-space: nowrap;
}

.overview-head p {
  margin: 6px 0 0;
  font-size: 14px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.stat {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 20px;
}

.stat-icon {
  width: 50px;
  height: 50px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 16px;
  background: var(--surface-2);
  font-size: 26px;
  flex-shrink: 0;
  box-shadow: var(--shadow-inset);
}

.stat.alert .stat-icon {
  background: rgba(242, 107, 122, 0.1);
}

.stat-main {
  min-width: 0;
}

.stat .num {
  font-size: 28px;
  font-weight: 800;
  color: var(--accent);
  line-height: 1.1;
}

.stat.alert .num {
  color: var(--pri-high);
}

.stat .label {
  color: var(--text-soft);
  font-size: 12px;
  margin-top: 3px;
  font-weight: 500;
}

.sections {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section h3 {
  margin: 0 0 14px;
  font-size: 15px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text);
}

.section-icon {
  font-size: 18px;
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  background: var(--surface-2);
  border: 1px solid transparent;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}

.li:hover {
  transform: translateX(6px);
  box-shadow: var(--shadow-sm);
  border-color: var(--border);
  background: var(--surface);
}

.li-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  font-weight: 500;
  font-size: 14px;
}

.tag.today {
  background: rgba(69, 184, 235, 0.1);
  color: var(--accent-hover);
  border-color: rgba(69, 184, 235, 0.22);
}

.status-section {
  padding-bottom: 20px;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-bottom: 18px;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  transition: transform 0.18s ease, box-shadow 0.18s ease;
}

.status-item:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.待办 { background: var(--pri-high); }
.status-dot.进行中 { background: var(--pri-mid); }
.status-dot.完成 { background: var(--pri-low); }

.status-name {
  color: var(--text-soft);
  font-size: 13px;
  font-weight: 500;
}

.status-num {
  margin-left: auto;
  font-weight: 800;
  color: var(--text);
  font-size: 16px;
}

.progress-track {
  height: 10px;
  border-radius: var(--radius-pill);
  background: var(--surface-2);
  overflow: hidden;
  display: flex;
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.05);
}

.progress-bar {
  height: 100%;
  transition: width 0.8s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.progress-bar.done {
  background: linear-gradient(90deg, var(--foam-300), var(--foam-400));
}

.progress-bar.doing {
  background: linear-gradient(90deg, var(--pri-mid), var(--sand-200));
}

.total {
  margin: 14px 0 0;
  text-align: center;
  font-size: 13px;
}

@media (max-width: 760px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .status-grid {
    grid-template-columns: 1fr;
  }
}
</style>
