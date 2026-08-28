<script setup>
import { computed, inject, onMounted, ref, watch } from 'vue'
import { createScheduleEntry, deleteScheduleEntry, getDaySchedule, getMonthSchedule, updateScheduleEntry } from '../api/schedule'
import { updateTask } from '../api/tasks'
import ArtIcon from '../components/ArtIcon.vue'
import AppSpinner from '../components/ui/AppSpinner.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import FirstRunTip from '../components/ui/FirstRunTip.vue'
import PageHeader from '../components/ui/PageHeader.vue'
import SegmentedControl from '../components/ui/SegmentedControl.vue'

const props = defineProps({
  tasks: { type: Array, required: true },
})

const emit = defineEmits(['open', 'create', 'changed'])

const toast = inject('toast', null)

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
// 月格子的排期 entry 明细（月接口只返回计数，这里按需补拉，用于拖拽改期）
const monthEntries = ref(new Map())
const loadingDay = ref(false)
const loadingMonth = ref(false)
const mutating = ref(false)
const error = ref('')

let dayRequestId = 0
let monthRequestId = 0

const modeOptions = [
  { value: 'day', label: '日行动', icon: 'task' },
  { value: 'month', label: '月计划', icon: 'timeline' },
]

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

const dayBuckets = computed(() => [
  createBucketVm('must_do', true),
  createBucketVm('planned', true),
  createBucketVm('in_progress_today', false),
  createBucketVm('upcoming_pressure', false),
  createBucketVm('unscheduled', false),
])

// 「等待安放」与选中日期无关，月视图预览不再重复展示，只在日模式保留一个。
const selectedDayPreviewBuckets = computed(() => dayBuckets.value.filter((bucket) => bucket.key !== 'unscheduled'))

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

// 顺序：最重要的信号在最左（压力 > 到期 > 推进 > 安排），被裁剪时先丢不重要的
function monthSignals(summary) {
  return [
    { key: 'overdue', label: '压力', count: summary.overdue_count, tone: 'sand' },
    { key: 'due', label: '到期', count: summary.due_count, tone: 'coral' },
    { key: 'progress', label: '推进', count: summary.in_progress_count, tone: 'mint' },
    { key: 'planned', label: '安排', count: summary.planned_count, tone: 'aqua' },
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
    await loadMonthEntries(monthSchedule.value, requestId)
  } catch (err) {
    if (requestId !== monthRequestId) return
    monthSchedule.value = []
    monthEntries.value = new Map()
    error.value = err?.message || '月度日程加载失败'
  } finally {
    if (requestId === monthRequestId) loadingMonth.value = false
  }
}

// 月接口只给每日计数；只对「有安排」的日子补拉日视图，收集 entry 明细供月格子拖拽改期
async function loadMonthEntries(days, requestId) {
  const dates = days.filter((d) => d.planned_count > 0).map((d) => d.date)
  if (!dates.length) {
    monthEntries.value = new Map()
    return
  }
  const results = await Promise.all(
    dates.map(async (date) => {
      try {
        const day = await getDaySchedule(date)
        const items = (day?.buckets?.planned || []).filter((item) => item.entry?.id)
        return [date, items]
      } catch {
        return [date, []]
      }
    })
  )
  if (requestId !== monthRequestId) return
  monthEntries.value = new Map(results)
}

// 月格子里的可拖拽条目：排期 entry（改 entry.date）+ 仅截止日期的任务（改 task.due_date），
// 同一任务同一天只出现一次（entry 优先）
const monthChipMap = computed(() => {
  const map = new Map()
  const seen = new Set()
  const push = (date, chip) => {
    const dedupeKey = `${date}|${chip.task.id}`
    if (seen.has(dedupeKey)) return
    seen.add(dedupeKey)
    if (!map.has(date)) map.set(date, [])
    map.get(date).push(chip)
  }
  for (const [date, items] of monthEntries.value) {
    for (const item of items) {
      push(date, {
        key: `entry-${item.entry.id}`,
        type: 'entry',
        id: item.entry.id,
        date,
        task: item.task,
        entry: item.entry,
      })
    }
  }
  for (const task of props.tasks) {
    if (task.status === '完成' || !task.due_date) continue
    const date = task.due_date.slice(0, 10)
    push(date, { key: `task-${task.id}`, type: 'task', id: task.id, date, task })
  }
  return map
})

