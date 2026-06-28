<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { createScheduleEntry, deleteScheduleEntry, getDaySchedule, getMonthSchedule, updateScheduleEntry } from '../api/schedule'
import ArtIcon from '../components/ArtIcon.vue'

const props = defineProps({
  tasks: { type: Array, required: true },
})

const emit = defineEmits(['open', 'create'])

const WEEK_LABELS = ['一', '二', '三', '四', '五', '六', '日']
const MONTH_LABELS = ['1 月', '2 月', '3 月', '4 月', '5 月', '6 月', '7 月', '8 月', '9 月', '10 月', '11 月', '12 月']
const PRIORITY_LABELS = { 高: '高优先', 中: '中优先', 低: '低优先' }
const STATUS_LABELS = { 待办: '待办', 进行中: '进行中', 完成: '完成' }
const EMPTY_COPY = {
  must_do: {
    title: '今天没有硬截止',
    text: '把注意力留给计划中的推进项，维持轻一点的节奏。',
  },
  planned: {
    title: '今天还没排入专注块',
    text: '可把下方未排期任务快速安放到今天，形成明确行动面板。',
  },
  in_progress_today: {
    title: '没有跨天推进任务',
    text: '如果有持续中的项目，给它补上起止日期会更清晰。',
  },
  upcoming_pressure: {
    title: '接下来七天压力平稳',
    text: '可以把余量留给复盘、整理和小步前进。',
  },
  unscheduled: {
    title: '没有悬空任务',
    text: '当前任务都已有时间信号，日程结构比较稳定。',
  },
}

const today = new Date()
const mode = ref('day')
const selectedDate = ref(toISODate(today))
const cursor = ref(startOfMonth(today))
const daySchedule = ref(emptyDaySchedule(selectedDate.value))
const monthSchedule = ref([])
const loadingDay = ref(false)
const loadingMonth = ref(false)
const mutating = ref(false)
const error = ref('')

let dayRequestId = 0
let monthRequestId = 0

const bucketMeta = {
  must_do: {
    icon: 'priority',
    tone: 'coral',
    title: '必须处理',
    rail: '把有时限的事情先稳稳收住。',
  },
  planned: {
    icon: 'calendar',
    tone: 'aqua',
    title: '今日安排',
    rail: '这是已经明确放进今天的专注块。',
  },
  in_progress_today: {
    icon: 'timeline',
    tone: 'mint',
    title: '持续推进',
    rail: '跨天项目适合保持轻量推进，不必一次压满。',
  },
  upcoming_pressure: {
    icon: 'bell',
    tone: 'sand',
    title: '接近期限',
    rail: '这些任务正在靠近，适合提前切出一小段准备时间。',
  },
  unscheduled: {
    icon: 'task',
    tone: 'pearl',
    title: '等待安放',
    rail: '先给它一个日子，再决定今天是否处理。',
  },
}

const actionSignals = computed(() => {
  const summary = daySchedule.value?.summary || {}
  return [
    {
      key: 'must_do',
      label: '到期 / 逾期',
      count: summary.must_do || 0,
      icon: 'priority',
      tone: 'coral',
    },
    {
      key: 'planned',
      label: '已安排',
      count: summary.planned || 0,
      icon: 'calendar',
      tone: 'aqua',
    },
    {
      key: 'in_progress_today',
      label: '进行中',
      count: summary.in_progress_today || 0,
      icon: 'timeline',
      tone: 'mint',
    },
    {
      key: 'upcoming_pressure',
      label: '七日压力',
      count: summary.upcoming_pressure || 0,
      icon: 'bell',
      tone: 'sand',
    },
  ]
})

const strongestBucket = computed(() => {
  const summary = daySchedule.value?.summary || {}
  if (summary.must_do) return 'must_do'
  if (summary.planned) return 'planned'
  if (summary.in_progress_today) return 'in_progress_today'
  if (summary.upcoming_pressure) return 'upcoming_pressure'
  return 'unscheduled'
})

const focusPhrase = computed(() => {
  const bucket = strongestBucket.value
  if (bucket === 'must_do') return '先把临近期限的事项安稳落地。'
  if (bucket === 'planned') return '今天已经有明确安排，按块推进就够了。'
  if (bucket === 'in_progress_today') return '保持持续推进，不需要把每段时间都填满。'
  if (bucket === 'upcoming_pressure') return '趁压力还轻，提前切出小步行动。'
  return '今天比较松，可以给未排期事项一个温和的起点。'
})

const selectedDateLabel = computed(() => formatFullDate(selectedDate.value))
const cursorLabel = computed(() => {
  const value = cursor.value
  return `${value.getFullYear()} 年 ${MONTH_LABELS[value.getMonth()]}`
})

