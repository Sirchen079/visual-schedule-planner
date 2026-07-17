<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import ArtIcon from '../components/ArtIcon.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import PageHeader from '../components/ui/PageHeader.vue'

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
  {
    label: overdue.value.length ? '已逾期' : '无逾期',
    value: overdue.value.length,
    tone: overdue.value.length ? 'alert' : 'calm',
    icon: 'priority',
    iconTone: overdue.value.length ? 'coral' : 'mint',
  },
  {
    label: '今日到期',
    value: todayDue.value.length,
    tone: todayDue.value.length ? 'focus' : 'calm',
    icon: 'calendar',
    iconTone: 'aqua',
  },
  { label: '本周截止', value: weekDue.value.length, tone: 'calm', icon: 'timeline', iconTone: 'sand' },
  { label: '完成率', value: `${doneRate.value}%`, tone: 'calm', icon: 'overview', iconTone: 'mint' },
])

// App.vue 中 openEdit(null) 与 openCreate() 等价(editing 为 null 时保存走新建),
// 空状态「新建任务」沿用现有 open 事件,不新增事件。
function createTask() {
  emit('open', null)
}
</script>

<template>
  <div class="overview workspace-page">
    <PageHeader icon="overview" title="总览" subtitle="从全局看清轻重缓急，让节奏保持平稳。" />

    <EmptyState
      v-if="!tasks.length"
      icon="task"
      title="还没有任务"
      hint="创建第一项任务后，这里会汇总逾期、今日到期、本周截止与完成节奏。"
    >
      <button type="button" class="empty-create" @click="createTask">
        <ArtIcon name="plus" tone="on-accent" :size="16" />
        <span>新建任务</span>
      </button>
    </EmptyState>

    <div v-else class="overview-grid workspace-shell">
      <aside class="overview-rail workspace-rail section-panel">
        <ArtIcon name="overview" tone="mint" :size="62" tile label="完成节奏" />
        <div class="completion">
          <strong>{{ doneRate }}%</strong>
          <span>完成率</span>
        </div>
        <div class="progress-track rail-track">
          <div class="progress-bar done" :style="{ width: `${doneRate}%` }"></div>
        </div>
        <div class="rail-stats">
          <div class="rail-stat" v-for="(count, status) in statusCount" :key="status">
            <span class="status-dot" :data-status="status"></span>
            <span>{{ status }}</span>
            <strong>{{ count }}</strong>
          </div>
        </div>
      </aside>

      <main class="overview-main workspace-main">
        <div class="stats-grid">
          <div
            class="stat metric-tile"
            v-for="(s, i) in stats"
            :key="s.label"
            :class="[s.tone, 'animate-in']"
            :style="{ animationDelay: `${i * 0.08}s` }"
          >
            <ArtIcon
              class="stat-icon"
              :name="s.icon"
              :tone="s.iconTone"
              :size="34"
              tile
              :label="s.label"
            />
            <div class="stat-main">
              <div class="num">{{ s.value }}</div>
              <div class="label">{{ s.label }}</div>
            </div>
          </div>
        </div>

        <div class="sections">
          <div class="section section-panel" v-if="overdue.length">
            <h3>
              <ArtIcon name="priority" tone="coral" :size="30" tile label="逾期" />
              <span>逾期未完成</span>
            </h3>
            <div class="task-list">
              <button class="li" v-for="t in overdue" :key="t.id" @click="emit('open', t)">
                <span class="li-title">{{ t.title }}</span>
                <span class="muted">{{ new Date(t.due_date).toLocaleDateString() }}</span>
              </button>
            </div>
          </div>

          <div class="section section-panel" v-if="todayDue.length">
            <h3>
              <ArtIcon name="calendar" tone="aqua" :size="30" tile label="今日" />
              <span>今日到期</span>
            </h3>
            <div class="task-list">
              <button class="li" v-for="t in todayDue" :key="t.id" @click="emit('open', t)">
                <span class="li-title">{{ t.title }}</span>
                <span class="tag today">今天</span>
              </button>
            </div>
          </div>

          <div class="section section-panel" v-if="weekDue.length">
            <h3>
              <ArtIcon name="timeline" tone="sand" :size="30" tile label="本周" />
              <span>本周截止</span>
            </h3>
            <div class="task-list">
              <button class="li" v-for="t in weekDue" :key="t.id" @click="emit('open', t)">
                <span class="li-title">{{ t.title }}</span>
                <span class="muted">{{ new Date(t.due_date).toLocaleDateString() }}</span>
              </button>
            </div>
          </div>

          <div class="section section-panel status-section">
            <h3>
              <ArtIcon name="board" tone="mint" :size="30" tile label="状态" />
              <span>状态分布</span>
            </h3>
            <div class="status-grid">
              <div class="status-item" v-for="(count, status) in statusCount" :key="status">
                <span class="status-dot" :data-status="status"></span>
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
      </main>

      <aside class="overview-aside workspace-aside section-panel">
        <div class="aside-head">
          <ArtIcon name="assistant" tone="aqua" :size="44" tile label="今日建议" />
          <div>
            <h3>今日建议</h3>
            <p class="muted">把压力、进度和空闲一起看。</p>
          </div>
        </div>
        <div class="advice-list">
          <div class="advice-item" :class="{ urgent: overdue.length }">
            <strong>{{ overdue.length ? '先处理逾期' : '没有逾期压力' }}</strong>
            <span>{{ overdue.length ? `还有 ${overdue.length} 项需要先收住` : '可以按当前节奏推进' }}</span>
          </div>
          <div class="advice-item">
            <strong>今日焦点</strong>
            <span>{{ todayDue.length ? `${todayDue.length} 项今天到期` : '今天没有硬截止项' }}</span>
          </div>
          <div class="advice-item">
            <strong>一周节奏</strong>
            <span>{{ weekDue.length ? `${weekDue.length} 项在本周收束` : '本周收束压力较轻' }}</span>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.overview {
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: none;
  margin: 0 auto;
}