// 月格子拖拽改期：dragstart 记录 {type, id, date}，目标格子 dragover 高亮，drop 执行
const dragPayload = ref(null)
const dropTargetDate = ref('')

// 月视图 chip 的悬浮提示：排程条目有时段时拼上「HH:MM-HH:MM」
function chipTitle(chip) {
  const span =
    chip.entry?.start_time
      ? ` ${chip.entry.start_time}${chip.entry?.end_time ? `-${chip.entry.end_time}` : ''}`
      : ''
  return `${chip.task.title}${span}（可拖拽改期）`
}

function onChipDragStart(event, chip) {
  dragPayload.value = { type: chip.type, id: chip.id, date: chip.date }
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', chip.task.title)
  event.stopPropagation()
}

function onChipDragEnd() {
  dragPayload.value = null
  dropTargetDate.value = ''
}

function onCellDragOver(event, date) {
  if (!dragPayload.value) return
  event.preventDefault()
  event.dataTransfer.dropEffect = 'move'
  dropTargetDate.value = date
}

function onGridDragLeave(event) {
  if (!event.currentTarget.contains(event.relatedTarget)) dropTargetDate.value = ''
}

async function onCellDrop(event, date) {
  event.preventDefault()
  const payload = dragPayload.value
  onChipDragEnd()
  if (!payload || payload.date === date) return
  mutating.value = true
  error.value = ''
  try {
    if (payload.type === 'entry') {
      await updateScheduleEntry(payload.id, { date })
    } else {
      await updateTask(payload.id, { due_date: `${date}T23:59:59` })
    }
    await refreshVisibleSchedule()
    emit('changed')
    toast?.success(payload.type === 'entry' ? '已更新安排' : '已改期')
  } catch (err) {
    toast?.error(err?.message || '改期失败')
  } finally {
    mutating.value = false
  }
}

// 双击月格子空白：快速创建并预填该日为截止日期（单击仍是选中日期）
function onCellDblClick(date) {
  emit('create', { due_date: date })
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
    toast?.success('已更新安排')
  } catch (err) {
    toast?.error(err?.message || '排期失败')
  } finally {
    mutating.value = false
  }
}

