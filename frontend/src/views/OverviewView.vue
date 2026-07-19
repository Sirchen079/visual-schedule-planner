<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { getByPriority, getByTag, getDaily, getRisk } from '../api/stats'
import { getTimeStats } from '../api/timer'
import { askAssistant } from '../utils/assistant'
import ArtIcon from '../components/ArtIcon.vue'
import BaseChart, { cssVar } from '../components/charts/BaseChart.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import PageHeader from '../components/ui/PageHeader.vue'
import { useThemeTick } from '../composables/useThemeTick'

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

// ---- 生产力分析：进入视图按需加载，任一接口失败只隐藏对应图表卡 ----
const themeTick = useThemeTick()
const daily30 = ref(null)
const daily84 = ref(null)
const tagStats = ref(null)
const priorityStats = ref(null)
// 风险预警：规则打分接口，失败静默隐藏整张卡片
const riskItems = ref(null)
// 时间投入统计：/stats/time，失败静默隐藏整张卡
const timeStats = ref(null)

// 「问助手分析」：让 AI 解读时间投入分布与预估偏差，并给下周时间分配建议
function reviewTime() {
  askAssistant(
    '分析我近 30 天的时间投入：各标签的时间分布是否合理？' +
      '预估 vs 实际的偏差说明了什么（哪些任务类型我总低估）？' +
      '请结合我的任务与目标，给出下周的时间分配建议。'
  )
}

onMounted(() => {
  getDaily(30).then((d) => { daily30.value = d.days || [] }).catch(() => {})
  getDaily(84).then((d) => { daily84.value = d.days || [] }).catch(() => {})
  getByTag().then((d) => { tagStats.value = d.tags || [] }).catch(() => {})
  getByPriority().then((d) => { priorityStats.value = d.priorities || [] }).catch(() => {})
  getRisk().then((d) => { riskItems.value = d.items || [] }).catch(() => {})
  getTimeStats(30).then((d) => { timeStats.value = d }).catch(() => {})
})

// 风险行点击：回到主任务列表找完整任务对象，沿用现有 open 通道打开编辑
function openRiskTask(item) {
  const t = props.tasks.find((x) => x.id === item.task_id)
  if (t) emit('open', t)
}

const PRI_DOT = {
  高: 'var(--pri-high)',
  中: 'var(--pri-mid)',
  低: 'var(--pri-low)',
}
function priDotColor(p) {
  return PRI_DOT[p] || 'var(--pri-mid)'
}

// 图表配色统一走主题变量（主题切换时 themeTick 触发 option 重建）
function chartColors() {
  return {
    text: cssVar('--text-soft', '#476a7d'),
    line: cssVar('--border', 'rgba(130, 185, 208, 0.55)'),
    split: cssVar('--surface-3', 'rgba(214, 236, 245, 0.82)'),
    accent: cssVar('--accent', '#3b98c6'),
    accentStrong: cssVar('--accent-strong', '#19698f'),
    sea: cssVar('--sea-300', '#9ed3e6'),
    success: cssVar('--success', '#4aaf7c'),
    warning: cssVar('--warning', '#c58a42'),
  }
}

const trendOption = computed(() => {
  themeTick.value
  if (!daily30.value?.length) return null
  const c = chartColors()
  return {
    grid: { left: 40, right: 16, top: 32, bottom: 28 },
    tooltip: { trigger: 'axis' },
    legend: { data: ['完成', '新增'], textStyle: { color: c.text }, top: 0 },
    xAxis: {
      type: 'category',
      data: daily30.value.map((d) => d.date.slice(5)),
      axisLabel: { color: c.text },
      axisLine: { lineStyle: { color: c.line } },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: c.text },
      splitLine: { lineStyle: { color: c.split } },
    },
    series: [
      {
        name: '完成',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: daily30.value.map((d) => d.completed),
        itemStyle: { color: c.success },
        lineStyle: { color: c.success, width: 2 },
        areaStyle: { color: c.success, opacity: 0.08 },
      },
      {
        name: '新增',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: daily30.value.map((d) => d.created),
        itemStyle: { color: c.accent },
        lineStyle: { color: c.accent, width: 2 },
        areaStyle: { color: c.accent, opacity: 0.08 },
      },
    ],
  }
})