/* 根节点已有 gap,去掉 PageHeader 自带下间距避免叠加 */
.overview :deep(.page-header) {
  margin-bottom: 0;
}

.empty-create {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.stat {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px;
}

.stat-icon {
  flex-shrink: 0;
}

.stat.alert .stat-icon {
  color: var(--danger);
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
  color: var(--danger);
}

.stat .label {
  color: var(--text-soft);
  font-size: 12px;
  margin-top: 4px;
  font-weight: 500;
}

.sections {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section h3 {
  margin: 0 0 12px;
  font-size: 15px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text);
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
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
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  color: var(--accent-hover);
  border-color: color-mix(in srgb, var(--accent) 22%, transparent);
}

.status-section {
  padding-bottom: 20px;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 16px;
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

/* 状态语义:待办=中性,进行中=警示,完成=成功(勿与优先级色混淆) */
.status-dot[data-status='待办'] { background: var(--sea-400); }
.status-dot[data-status='进行中'] { background: var(--warning); }
.status-dot[data-status='完成'] { background: var(--success); }

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
  background: linear-gradient(90deg, var(--warning), var(--sand-200));
}

.total {
  margin: 16px 0 0;
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

.overview-grid {
  align-items: stretch;
}

.overview-rail,
.overview-aside {
  display: grid;
  gap: 16px;
  align-content: start;
  padding: 18px;
}

.overview-main {
  display: grid;
  gap: 16px;
}

.completion {
  display: grid;
  gap: 4px;
}

.completion strong {
  color: var(--accent-strong);
  font-size: 40px;
  line-height: 1;
}

.completion span,
.rail-stat span,
.advice-item span {
  color: var(--text-soft);
  font-size: 12px;
  font-weight: 700;
}

.rail-track {
  margin: 0;
}

.rail-stats,
.advice-list {
  display: grid;
  gap: 10px;
}

.rail-stat,
.advice-item {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-xs);
  background: var(--surface-2);
}

.rail-stat strong {
  margin-left: auto;
  color: var(--text);
}

.aside-head {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.aside-head h3 {
  margin: 0 0 4px;
  font-size: 17px;
}

.advice-item {
  flex-direction: column;
  align-items: flex-start;
}

.advice-item strong {
  color: var(--text);
}

.advice-item.urgent {
  border-color: color-mix(in srgb, var(--danger) 30%, transparent);
  background: var(--danger-soft);
}

.section {
  padding: 16px;
}

.li {
  width: 100%;
  color: var(--text);
  text-align: left;
  box-shadow: none;
}

@media (max-width: 1180px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }
}
</style>