const monthCells = computed(() => {
  const year = cursor.value.getFullYear()
  const month = cursor.value.getMonth()
  const first = new Date(year, month, 1)
  const offset = (first.getDay() + 6) % 7
  const start = new Date(year, month, 1 - offset)
  const dayMap = new Map(monthSchedule.value.map((item) => [item.date, item]))
  const cells = []
  for (let i = 0; i < 42; i += 1) {
    const value = new Date(start)
    value.setDate(start.getDate() + i)
    const iso = toISODate(value)
    cells.push({
      date: iso,
      day: value,
      inMonth: value.getMonth() === month,
      isToday: iso === toISODate(today),
      isSelected: iso === selectedDate.value,
      summary: dayMap.get(iso) || {
        date: iso,
        due_count: 0,
        planned_count: 0,
        in_progress_count: 0,
        overdue_count: 0,
        total_count: 0,
      },
    })
  }
  return cells
})

const selectedMonthCell = computed(
  () => monthCells.value.find((cell) => cell.date === selectedDate.value) || null
)

const dayBuckets = computed(() => [
  createBucketVm('must_do', true),
  createBucketVm('planned', true),
  createBucketVm('in_progress_today', false),
  createBucketVm('upcoming_pressure', false),
  createBucketVm('unscheduled', false),
])

const selectedDayPreviewBuckets = computed(() => dayBuckets.value.slice(0, 3))

const dayRail = computed(() => {
  const summary = daySchedule.value?.summary || {}
  return [
    { time: '08:30', label: '唤醒', accent: summary.must_do ? 'must_do' : 'planned' },
    { time: '10:30', label: '专注', accent: summary.planned ? 'planned' : 'in_progress_today' },
    { time: '14:00', label: '续航', accent: summary.in_progress_today ? 'in_progress_today' : 'upcoming_pressure' },
    { time: '17:30', label: '收束', accent: summary.upcoming_pressure ? 'upcoming_pressure' : 'unscheduled' },
  ]
})

function emptyDaySchedule(date) {
  return {
    date,
    summary: {
      total: 0,
      must_do: 0,
      planned: 0,
      in_progress_today: 0,
      upcoming_pressure: 0,
      unscheduled: 0,
    },
    buckets: {
      must_do: [],
      planned: [],
      in_progress_today: [],
      upcoming_pressure: [],
      unscheduled: [],
    },
  }
}

function startOfMonth(value) {
  return new Date(value.getFullYear(), value.getMonth(), 1)
}