const heatOption = computed(() => {
  themeTick.value
  if (!daily84.value?.length) return null
  const c = chartColors()
  const days = daily84.value
  const max = Math.max(4, ...days.map((d) => d.completed))
  return {
    tooltip: {
      formatter: (p) => `${p.data[0]}：完成 ${p.data[1]} 项`,
    },
    visualMap: {
      min: 0,
      max,
      calculable: false,
      orient: 'horizontal',
      right: 0,
      bottom: 0,
      itemWidth: 12,
      itemHeight: 80,
      textStyle: { color: c.text, fontSize: 11 },
      inRange: {
        color: [cssVar('--surface-3', '#d6ecf5'), c.sea, c.accent, c.accentStrong],
      },
    },
    calendar: {
      top: 28,
      left: 44,
      right: 12,
      bottom: 44,
      range: [days[0].date, days[days.length - 1].date],
      cellSize: ['auto', 14],
      splitLine: { show: false },
      itemStyle: {
        color: 'transparent',
        borderColor: cssVar('--surface-solid', '#ffffff'),
        borderWidth: 2,
      },
      dayLabel: { color: c.text, fontSize: 11, nameMap: ['日', '一', '二', '三', '四', '五', '六'] },
      monthLabel: { color: c.text, fontSize: 11, nameMap: 'cn' },
      yearLabel: { show: false },
    },
    series: [
      {
        type: 'heatmap',
        coordinateSystem: 'calendar',
        data: days.map((d) => [d.date, d.completed]),
      },
    ],
  }
})

const tagOption = computed(() => {
  themeTick.value
  if (!tagStats.value?.length) return null
  const c = chartColors()
  const tags = tagStats.value.slice(0, 8)
  return {
    grid: { left: 8, right: 24, top: 32, bottom: 8, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['已完成', '未完成'], textStyle: { color: c.text }, top: 0 },
    xAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: c.text },
      splitLine: { lineStyle: { color: c.split } },
    },
    yAxis: {
      type: 'category',
      inverse: true,
      data: tags.map((t) => t.name),
      axisLabel: { color: c.text },
      axisLine: { lineStyle: { color: c.line } },
    },
    series: [
      {
        name: '已完成',
        type: 'bar',
        stack: 'tag',
        barWidth: 14,
        data: tags.map((t) => ({
          value: t.completed,
          itemStyle: { color: t.color || c.accent },
        })),
      },
      {
        name: '未完成',
        type: 'bar',
        stack: 'tag',
        barWidth: 14,
        data: tags.map((t) => ({
          value: Math.max(0, t.total - t.completed),
          itemStyle: { color: t.color || c.accent, opacity: 0.28, borderRadius: [0, 4, 4, 0] },
        })),
      },
    ],
  }
})

const priorityOption = computed(() => {
  themeTick.value
  if (!priorityStats.value?.length) return null
  const c = chartColors()
  const statuses = [
    ['待办', c.sea],
    ['进行中', c.warning],
    ['完成', c.success],
  ]
  return {
    grid: { left: 40, right: 16, top: 32, bottom: 28 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { textStyle: { color: c.text }, top: 0 },
    xAxis: {
      type: 'category',
      data: priorityStats.value.map((p) => p.priority),
      axisLabel: { color: c.text },
      axisLine: { lineStyle: { color: c.line } },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: c.text },
      splitLine: { lineStyle: { color: c.split } },
    },
    series: statuses.map(([name, color]) => ({
      name,
      type: 'bar',
      stack: 'status',
      barWidth: 36,
      itemStyle: { color },
      data: priorityStats.value.map((p) => p.by_status?.[name] || 0),
    })),
  }
})

// ---- 时间投入：每日分钟柱状 + 标签环图 + 预估 vs 实际 ----
const timeTotalLabel = computed(() => {
  const m = timeStats.value?.total_minutes || 0
  const h = Math.floor(m / 60)
  const mm = Math.round(m % 60)
  return h > 0 ? `共 ${h} 小时 ${mm} 分钟` : `共 ${mm} 分钟`
})

function fmtMinutes(m) {
  if (m === null || m === undefined) return '—'
  if (m < 60) return `${Math.round(m)} 分钟`
  const h = Math.floor(m / 60)
  const mm = Math.round(m % 60)
  return mm ? `${h} 小时 ${mm} 分钟` : `${h} 小时`
}