function refreshFromTaskChanges() {
  loadDaySchedule(selectedDate.value)
  loadMonthSchedule(cursor.value)
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
    toast?.success('已顺延到明天')
  } catch (err) {
    toast?.error(err?.message || '移动排期失败')
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
    toast?.success('已移除排期')
  } catch (err) {
    toast?.error(err?.message || '移除排期失败')
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

watch(
  () => props.tasks,
  () => {
    refreshFromTaskChanges()
  },
  { deep: true }
)

onMounted(async () => {
  await refreshVisibleSchedule()
})
</script>

<template>
  <section class="calendar-action-center workspace-page">
    <PageHeader icon="calendar" title="日程行动中心" :subtitle="focusPhrase">
      <template #actions>
        <SegmentedControl v-model="mode" :options="modeOptions" aria-label="日程视图模式" />
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
      </template>
    </PageHeader>

    <FirstRunTip
      tip-key="zs-tip-calendar"
      icon="calendar"
      text="双击空白格按该日期快速创建，拖拽条目可直接改期"
    />

    <div class="signal-grid">
      <article v-for="signal in actionSignals" :key="signal.key" class="metric-tile signal-card">
        <ArtIcon :name="signal.icon" :tone="signal.tone" :size="34" tile :label="signal.label" />
        <div>
          <strong>{{ signal.count }}</strong>
          <span>{{ signal.label }}</span>
        </div>
      </article>
    </div>

    <p v-if="error" class="error-line" role="alert">{{ error }}</p>

    <div v-if="mode === 'day'" class="day-layout" data-view-mode="day">
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
            <ArtIcon name="assistant" tone="aqua" :size="44" tile label="助手排程" />
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
              <ArtIcon :name="bucket.icon" :tone="bucket.tone" :size="34" tile :label="bucket.title" />
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
                  <span v-if="item.entry?.source" class="task-pill">来源 {{ item.entry.source }}</span>
                  <span v-if="item.entry?.start_time" class="task-pill">{{ item.entry.start_time }}<template v-if="item.entry?.end_time">-{{ item.entry.end_time }}</template></span>
                  <span v-if="item.entry?.note" class="task-pill note-pill">{{ item.entry.note }}</span>
                  <span v-if="item.task.subtasks?.length" class="task-pill">子任务 {{ item.task.subtasks.filter((subtask) => subtask.done).length }}/{{ item.task.subtasks.length }}</span>
                  <span v-if="item.task.files?.length" class="task-pill">资料 {{ item.task.files.length }}</span>
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

          <EmptyState v-else :icon="bucket.icon" :title="bucket.empty.title" :hint="bucket.empty.text" compact />
        </section>
      </main>
    </div>

    <div v-else class="month-layout" data-view-mode="month">
      <section class="month-plan-grid glass">
        <div class="month-weekdays">
          <span v-for="label in WEEK_LABELS" :key="label">{{ label }}</span>
        </div>

        <div class="month-grid" @dragleave="onGridDragLeave">
          <div
            v-for="cell in monthCells"
            :key="cell.date"
            class="month-cell"
            :class="[
              monthIntensityClass(cell.summary),
              {
                muted: !cell.inMonth,
                today: cell.isToday,
                selected: cell.isSelected,
                'drop-target': dropTargetDate === cell.date && dragPayload?.date !== cell.date,
              },
            ]"
            role="button"
            tabindex="0"
            :title="`${formatShortDate(cell.date)}，双击快速新建`"
            @click="selectDate(cell.date)"
            @dblclick="onCellDblClick(cell.date)"
            @keydown.enter="selectDate(cell.date)"
            @dragover="onCellDragOver($event, cell.date)"
            @drop="onCellDrop($event, cell.date)"
          >
            <div class="cell-top">
              <span class="cell-date">{{ cell.day.getDate() }}</span>
              <span v-if="cell.summary.total_count" class="cell-total">{{ cell.summary.total_count }}</span>
            </div>
            <div v-if="monthChipMap.get(cell.date)?.length" class="cell-tasks">
              <span
                v-for="chip in monthChipMap.get(cell.date).slice(0, 2)"
                :key="chip.key"
                class="cell-task"
                :class="{ entry: chip.type === 'entry' }"
                draggable="true"
                :title="chipTitle(chip)"
                @click.stop="emit('open', chip.task)"
                @dragstart="onChipDragStart($event, chip)"
                @dragend="onChipDragEnd"
              >
                {{ chip.task.title }}
              </span>
              <span v-if="monthChipMap.get(cell.date).length > 2" class="cell-more">
                +{{ monthChipMap.get(cell.date).length - 2 }}
              </span>
            </div>
            <div v-if="monthSignals(cell.summary).length" class="cell-signals">
              <span
                v-for="signal in monthSignals(cell.summary)"
                :key="`${cell.date}-${signal.key}`"
                class="sig"
                :data-tone="signal.tone"
                :title="`${signal.label} ${signal.count}`"
              >●{{ signal.count }}</span>
            </div>
          </div>
        </div>
      </section>

      <aside class="selected-day-preview glass">
        <div class="preview-head">
          <ArtIcon name="calendar" tone="aqua" :size="44" tile />
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
      <AppSpinner size="lg" :label="loadingDay ? '正在更新日程…' : '正在同步月度信号…'" />
    </div>
  </section>
</template>

<style scoped>
.calendar-action-center {
  position: relative;
  display: grid;
  gap: var(--gap);
  max-width: none;
  margin: 0 auto;
  padding-bottom: 8px;
}

.calendar-action-center :deep(.page-header) {
  margin-bottom: 0;
}

/* ===== 页头操作区 ===== */
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

.nav-label span,
.rail-head p,
.assistant-panel-head p,
.bucket-title p,
.preview-head p {
  margin: 0;
  color: var(--text-soft);
}

.icon-button {
  width: 40px;
  height: 40px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
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
  gap: 6px;
  padding: 10px 18px;
  font-weight: 600;
}

.create-btn :deep(.art-icon) {
  transition: transform 0.2s ease;
}

.create-btn:hover :deep(.art-icon) {
  transform: rotate(90deg);
}

/* ===== 信号指标 ===== */
.signal-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
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
  border: 1px solid color-mix(in srgb, var(--danger) 32%, transparent);
  border-radius: var(--radius-sm);
  background: var(--danger-soft);
  color: var(--danger);
  font-weight: 700;
}

/* ===== 玻璃面板（视觉由全局 .glass 提供，这里统一圆角与内边距） ===== */
.day-rail,
.assistant-panel,
.day-bucket,
.month-plan-grid,
.selected-day-preview {
  border-radius: var(--radius);
  padding: 16px;
}

/* ===== 日模式布局 ===== */
.day-layout {
  display: grid;
  grid-template-columns: 340px minmax(0, 1fr);
  gap: var(--gap);
  align-items: start;
}