function toISODate(value) {
  const year = value.getFullYear()
  const month = `${value.getMonth() + 1}`.padStart(2, '0')
  const day = `${value.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

function parseISODate(value) {
  const [year, month, day] = String(value).split('-').map(Number)
  return new Date(year, (month || 1) - 1, day || 1)
}

function formatFullDate(value) {
  const date = parseISODate(value)
  return date.toLocaleDateString('zh-CN', {
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  })
}

function formatShortDate(value) {
  if (!value) return '未设日期'
  return parseISODate(value).toLocaleDateString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
  })
}

function formatPriority(task) {
  return PRIORITY_LABELS[task.priority] || task.priority || '未标记'
}

function formatStatus(task) {
  return STATUS_LABELS[task.status] || task.status || '待办'
}

function taskTags(task) {
  return Array.isArray(task.tags) ? task.tags.slice(0, 3) : []
}

function bucketCount(key) {
  return daySchedule.value?.summary?.[key] || 0
}

function createBucketVm(key, prominent) {
  const items = daySchedule.value?.buckets?.[key] || []
  return {
    key,
    ...bucketMeta[key],
    items,
    prominent,
    empty: EMPTY_COPY[key],
  }
}

function monthIntensityClass(summary) {
  if (!summary?.total_count) return 'level-0'
  if (summary.total_count >= 5) return 'level-4'
  if (summary.total_count >= 4) return 'level-3'
  if (summary.total_count >= 2) return 'level-2'
  return 'level-1'
}

function monthSignals(summary) {
  return [
    { key: 'due', label: '到期', count: summary.due_count, tone: 'coral' },
    { key: 'planned', label: '安排', count: summary.planned_count, tone: 'aqua' },
    { key: 'progress', label: '推进', count: summary.in_progress_count, tone: 'mint' },
    { key: 'overdue', label: '压力', count: summary.overdue_count, tone: 'sand' },
  ].filter((item) => item.count)
}

async function loadDaySchedule(date) {
  const requestId = ++dayRequestId
  loadingDay.value = true
  error.value = ''
  try {
    const response = await getDaySchedule(date)
    if (requestId !== dayRequestId) return
    daySchedule.value = response
  } catch (err) {
    if (requestId !== dayRequestId) return
    daySchedule.value = emptyDaySchedule(date)
    error.value = err?.message || '日程加载失败'
  } finally {
    if (requestId === dayRequestId) loadingDay.value = false
  }
}

async function loadMonthSchedule(currentCursor = cursor.value) {
  const requestId = ++monthRequestId
  loadingMonth.value = true
  error.value = ''
  try {
    const response = await getMonthSchedule({
      year: currentCursor.getFullYear(),
      month: currentCursor.getMonth() + 1,
    })
    if (requestId !== monthRequestId) return
    monthSchedule.value = response.days || []
  } catch (err) {
    if (requestId !== monthRequestId) return
    monthSchedule.value = []
    error.value = err?.message || '月度日程加载失败'
  } finally {
    if (requestId === monthRequestId) loadingMonth.value = false
  }
}

async function refreshVisibleSchedule() {
  await Promise.all([loadDaySchedule(selectedDate.value), loadMonthSchedule(cursor.value)])
}

function syncCursorToSelectedDate() {
  const selected = parseISODate(selectedDate.value)
  const monthStart = startOfMonth(selected)
  if (monthStart.getTime() !== cursor.value.getTime()) {
    cursor.value = monthStart
  }
}

function prevPeriod() {
  if (mode.value === 'month') {
    cursor.value = new Date(cursor.value.getFullYear(), cursor.value.getMonth() - 1, 1)
    return
  }
  const value = parseISODate(selectedDate.value)
  value.setDate(value.getDate() - 1)
  selectedDate.value = toISODate(value)
}

function nextPeriod() {
  if (mode.value === 'month') {
    cursor.value = new Date(cursor.value.getFullYear(), cursor.value.getMonth() + 1, 1)
    return
  }
  const value = parseISODate(selectedDate.value)
  value.setDate(value.getDate() + 1)
  selectedDate.value = toISODate(value)
}

function jumpToToday() {
  selectedDate.value = toISODate(today)
  cursor.value = startOfMonth(today)
}

function selectDate(date) {
  selectedDate.value = date
}

function openAssistantPrompt(kind) {
  const prompts = {
    today: `请帮我安排 ${selectedDate.value} 的任务：优先处理到期和高优先事项，并把大任务拆成可执行步骤。`,
    pressure: `请检查 ${selectedDate.value} 之后七天的任务压力，给我一个更平稳的推进建议。`,
    unscheduled: `请把未排期任务按轻重缓急安放到接下来几天，先给出保守安排。`,
  }
  window.dispatchEvent(
    new CustomEvent('assistant:prompt', {
      detail: {
        text: prompts[kind] || prompts.today,
      },
    })
  )
}

async function quickAssign(taskId) {
  mutating.value = true
  error.value = ''
  try {
    await createScheduleEntry({
      task_id: taskId,
      date: selectedDate.value,
      source: 'manual',
      note: 'Quick assign',
    })
    await refreshVisibleSchedule()
  } catch (err) {
    error.value = err?.message || '排期失败'
  } finally {
    mutating.value = false
  }
}

async function moveEntryToNextDay(item) {
  if (!item?.entry?.id) return
  const date = parseISODate(selectedDate.value)
  date.setDate(date.getDate() + 1)
  mutating.value = true
  error.value = ''
  try {
    await updateScheduleEntry(item.entry.id, {
      date: toISODate(date),
      note: item.entry.note || '顺延一天',
    })
    await refreshVisibleSchedule()
  } catch (err) {
    error.value = err?.message || '移动排期失败'
  } finally {
    mutating.value = false
  }
}

async function removeEntry(item) {
  if (!item?.entry?.id) return
  mutating.value = true
  error.value = ''
  try {
    await deleteScheduleEntry(item.entry.id)
    await refreshVisibleSchedule()
  } catch (err) {
    error.value = err?.message || '移除排期失败'
  } finally {
    mutating.value = false
  }
}

watch(selectedDate, (value) => {
  syncCursorToSelectedDate()
  loadDaySchedule(value)
})

watch(cursor, (value) => {
  loadMonthSchedule(value)
})

watch(mode, (value) => {
  if (value === 'month') loadMonthSchedule(cursor.value)
})

onMounted(async () => {
  await refreshVisibleSchedule()
})
</script>

<template>
  <section class="calendar-action-center">
    <header class="action-header glass">
      <div class="header-copy">
        <div class="page-title">
          <ArtIcon name="calendar" tone="aqua" :size="36" tile label="日程行动中心" />
          <div>
            <h2>日程行动中心</h2>
            <p>{{ selectedDateLabel }}</p>
          </div>
        </div>
        <p class="focus-phrase">{{ focusPhrase }}</p>
      </div>

      <div class="header-controls">
        <div class="segmented" role="tablist" aria-label="日程视图模式">
          <button
            class="ghost mode-button"
            data-view-mode="day"
            :aria-pressed="mode === 'day'"
            :class="{ active: mode === 'day' }"
            @click="mode = 'day'"
          >
            <ArtIcon name="task" tone="aqua" :size="24" />
            <span>Day Action</span>
          </button>
          <button
            class="ghost mode-button"
            data-view-mode="month"
            :aria-pressed="mode === 'month'"
            :class="{ active: mode === 'month' }"
            @click="mode = 'month'"
          >
            <ArtIcon name="timeline" tone="mint" :size="24" />
            <span>Month Plan</span>
          </button>
        </div>

        <div class="date-nav">
          <button class="ghost icon-button" title="上一段" @click="prevPeriod">
            <ArtIcon name="chevron-left" tone="pearl" :size="22" label="上一段" />
          </button>
          <div class="nav-label">
            <strong>{{ mode === 'month' ? cursorLabel : selectedDateLabel }}</strong>
            <span>{{ mode === 'month' ? '月度信号总览' : '今日行动焦点' }}</span>
          </div>
          <button class="ghost icon-button" title="下一段" @click="nextPeriod">
            <ArtIcon name="chevron-right" tone="pearl" :size="22" label="下一段" />
          </button>
          <button class="ghost today-button" @click="jumpToToday">今天</button>
          <button class="create-btn" @click="emit('create')">
            <ArtIcon name="plus" tone="on-accent" :size="20" />
            <span>新建任务</span>
          </button>
        </div>
      </div>

      <div class="signal-grid">
        <article v-for="signal in actionSignals" :key="signal.key" class="signal-card">
          <ArtIcon :name="signal.icon" :tone="signal.tone" :size="30" tile :label="signal.label" />
          <div>
            <strong>{{ signal.count }}</strong>
            <span>{{ signal.label }}</span>
          </div>
        </article>
      </div>
    </header>

    <p v-if="error" class="error-line" role="alert">{{ error }}</p>

    <div v-if="mode === 'day'" class="day-layout">
      <aside class="day-side">
        <section class="day-rail glass">
          <div class="rail-head">
            <ArtIcon :name="bucketMeta[strongestBucket].icon" :tone="bucketMeta[strongestBucket].tone" :size="50" tile />
            <div>
              <h3>{{ bucketMeta[strongestBucket].title }}</h3>
              <p>{{ bucketMeta[strongestBucket].rail }}</p>
            </div>
          </div>

          <div class="rail-line">
            <div v-for="slot in dayRail" :key="slot.time" class="rail-slot" :data-accent="slot.accent">
              <span class="slot-time">{{ slot.time }}</span>
              <span class="slot-dot"></span>
              <span class="slot-label">{{ slot.label }}</span>
            </div>
          </div>
        </section>

        <section class="assistant-panel glass">
          <div class="assistant-panel-head">
            <ArtIcon name="assistant" tone="aqua" :size="48" tile label="助手排程" />
            <div>
              <h3>交给助手整理</h3>
              <p>把今天、压力窗口或未排期事项直接移交给助手继续拆分。</p>
            </div>
          </div>
          <div class="assistant-actions">
            <button class="ghost assistant-plan-button" title="安排今天" @click="openAssistantPrompt('today')">
              <ArtIcon name="calendar" tone="aqua" :size="24" />
              <span>安排今天</span>
            </button>
            <button class="ghost assistant-plan-button" title="平衡压力" @click="openAssistantPrompt('pressure')">
              <ArtIcon name="bell" tone="sand" :size="24" />
              <span>平衡压力</span>
            </button>
            <button class="ghost assistant-plan-button" title="安放未排期" @click="openAssistantPrompt('unscheduled')">
              <ArtIcon name="task" tone="mint" :size="24" />
              <span>安放未排期</span>
            </button>
          </div>
        </section>
      </aside>

      <main class="day-main">
        <section
          v-for="bucket in dayBuckets"
          :key="bucket.key"
          class="day-bucket glass"
          :class="{ prominent: bucket.prominent }"
          :data-bucket="bucket.key"
        >
          <header class="bucket-head">
            <div class="bucket-title">
              <ArtIcon :name="bucket.icon" :tone="bucket.tone" :size="30" tile :label="bucket.title" />
              <div>
                <h3>{{ bucket.title }}</h3>
                <p>{{ bucket.rail }}</p>
              </div>
            </div>
            <span class="bucket-count">{{ bucketCount(bucket.key) }}</span>
          </header>

          <div v-if="bucket.items.length" class="task-stack">
            <article
              v-for="item in bucket.items"
              :key="`${bucket.key}-${item.task.id}-${item.entry?.id || 'task'}`"
              class="task-card"
            >
              <button class="task-body" type="button" @click="emit('open', item.task)">
                <div class="task-topline">
                  <strong>{{ item.task.title }}</strong>
                  <span class="task-progress">{{ item.task.progress || 0 }}%</span>
                </div>
                <div class="task-meta">
                  <span class="task-pill">{{ formatPriority(item.task) }}</span>
                  <span class="task-pill">{{ formatStatus(item.task) }}</span>
                  <span v-if="item.task.due_date" class="task-pill">截止 {{ formatShortDate(item.task.due_date.slice(0, 10)) }}</span>
                  <span v-if="item.entry?.note" class="task-pill note-pill">{{ item.entry.note }}</span>
                </div>
                <div v-if="taskTags(item.task).length" class="tag-row">
                  <span
                    v-for="tag in taskTags(item.task)"
                    :key="tag.id || tag.name"
                    class="tag-chip"
                    :style="{ '--tag-color': tag.color || 'var(--accent)' }"
                  >
                    {{ tag.name }}
                  </span>
                </div>
              </button>

              <div v-if="bucket.key === 'planned' && item.entry" class="task-actions">
                <button
                  class="ghost icon-button small"
                  :disabled="mutating"
                  title="顺延一天"
                  @click="moveEntryToNextDay(item)"
                >
                  <ArtIcon name="chevron-right" tone="aqua" :size="22" label="顺延一天" />
                </button>
                <button
                  class="ghost icon-button small"
                  :disabled="mutating"
                  title="移除排期"
                  @click="removeEntry(item)"
                >
                  <ArtIcon name="trash" tone="coral" :size="22" label="移除排期" />
                </button>
              </div>

              <div v-else-if="bucket.key === 'unscheduled'" class="task-actions">
                <button
                  class="ghost icon-button small"
                  :disabled="mutating"
                  title="安排到选中日期"
                  @click="quickAssign(item.task.id)"
                >
                  <ArtIcon name="plus" tone="mint" :size="22" label="安排到选中日期" />
                </button>
              </div>
            </article>
          </div>

          <div v-else class="empty-bucket">
            <ArtIcon :name="bucket.icon" :tone="bucket.tone" :size="28" />
            <div>
              <strong>{{ bucket.empty.title }}</strong>
              <p>{{ bucket.empty.text }}</p>
            </div>
          </div>
        </section>
      </main>
    </div>

    <div v-else class="month-layout">
      <section class="month-plan-grid glass">
        <div class="month-weekdays">
          <span v-for="label in WEEK_LABELS" :key="label">{{ label }}</span>
        </div>

        <div class="month-grid">
          <button
            v-for="cell in monthCells"
            :key="cell.date"
            class="month-cell"
            :class="[
              monthIntensityClass(cell.summary),
              {
                muted: !cell.inMonth,
                today: cell.isToday,
                selected: cell.isSelected,
              },
            ]"
            @click="selectDate(cell.date)"
          >
            <div class="cell-top">
              <span class="cell-date">{{ cell.day.getDate() }}</span>
              <span v-if="cell.summary.total_count" class="cell-total">{{ cell.summary.total_count }}</span>
            </div>
            <div class="cell-signals">
              <span
                v-for="signal in monthSignals(cell.summary)"
                :key="`${cell.date}-${signal.key}`"
                class="signal-chip"
                :data-tone="signal.tone"
              >
                {{ signal.label }} {{ signal.count }}
              </span>
            </div>
          </button>
        </div>
      </section>

      <aside class="selected-day-preview glass">
        <div class="preview-head">
          <ArtIcon name="calendar" tone="aqua" :size="40" tile />
          <div>
            <h3>{{ selectedDateLabel }}</h3>
            <p>选中日期的行动摘要会同步显示在这里。</p>
          </div>
        </div>

        <div class="preview-summary">
          <article v-for="signal in actionSignals" :key="signal.key" class="preview-signal">
            <ArtIcon :name="signal.icon" :tone="signal.tone" :size="22" />
            <div>
              <strong>{{ signal.count }}</strong>
              <span>{{ signal.label }}</span>
            </div>
          </article>
        </div>

        <div class="preview-buckets">
          <section v-for="bucket in selectedDayPreviewBuckets" :key="bucket.key" class="preview-bucket">
            <div class="preview-bucket-head">
              <ArtIcon :name="bucket.icon" :tone="bucket.tone" :size="22" />
              <strong>{{ bucket.title }}</strong>
              <span>{{ bucket.items.length }}</span>
            </div>
            <div v-if="bucket.items.length" class="preview-task-list">
              <button
                v-for="item in bucket.items.slice(0, 3)"
                :key="`${bucket.key}-${item.task.id}-${item.entry?.id || 'task'}-preview`"
                class="preview-task"
                type="button"
                @click="emit('open', item.task)"
              >
                <span>{{ item.task.title }}</span>
                <small>{{ formatPriority(item.task) }}</small>
              </button>
            </div>
            <div v-else class="preview-empty">{{ bucket.empty.title }}</div>
          </section>
        </div>

        <button class="ghost assistant-plan-button preview-button" @click="openAssistantPrompt('today')">
          <ArtIcon name="assistant" tone="aqua" :size="24" />
          <span>让助手接手这一天</span>
        </button>
      </aside>
    </div>

    <div v-if="loadingDay || loadingMonth" class="loading-overlay" aria-live="polite">
      <span class="spinner-ring"></span>
      <span>{{ loadingDay ? '正在更新日程…' : '正在同步月度信号…' }}</span>
    </div>
  </section>
</template>

<style scoped>
.calendar-action-center {
  position: relative;
  display: grid;
  gap: 16px;
  max-width: 1320px;
  margin: 0 auto;
  padding-bottom: 8px;
}

.action-header,
.day-rail,
.assistant-panel,
.day-bucket,
.month-plan-grid,
.selected-day-preview {
  position: relative;
  overflow: hidden;
  border-radius: 8px;
}

.action-header::before,
.day-rail::before,
.assistant-panel::before,
.day-bucket::before,
.month-plan-grid::before,
.selected-day-preview::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at top right, rgba(255, 255, 255, 0.26), transparent 32%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.16), transparent 48%);
  pointer-events: none;
}

.action-header {
  display: grid;
  gap: 14px;
  padding: 18px;
}

.header-copy,
.header-controls {
  display: grid;
  gap: 12px;
}

.page-title {
  align-items: flex-start;
}

.page-title h2 {
  margin: 0;
  font-size: 28px;
  line-height: 1.1;
}

.page-title p,
.focus-phrase,
.nav-label span,
.bucket-title p,
.rail-head p,
.assistant-panel-head p,
.preview-head p,
.empty-bucket p {
  margin: 0;
  color: var(--text-soft);
}

.focus-phrase {
  font-size: 14px;
  line-height: 1.6;
}

.header-controls {
  align-items: end;
  grid-template-columns: minmax(0, 1fr);
}

.segmented {
  display: inline-grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px;
  padding: 4px;
  width: fit-content;
  max-width: 100%;
  background: rgba(255, 255, 255, 0.55);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow-inset);
}

.mode-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 42px;
  padding: 8px 14px;
  border-radius: 8px;
}

.mode-button.active {
  background: linear-gradient(135deg, var(--accent), var(--sea-400));
  color: #fff;
  border-color: transparent;
  box-shadow: 0 10px 24px var(--accent-glow);
}

.date-nav {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.nav-label {
  display: grid;
  gap: 2px;
  min-width: 0;
  padding: 0 4px;
}

.nav-label strong {
  font-size: 15px;
}

.icon-button {
  width: 40px;
  height: 40px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
}

.icon-button.small {
  width: 34px;
  height: 34px;
}

.today-button {
  min-height: 40px;
  padding: 8px 16px;
}

.create-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 42px;
  padding: 10px 16px;
}

.signal-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.signal-card {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 12px;
  border: 1px solid rgba(151, 200, 218, 0.42);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.54);
}

.signal-card strong,
.preview-signal strong {
  display: block;
  font-size: 20px;
  line-height: 1;
}

.signal-card span,
.preview-signal span {
  color: var(--text-soft);
  font-size: 12px;
}

.error-line {
  margin: 0;
  padding: 12px 14px;
  border: 1px solid rgba(217, 93, 106, 0.28);
  border-radius: 8px;
  background: rgba(253, 236, 239, 0.88);
  color: var(--danger);
  font-weight: 700;
}

.day-layout {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.day-side,
.day-main,
.month-layout,
.preview-buckets {
  display: grid;
  gap: 16px;
}

.day-rail,
.assistant-panel,
.day-bucket,
.month-plan-grid,
.selected-day-preview {
  padding: 16px;
}

.rail-head,
.assistant-panel-head,
.preview-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  min-width: 0;
}

.rail-head h3,
.assistant-panel-head h3,
.bucket-title h3,
.preview-head h3 {
  margin: 0 0 4px;
  font-size: 18px;
}

.rail-line {
  position: relative;
  display: grid;
  gap: 14px;
  margin-top: 16px;
  padding-left: 8px;
}

.rail-line::before {
  content: '';
  position: absolute;
  left: 50px;
  top: 8px;
  bottom: 8px;
  width: 1px;
  background: linear-gradient(180deg, rgba(59, 152, 198, 0.3), rgba(74, 175, 124, 0.18));
}

.rail-slot {
  position: relative;
  display: grid;
  grid-template-columns: 42px 16px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
}

.slot-time,
.slot-label {
  font-size: 12px;
  font-weight: 700;
}

.slot-time {
  color: var(--text-soft);
}

.slot-dot {
  width: 12px;
  height: 12px;
  border-radius: 999px;
  background: var(--accent);
  box-shadow: 0 0 0 6px rgba(59, 152, 198, 0.12);
}

.rail-slot[data-accent="must_do"] .slot-dot {
  background: var(--danger);
  box-shadow: 0 0 0 6px rgba(217, 93, 106, 0.14);
}

.rail-slot[data-accent="planned"] .slot-dot {
  background: var(--accent);
}

.rail-slot[data-accent="in_progress_today"] .slot-dot {
  background: var(--success);
  box-shadow: 0 0 0 6px rgba(74, 175, 124, 0.14);
}

.rail-slot[data-accent="upcoming_pressure"] .slot-dot {
  background: var(--warning);
  box-shadow: 0 0 0 6px rgba(197, 138, 66, 0.14);
}

.assistant-actions {
  display: grid;
  gap: 8px;
  margin-top: 14px;
}

.assistant-plan-button {
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
  min-height: 42px;
  padding: 10px 12px;
}

.day-main {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: start;
}

.day-bucket {
  display: grid;
  gap: 12px;
  min-height: 220px;
}

.day-bucket.prominent {
  min-height: 250px;
}

.day-bucket[data-bucket="must_do"],
.day-bucket[data-bucket="planned"] {
  grid-column: span 1;
}

.day-bucket[data-bucket="in_progress_today"],
.day-bucket[data-bucket="upcoming_pressure"],
.day-bucket[data-bucket="unscheduled"] {
  min-height: 180px;
}

.bucket-head,
.bucket-title,
.task-body,
.task-meta,
.task-actions,
.preview-bucket-head,
.preview-task,
.preview-summary {
  display: flex;
}

.bucket-head {
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.bucket-title {
  gap: 10px;
  min-width: 0;
}

.bucket-count {
  min-width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  color: var(--text-soft);
  font-size: 12px;
  font-weight: 800;
}

.task-stack {
  display: grid;
  gap: 10px;
}

.task-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  padding: 10px;
  border: 1px solid rgba(151, 200, 218, 0.42);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.7);
}

.task-body {
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  min-width: 0;
  padding: 0;
  background: transparent;
  border: 0;
  box-shadow: none;
  color: inherit;
  text-align: left;
}

.task-body:hover {
  background: transparent;
  box-shadow: none;
}

.task-topline {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: baseline;
}

.task-topline strong,
.preview-task span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-progress {
  flex-shrink: 0;
  color: var(--text-soft);
  font-size: 12px;
  font-weight: 700;
}

.task-meta,
.tag-row {
  flex-wrap: wrap;
  gap: 6px;
}

.task-pill,
.tag-chip,
.signal-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  max-width: 100%;
  min-height: 24px;
  padding: 0 9px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.task-pill {
  border: 1px solid var(--border);
  background: var(--surface-2);
  color: var(--text-soft);
}

.task-pill.note-pill {
  color: var(--accent-strong);
}

.tag-chip {
  border: 1px solid color-mix(in srgb, var(--tag-color) 26%, var(--border));
  background: color-mix(in srgb, var(--tag-color) 12%, white);
  color: color-mix(in srgb, var(--tag-color) 74%, #14303f);
}

.task-actions {
  align-items: flex-start;
  gap: 6px;
}

.empty-bucket {
  display: grid;
  gap: 8px;
  align-content: center;
  min-height: 110px;
  padding: 10px;
  border: 1px dashed rgba(151, 200, 218, 0.55);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.34);
}

.empty-bucket strong,
.preview-empty {
  color: var(--text);
  font-weight: 800;
}

.month-layout {
  grid-template-columns: minmax(0, 1.6fr) 340px;
  align-items: start;
}

.month-weekdays {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
  color: var(--text-soft);
  font-size: 12px;
  font-weight: 800;
  text-align: center;
}

.month-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 8px;
}

.month-cell {
  display: grid;
  align-content: start;
  gap: 8px;
  min-height: 108px;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid rgba(151, 200, 218, 0.42);
  background: rgba(255, 255, 255, 0.62);
  color: var(--text);
  text-align: left;
}

.month-cell.level-0 {
  background: rgba(255, 255, 255, 0.46);
}

.month-cell.level-1 {
  background: linear-gradient(180deg, rgba(229, 244, 249, 0.86), rgba(255, 255, 255, 0.68));
}

.month-cell.level-2 {
  background: linear-gradient(180deg, rgba(210, 239, 249, 0.92), rgba(255, 255, 255, 0.72));
}

.month-cell.level-3 {
  background: linear-gradient(180deg, rgba(200, 232, 243, 0.96), rgba(243, 251, 255, 0.82));
}

.month-cell.level-4 {
  background: linear-gradient(180deg, rgba(189, 228, 241, 0.98), rgba(236, 248, 252, 0.88));
}

.month-cell.muted {
  opacity: 0.46;
}

.month-cell.today {
  border-color: var(--accent);
  box-shadow: inset 0 0 0 1px rgba(59, 152, 198, 0.3);
}

.month-cell.selected {
  border-color: var(--accent-strong);
  box-shadow: inset 0 0 0 1px rgba(25, 105, 143, 0.34), var(--shadow-sm);
}

.cell-top {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}

.cell-date,
.cell-total {
  font-size: 12px;
  font-weight: 800;
}

.cell-total {
  color: var(--accent-strong);
}

.cell-signals {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.signal-chip {
  justify-content: flex-start;
  padding-inline: 8px;
  min-height: 22px;
  background: rgba(255, 255, 255, 0.74);
  border: 1px solid var(--border);
  color: var(--text-soft);
}

.signal-chip[data-tone="coral"] {
  border-color: rgba(217, 93, 106, 0.28);
  color: var(--danger);
}

.signal-chip[data-tone="aqua"] {
  border-color: rgba(59, 152, 198, 0.28);
  color: var(--accent-strong);
}

.signal-chip[data-tone="mint"] {
  border-color: rgba(74, 175, 124, 0.28);
  color: var(--success);
}

.signal-chip[data-tone="sand"] {
  border-color: rgba(197, 138, 66, 0.28);
  color: var(--warning);
}

.selected-day-preview {
  display: grid;
  gap: 14px;
}

.preview-summary {
  flex-wrap: wrap;
  gap: 8px;
}

.preview-signal {
  align-items: center;
  gap: 8px;
  min-width: calc(50% - 4px);
  padding: 10px;
  border: 1px solid rgba(151, 200, 218, 0.42);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.58);
}

.preview-bucket {
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px solid rgba(151, 200, 218, 0.34);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.48);
}

.preview-bucket-head {
  align-items: center;
  gap: 8px;
}

.preview-bucket-head span {
  margin-left: auto;
  color: var(--text-soft);
  font-size: 12px;
  font-weight: 800;
}

.preview-task-list {
  display: grid;
  gap: 6px;
}

.preview-task {
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
  padding: 8px 10px;
  border: 1px solid rgba(151, 200, 218, 0.34);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.72);
  color: var(--text);
  text-align: left;
}

.preview-task small {
  flex-shrink: 0;
  color: var(--text-soft);
}

.preview-empty {
  color: var(--text-soft);
  font-size: 12px;
}

.preview-button {
  justify-content: center;
}

.loading-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  background: rgba(247, 252, 255, 0.52);
  backdrop-filter: blur(3px);
  border-radius: 8px;
  color: var(--text-soft);
  font-weight: 700;
}

.spinner-ring {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(59, 152, 198, 0.2);
  border-top-color: var(--accent);
  border-radius: 999px;
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 1100px) {
  .day-layout,
  .month-layout {
    grid-template-columns: 1fr;
  }

  .day-main {
    grid-template-columns: 1fr;
  }

  .signal-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .action-header,
  .day-rail,
  .assistant-panel,
  .day-bucket,
  .month-plan-grid,
  .selected-day-preview {
    padding: 14px;
  }

  .page-title h2 {
    font-size: 24px;
  }

  .signal-grid {
    grid-template-columns: 1fr 1fr;
  }

  .month-grid {
    gap: 6px;
  }

  .month-cell {
    min-height: 92px;
    padding: 8px;
  }
}

@media (max-width: 390px) {
  .calendar-action-center {
    gap: 12px;
  }

  .segmented,
  .date-nav,
  .signal-grid,
  .preview-summary {
    width: 100%;
  }

  .mode-button,
  .assistant-plan-button,
  .today-button,
  .create-btn {
    min-width: 0;
  }

  .mode-button span,
  .assistant-plan-button span,
  .create-btn span {
    overflow-wrap: anywhere;
  }

  .signal-grid,
  .preview-summary {
    grid-template-columns: 1fr;
  }

  .signal-card,
  .preview-signal {
    min-width: 0;
  }

  .task-card {
    grid-template-columns: 1fr;
  }

  .task-actions {
    justify-content: flex-end;
  }
}
</style>