// 偏差百分比：实际/预估；预估为 0 或缺失时无意义
function deviationPct(e) {
  if (!e.estimated_minutes) return null
  return Math.round((e.actual_minutes / e.estimated_minutes) * 100)
}

const timeDailyOption = computed(() => {
  themeTick.value
  const daily = timeStats.value?.daily
  if (!daily?.length) return null
  const c = chartColors()
  return {
    grid: { left: 40, right: 16, top: 20, bottom: 28 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (ps) => `${ps[0].name}：${ps[0].value} 分钟`,
    },
    xAxis: {
      type: 'category',
      data: daily.map((d) => d.date.slice(5)),
      axisLabel: { color: c.text },
      axisLine: { lineStyle: { color: c.line } },
    },
    yAxis: {
      type: 'value',
      minInterval: 10,
      axisLabel: { color: c.text },
      splitLine: { lineStyle: { color: c.split } },
    },
    series: [
      {
        name: '投入分钟',
        type: 'bar',
        barMaxWidth: 18,
        itemStyle: { color: c.accent, borderRadius: [4, 4, 0, 0] },
        data: daily.map((d) => d.minutes),
      },
    ],
  }
})

const timeTagOption = computed(() => {
  themeTick.value
  const byTag = timeStats.value?.by_tag
  if (!byTag?.length) return null
  const c = chartColors()
  return {
    tooltip: {
      formatter: (p) => `${p.name}：${p.value} 分钟（${p.percent}%）`,
    },
    legend: {
      bottom: 0,
      textStyle: { color: c.text, fontSize: 11 },
      itemWidth: 10,
      itemHeight: 10,
    },
    series: [
      {
        type: 'pie',
        radius: ['48%', '72%'],
        center: ['50%', '44%'],
        avoidLabelOverlap: true,
        itemStyle: {
          borderColor: cssVar('--surface-solid', '#ffffff'),
          borderWidth: 2,
          borderRadius: 4,
        },
        label: { show: false },
        data: byTag.map((t) => ({
          name: t.name,
          value: t.minutes,
          itemStyle: t.color ? { color: t.color } : undefined,
        })),
      },
    ],
  }
})

const hasTimeContent = computed(
  () =>
    (timeStats.value?.total_minutes || 0) > 0 &&
    (timeDailyOption.value || timeTagOption.value || timeStats.value?.estimates?.length)
)