.day-side,
.day-main,
.month-layout,
.preview-buckets {
  display: grid;
  gap: var(--gap);
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
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--accent) 30%, transparent),
    color-mix(in srgb, var(--success) 18%, transparent)
  );
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
  border-radius: var(--radius-pill);
  background: var(--accent);
  box-shadow: 0 0 0 6px color-mix(in srgb, var(--accent) 14%, transparent);
}

.rail-slot[data-accent='must_do'] .slot-dot {
  background: var(--danger);
  box-shadow: 0 0 0 6px color-mix(in srgb, var(--danger) 16%, transparent);
}

.rail-slot[data-accent='planned'] .slot-dot {
  background: var(--accent);
}

.rail-slot[data-accent='in_progress_today'] .slot-dot {
  background: var(--success);
  box-shadow: 0 0 0 6px color-mix(in srgb, var(--success) 16%, transparent);
}

.rail-slot[data-accent='upcoming_pressure'] .slot-dot {
  background: var(--warning);
  box-shadow: 0 0 0 6px color-mix(in srgb, var(--warning) 16%, transparent);
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

/* 6 列网格：焦点桶（必须处理 / 今日安排）各占 3 列，次级桶各占 2 列，分区一目了然 */
.day-main {
  grid-template-columns: repeat(6, minmax(0, 1fr));
  align-items: start;
}

.day-bucket {
  display: grid;
  gap: 12px;
  align-content: start;
  grid-column: span 2;
  min-height: 200px;
}

.day-bucket.prominent {
  grid-column: span 3;
  min-height: 250px;
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
  border-radius: var(--radius-pill);
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
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
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
  border-radius: var(--radius-pill);
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
  background: color-mix(in srgb, var(--tag-color) 12%, var(--surface));
  color: color-mix(in srgb, var(--tag-color) 72%, var(--text));
}

.task-actions {
  align-items: flex-start;
  gap: 6px;
}

/* ===== 月模式布局 ===== */
.month-layout {
  grid-template-columns: minmax(0, 1.7fr) 360px;
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
  /* 行高基线 + 1fr 增量：所有行取同一 minmax(108px, 1fr)，
     每行至少 108px，最忙的行撑高时其余行同步拉齐到同一高度，消除「周与周行高不齐」。
     配合格子 overflow:hidden，任何密度下都不越界。 */
  grid-auto-rows: minmax(108px, 1fr);
}

.month-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 0;
  height: 100%;
  padding: 10px;
  overflow: hidden;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--surface-2);
  box-shadow: none;
  color: var(--text);
  text-align: left;
  cursor: pointer;
}

/* hover 规则写在热力层级之前，让层级色在悬停时保持不丢失 */
.month-cell:hover {
  background: var(--surface-3);
  border-color: var(--border-strong);
}

/* 热力底色降噪：改为左侧 3px 色条，格子底色统一 surface-2，版面立刻干净。
   drop-target/today/selected 用 box-shadow 表达（避免 overflow:hidden 裁掉 outline）。 */
.month-cell.level-1 {
  box-shadow: inset 3px 0 0 color-mix(in srgb, var(--accent) 35%, transparent);
}

.month-cell.level-2 {
  box-shadow: inset 3px 0 0 color-mix(in srgb, var(--accent) 60%, transparent);
}

.month-cell.level-3 {
  box-shadow: inset 3px 0 0 color-mix(in srgb, var(--accent) 85%, transparent);
}

.month-cell.level-4 {
  box-shadow: inset 3px 0 0 var(--accent);
}

/* 邻月 muted：只降文字与 chip 透明度，不降边框背景，避免整格发灰导致的视觉断层 */
.month-cell.muted {
  opacity: 1;
}

.month-cell.muted .cell-date {
  color: var(--text-muted);
}

.month-cell.muted .cell-tasks,
.month-cell.muted .cell-signals {
  opacity: 0.35;
}

.month-cell.today {
  border-color: var(--accent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 30%, transparent);
}

/* today/selected 与热力色条共存：合并 box-shadow */
.month-cell.today.level-1,
.month-cell.today.level-2,
.month-cell.today.level-3,
.month-cell.today.level-4 {
  box-shadow:
    inset 3px 0 0 var(--accent),
    inset 0 0 0 1px color-mix(in srgb, var(--accent) 30%, transparent);
}

.month-cell.selected {
  border-color: var(--accent-strong);
  box-shadow:
    inset 0 0 0 1px color-mix(in srgb, var(--accent-strong) 34%, transparent),
    var(--shadow-sm);
}

/* 拖拽改期：可投放的目标格子高亮（用 inset box-shadow 替代 outline，避免被 overflow:hidden 裁掉） */
.month-cell.drop-target {
  background: color-mix(in srgb, var(--accent) 10%, var(--surface-2));
  box-shadow: inset 0 0 0 2px var(--accent);
}

/* 格子里的任务条目（可拖拽改期，点击打开编辑）。flex:1 吃掉格子剩余高度，超出直接裁剪绝不越界 */
.cell-tasks {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.cell-task {
  display: block;
  max-width: 100%;
  min-height: 20px;
  padding: 1px 7px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  border-radius: var(--radius-xs);
  border: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface-solid) 85%, transparent);
  color: var(--text);
  font-size: 11px;
  font-weight: 600;
  cursor: grab;
}

.cell-task.entry {
  border-left: 3px solid var(--accent);
}

.cell-task:hover {
  border-color: var(--border-strong);
}

.cell-task:active {
  cursor: grabbing;
}

.cell-more {
  padding-left: 4px;
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 700;
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
  min-width: 18px;
  padding: 0 6px;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--accent) 18%, transparent);
  color: var(--accent-strong);
  font-size: 11px;
  line-height: 16px;
  text-align: center;
}

/* 信号区：单行内联圆点指示（无边框无背景），固定在格子底部 */
.cell-signals {
  display: flex;
  gap: 6px;
  flex-wrap: nowrap;
  align-items: center;
  margin-top: auto;
  overflow: hidden;
  white-space: nowrap;
  font-size: 10px;
  line-height: 1;
}

.cell-signals .sig {
  display: inline-flex;
  align-items: center;
  gap: 1px;
  font-weight: 800;
  letter-spacing: 0.2px;
  color: var(--text-soft);
}

.cell-signals .sig[data-tone='coral'] {
  color: var(--danger);
}

.cell-signals .sig[data-tone='aqua'] {
  color: var(--accent-strong);
}

.cell-signals .sig[data-tone='mint'] {
  color: var(--success);
}

.cell-signals .sig[data-tone='sand'] {
  color: var(--warning);
}

/* ===== 选中日预览 ===== */
.selected-day-preview {
  display: grid;
  gap: 14px;
  align-content: start;
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
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
}

.preview-bucket {
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
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
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  box-shadow: none;
  color: var(--text);
  text-align: left;
}

.preview-task:hover {
  background: var(--accent-soft);
  border-color: var(--border-strong);
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

/* ===== 局部加载遮罩 ===== */
.loading-overlay {
  position: absolute;
  inset: 0;
  z-index: 5;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius);
  background: color-mix(in srgb, var(--surface) 68%, transparent);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  color: var(--text-soft);
  font-weight: 700;
}

/* ===== 中间档 768–1100px：侧栏上置并排，月预览下沉为底部面板 ===== */
@media (max-width: 1100px) {
  .day-layout,
  .month-layout {
    grid-template-columns: 1fr;
  }

  .day-side {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    align-items: start;
  }

  .preview-summary {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .preview-signal {
    min-width: 0;
  }

  .preview-buckets {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .signal-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .day-rail,
  .assistant-panel,
  .day-bucket,
  .month-plan-grid,
  .selected-day-preview {
    padding: 14px;
  }

  .day-side {
    grid-template-columns: 1fr;
  }

  .day-main {
    grid-template-columns: 1fr;
  }

  .day-bucket,
  .day-bucket.prominent {
    grid-column: auto;
    min-height: 0;
  }

  .signal-grid {
    grid-template-columns: 1fr 1fr;
  }

  .preview-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .preview-buckets {
    grid-template-columns: 1fr;
  }

  .month-grid {
    gap: 6px;
  }

  .month-cell {
    padding: 8px;
  }
}

@media (max-width: 390px) {
  .calendar-action-center {
    gap: 12px;
  }

  .date-nav,
  .signal-grid,
  .preview-summary {
    width: 100%;
  }

  .assistant-plan-button,
  .today-button,
  .create-btn {
    min-width: 0;
  }

  .assistant-plan-button span,
  .create-btn span {
    overflow-wrap: anywhere;
  }

  .signal-grid,
  .preview-summary {
    grid-template-columns: 1fr;
  }

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