const hasAnalytics = computed(
  () => trendOption.value || heatOption.value || tagOption.value || priorityOption.value
)
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
          <div class="section section-panel risk-section" v-if="riskItems?.length">
            <h3>
              <ArtIcon name="alert" tone="coral" :size="30" tile label="风险" />
              <span>风险预警</span>
              <span class="risk-note muted">规则评估</span>
            </h3>
            <div class="task-list">
              <button class="li risk-li" v-for="r in riskItems" :key="r.task_id" @click="openRiskTask(r)">
                <span class="pri-dot" :style="{ background: priDotColor(r.priority) }"></span>
                <span class="li-title">{{ r.title }}</span>
                <span class="muted risk-progress">进度 {{ r.progress }}%</span>
                <span class="risk-reasons">
                  <span class="reason-chip" v-for="reason in r.reasons" :key="reason">{{ reason }}</span>
                </span>
              </button>
            </div>
          </div>

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

    <section v-if="hasAnalytics" class="analytics section-panel">
      <h3 class="analytics-title">
        <ArtIcon name="timeline" tone="aqua" :size="30" tile label="分析" />
        <span>生产力分析</span>
      </h3>
      <div class="analytics-grid">
        <div v-if="trendOption" class="chart-card chart-card-wide">
          <h4>近 30 天完成 vs 新增</h4>
          <BaseChart :option="trendOption" height="260px" />
        </div>
        <div v-if="heatOption" class="chart-card chart-card-wide">
          <h4>近 12 周完成热力</h4>
          <BaseChart :option="heatOption" height="230px" />
        </div>
        <div v-if="tagOption" class="chart-card">
          <h4>标签分布（前 8）</h4>
          <BaseChart :option="tagOption" height="280px" />
        </div>
        <div v-if="priorityOption" class="chart-card">
          <h4>优先级 × 状态</h4>
          <BaseChart :option="priorityOption" height="280px" />
        </div>
      </div>
    </section>

    <section v-if="timeStats" class="analytics section-panel time-panel">
      <h3 class="analytics-title">
        <ArtIcon name="timeline" tone="mint" :size="30" tile label="时间投入" />
        <span>时间投入</span>
        <span class="time-total muted">{{ timeTotalLabel }} · 近 30 天</span>
        <button type="button" class="ghost time-ask-btn" @click="reviewTime">问助手分析</button>
      </h3>
      <template v-if="hasTimeContent">
        <div class="analytics-grid">
          <div v-if="timeDailyOption" class="chart-card chart-card-wide">
            <h4>每日投入（分钟）</h4>
            <BaseChart :option="timeDailyOption" height="240px" />
          </div>
          <div v-if="timeTagOption" class="chart-card">
            <h4>标签分布</h4>
            <BaseChart :option="timeTagOption" height="280px" />
          </div>
          <div v-if="timeStats.estimates?.length" class="chart-card">
            <h4>预估 vs 实际</h4>
            <table class="estimate-table">
              <thead>
                <tr>
                  <th>任务</th>
                  <th>预估</th>
                  <th>实际</th>
                  <th>偏差</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="e in timeStats.estimates" :key="e.task_id">
                  <td class="est-title" :title="e.title">{{ e.title }}</td>
                  <td>{{ fmtMinutes(e.estimated_minutes) }}</td>
                  <td>{{ fmtMinutes(e.actual_minutes) }}</td>
                  <td>
                    <span
                      v-if="deviationPct(e) !== null"
                      class="deviation"
                      :class="{ low: deviationPct(e) > 150 }"
                    >
                      {{ deviationPct(e) }}%
                      <em v-if="deviationPct(e) > 150">低估</em>
                    </span>
                    <span v-else class="muted">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
      <p v-else class="muted time-empty">还没有计时记录，从任务卡右键「开始专注」试试</p>
    </section>
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

/* 风险预警卡：头部右侧小字标注评估方式，reasons 用 coral 色 chip */
.risk-note {
  margin-left: auto;
  font-size: 12px;
  font-weight: 500;
}

.risk-li {
  flex-wrap: wrap;
  justify-content: flex-start;
}

.pri-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.risk-li .li-title {
  flex: 1 1 auto;
}

.risk-progress {
  font-size: 12px;
  white-space: nowrap;
}

.risk-reasons {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.reason-chip {
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 650;
  white-space: nowrap;
  color: var(--danger-strong);
  background: var(--danger-soft);
  border: 1px solid color-mix(in srgb, var(--danger) 24%, transparent);
  border-radius: var(--radius-pill);
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

/* 生产力分析：复用 section-panel 视觉，图表卡走 surface-2 卡片 */
.analytics {
  display: grid;
  gap: 16px;
  padding: 16px;
}

.analytics-title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text);
}

.analytics-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.chart-card {
  min-width: 0;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
}

.chart-card-wide {
  grid-column: 1 / -1;
}

.chart-card h4 {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-soft);
}

@media (max-width: 900px) {
  .analytics-grid {
    grid-template-columns: 1fr;
  }
}

/* 时间投入：合计小字 + 预估 vs 实际表格 */
.time-total {
  margin-left: auto;
  font-size: 12px;
  font-weight: 500;
}

.time-empty {
  margin: 0;
  font-size: 13px;
}

.estimate-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.estimate-table th {
  text-align: left;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-soft);
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

.estimate-table td {
  padding: 8px;
  border-bottom: 1px solid var(--border);
  color: var(--text);
  white-space: nowrap;
}

.estimate-table tr:last-child td {
  border-bottom: none;
}

.estimate-table .est-title {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.deviation {
  font-weight: 700;
  color: var(--text-soft);
}

.deviation.low {
  color: var(--danger);
}

.deviation em {
  font-style: normal;
  margin-left: 6px;
  padding: 1px 8px;
  font-size: 11px;
  font-weight: 650;
  color: var(--danger-strong);
  background: var(--danger-soft);
  border: 1px solid color-mix(in srgb, var(--danger) 24%, transparent);
  border-radius: var(--radius-pill);
}
</style>
