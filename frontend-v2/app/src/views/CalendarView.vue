<script setup lang="ts">
/**
 * 日历标签页（内容区）：暗桌 + 纸面（PaperCalendar 周历 / PaperDayView 日视图 /
 * PaperMonthView 月视图），M2.5 起支持日/周/月切换。
 * - 视图切换控件（日|周|月）+ 换页箭头 + 回今按钮，全部 Teleport 到壳层内容头右侧
 *   （#head-actions，融入 final-calendar 的 content-head 控件区风格：.seg 分段控件）
 *   头部不放日期区间文本（纸面刊头已完整展示，重复即挤折内容头——M6 修复）；
 *   控件满行时随壳层 .content-head 整体折到第二行，绝不挤压成竖排
 * - 三种视图数据同源：GET /api/schedule/events/expand（RRULE 后端展开）
 * - 点击课程/事件块 → EventDetailCard 详情便签（RRULE 人类可读）；月历点击某天 → 日视图
 * - 桌面有一道自上而下的台灯暖光（--desk-glow），纸面浮于其上
 */
import { useRoute, useRouter } from 'vue-router'
import { parseCalendarTarget } from '../api/calendarTarget'
import { computed, onMounted, ref, watch } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import PaperCalendar from '../components/calendar/PaperCalendar.vue'
import PaperDayView from '../components/calendar/PaperDayView.vue'
import PaperMonthView from '../components/calendar/PaperMonthView.vue'
import EventDetailCard from '../components/calendar/EventDetailCard.vue'
import { SHORTCUTS } from '../keymap'
import { useViewHotkeys } from '../composables/useHotkeys'
import { useScheduleStore } from '../stores/schedule'
import type { EventOccurrence, EventDetail } from '../api/schedule'
import { firstOfMonth, toIsoDate } from '../utils/date'

type CalMode = 'day' | 'week' | 'month'

const MODES: Array<{ key: CalMode; label: string }> = [
  { key: 'day', label: '日' },
  { key: 'week', label: '周' },
  { key: 'month', label: '月' },
]

const schedule = useScheduleStore()

const mode = ref<CalMode>('week')
const exporting = ref(false), exportError = ref(''), exportNotice = ref('')
async function exportCalendar(): Promise<void> {
  if (exporting.value) return
  exporting.value = true; exportError.value = ''; exportNotice.value = ''
  try {
    const response = await fetch('/api/ical/export', { cache: 'no-store' })
    if (!response.ok) throw new Error(`导出失败（HTTP ${response.status}），请重试。`)
    const content = await response.text()
    if (!content.startsWith('BEGIN:VCALENDAR')) throw new Error('导出内容异常，请重试。')
    const url = URL.createObjectURL(new Blob([content], { type: 'text/calendar;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url; link.download = `知时日程-${toIsoDate(new Date())}.ics`
    document.body.appendChild(link); link.click(); link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 60000)
    exportNotice.value = '已发起下载。将 .ics 文件传到手机后，在支持导入的日历应用中打开；后续修改需重新导出。'
  } catch (e) {
    exportError.value = e instanceof TypeError ? '无法连接本地服务，请检查知时是否正常运行后重试。' : e instanceof Error ? e.message : '导出失败，请重试。'
  } finally { exporting.value = false }
}

const todayIso = computed(() => toIsoDate(new Date()))

/** 头部不放日期区间文本：三种视图的纸面刊头均已完整展示区间（周历「M 月 D 日 — M 月 D 日 ·
 * 第 N 周」/日视图 dateline 含年份/月历「YYYY 年 M 月」），头部重复一份会把内容头挤到折行
 * （修前 1440/800 走查实锤）。头部只保留操作：视图切换 + 换页 + 回今。 */

const centerLabel = computed(() => (mode.value === 'day' ? '今天' : mode.value === 'month' ? '本月' : '本周'))

const atCurrent = computed(() => {
  if (mode.value === 'day') return schedule.dayDate === todayIso.value
  if (mode.value === 'month') return schedule.monthAnchor === firstOfMonth(todayIso.value)
  const ds = schedule.weekDates
  return ds.length === 7 && ds.includes(todayIso.value)
})

function prev(): void {
  if (mode.value === 'day') void schedule.shiftDay(-1)
  else if (mode.value === 'month') void schedule.shiftMonth(-1)
  else void schedule.shiftWeek(-1)
}

function next(): void {
  if (mode.value === 'day') void schedule.shiftDay(1)
  else if (mode.value === 'month') void schedule.shiftMonth(1)
  else void schedule.shiftWeek(1)
}

function backToCurrent(): void {
  if (mode.value === 'day') void schedule.shiftDay(0)
  else if (mode.value === 'month') void schedule.shiftMonth(0)
  else void schedule.shiftWeek(0)
}

/** 切视图：首次进入日/月视图时按需拉取（不重复拉已加载数据） */
function switchMode(m: CalMode): void {
  mode.value = m
  detailId.value = null
  if (m === 'day' && !schedule.dayDate) void schedule.loadSingleDay()
  if (m === 'month' && !schedule.monthAnchor) void schedule.loadMonth()
}

/** 月历点某天 → 跳日视图 */
function pickDay(iso: string): void {
  void schedule.loadSingleDay(iso)
  mode.value = 'day'
}

const error = computed(() => schedule.error)

function retry(): void {
  if (mode.value === 'day') void schedule.loadSingleDay()
  else if (mode.value === 'month') void schedule.loadMonth()
  else void schedule.loadWeek(schedule.weekAnchor || undefined)
}

/** 详情便签：当前查看的事件 id（null = 关闭）与其 expand occurrence 携带的 repeat_note */
const detailId = ref<number | null>(null)
const detailOccurrenceDate = ref<string | null>(null)
const route = useRoute(), router = useRouter()
const detailRepeatNote = ref<string | null>(null)

function openDetail(occ: EventOccurrence): void {
  detailId.value = occ.event_id
  detailOccurrenceDate.value = occ.date
  detailRepeatNote.value = occ.repeat_note ?? null
}

function eventSaved(event: EventDetail): void {
  if (!event.recur_rrule) detailOccurrenceDate.value = event.date
}

function closeDetail(): void {
  detailId.value = null
  if (route.query.event) void router.replace({ path: '/calendar' })
}
watch(() => route.fullPath, value => {
  const target = parseCalendarTarget(value)
  if (!target) return
  mode.value = 'day'; void schedule.loadSingleDay(target.date)
  detailId.value = target.eventId; detailOccurrenceDate.value = target.date; detailRepeatNote.value = null
}, { immediate: true })

onMounted(() => {
  if (!schedule.weekAnchor) void schedule.loadWeek()
})

/* ---- 日历视图专属键（M4e，仅 /calendar 生效）----
 * ←/→/t 走 useViewHotkeys：本视图挂载时注册、卸载即注销（router 离开后绝不再触发），
 * 输入守卫/IME 守卫与全局键同一套。键位数据取自 keymap.ts（速查浮层的日历分组同源）。 */
useViewHotkeys(
  SHORTCUTS.filter((s) => s.group === 'calendar').flatMap((s) => s.combos ?? []),
  (combo) => {
    if (combo === 'arrowleft') prev()
    else if (combo === 'arrowright') next()
    else if (combo === 't') backToCurrent()
  },
)
</script>

<template>
  <section class="calendar-view">
    <!-- 视图切换 + 换页控件：挂到壳层内容头右侧 -->
    <Teleport defer to="#head-actions">
      <div class="seg" role="tablist" aria-label="日历视图切换">
        <button
          v-for="m in MODES"
          :key="m.key"
          class="seg-btn"
          :class="{ on: mode === m.key }"
          :data-mode="m.key"
          role="tab"
          :aria-selected="mode === m.key"
          @click="switchMode(m.key)"
        >
          {{ m.label }}
        </button>
      </div>
      <button class="nav-arrow" :title="mode === 'month' ? '上一月' : mode === 'day' ? '前一天' : '上一周'" :aria-label="mode === 'month' ? '上一月' : mode === 'day' ? '前一天' : '上一周'" @click="prev">
        <AppIcon name="chevron-down" :size="13" class="flip" />
      </button>
      <button class="nav-today" :title="`回到${centerLabel}`" :disabled="atCurrent" @click="backToCurrent">
        {{ centerLabel }}
      </button>
      <button class="nav-arrow" :title="mode === 'month' ? '下一月' : mode === 'day' ? '后一天' : '下一周'" :aria-label="mode === 'month' ? '下一月' : mode === 'day' ? '后一天' : '下一周'" @click="next">
        <AppIcon name="chevron-down" :size="13" />
      </button>
      <button id="calendar-export" class="nav-today" :disabled="exporting" title="导出全部已保存日程为 .ics 文件，可导入手机日历" @click="exportCalendar">{{ exporting ? '导出中…' : '导出日历' }}</button>
    </Teleport>

    <div v-if="error" class="cal-error">
      <span>{{ error }}</span>
      <button class="retry" @click="retry">重试</button>
    </div>

    <div v-if="exportError || exportNotice" class="export-status" :role="exportError ? 'alert' : 'status'">
      <span>{{ exportError || exportNotice }}</span>
      <button v-if="exportError" class="retry" :disabled="exporting" @click="exportCalendar">重试</button>
      <button class="retry" aria-label="关闭导出提示" @click="exportError = ''; exportNotice = ''">关闭</button>
    </div>
    <!-- 暗桌：台灯暖光下的纸面 -->
    <div class="desk" :data-loading="schedule.loading">
      <PaperCalendar v-if="mode === 'week'" @open="openDetail" />
      <PaperDayView v-else-if="mode === 'day'" @open="openDetail" />
      <PaperMonthView v-else @pick="pickDay" @open="openDetail" />
    </div>

    <!-- 事件详情便签卡（重复规则优用 expand 透出的 repeat_note，回退 RRULE 解读） -->
    <EventDetailCard
      :event-id="detailId" :occurrence-date="detailOccurrenceDate"
      :repeat-note-hint="detailRepeatNote"
      @close="closeDetail" @saved="eventSaved"
    />
  </section>
</template>

<style scoped>
.export-status { display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin:10px 16px 0; padding:10px 12px; border:1px solid var(--line-2); border-radius:7px; color:var(--ink-2); font-size:12px; line-height:1.6; }
.export-status span { flex:1; min-width:180px; }
.export-status[role="alert"] { color:var(--terra-soft); }
.calendar-view {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
/* 视图分段控件（final-calendar content-head 的 .seg 语言）。
 * 全部 flex:none + 不折行：壳层 .content-head 已允许整体换行，控件宁换行不挤压
 * （挤压会把「本周」「日历」等文字压成竖排——修前 800px 走查实锤）。 */
.seg {
  display: flex;
  flex: none;
  border: 1px solid var(--line-2);
  border-radius: 8px;
  overflow: hidden;
}
.seg-btn {
  padding: 4px 9px;
  font-size: 12px;
  color: var(--ink-3);
}
.seg-btn + .seg-btn {
  border-left: 1px solid var(--line);
}
.seg-btn:hover {
  color: var(--ink-2);
}
.seg-btn.on {
  background: var(--amber-wash);
  color: var(--amber-soft);
}
.nav-arrow {
  flex: none;
  width: 26px;
  height: 26px;
  border: 1px solid var(--line-2);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ink-3);
}
.nav-arrow:hover {
  color: var(--ink-2);
  border-color: var(--line-hover);
}
.nav-arrow .flip {
  transform: rotate(180deg);
}
.nav-today {
  flex: none;
  height: 26px;
  padding: 0 9px;
  border: 1px solid var(--line-2);
  border-radius: 8px;
  font-size: 12px;
  color: var(--ink-2);
  white-space: nowrap;
}
.nav-today:hover:not(:disabled) {
  border-color: var(--line-hover);
  color: var(--ink);
}
.nav-today:disabled {
  /* 浅色主题经 --ctl-disabled-opacity 抬到 0.75（disabled 文本 ≥3:1）；暗色走 fallback 0.45 不变 */
  opacity: var(--ctl-disabled-opacity, 0.45);
  cursor: default;
  color: var(--amber-soft);
  border-color: var(--amber-border-weak);
}
.cal-error {
  margin: 12px 20px 0;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12.5px;
  color: var(--terra-soft);
  border: 1px dashed var(--terra-dashed);
  border-radius: var(--radius-s);
  padding: 8px 12px;
}
.retry {
  font-size: 12px;
  color: var(--amber-soft);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-s);
  padding: 2px 10px;
}
.retry:hover {
  border-color: var(--line-hover);
}

/* ---- 暗桌 ---- */
.desk {
  flex: 1;
  min-height: 0;
  padding: 12px 12px 18px;
  position: relative;
  overflow: hidden;
}
.desk::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: radial-gradient(56% 60% at 50% 30%, var(--desk-glow), transparent 70%);
}
.desk :deep(.paper) {
  transition: opacity 0.2s;
}
.desk[data-loading='true'] :deep(.paper) {
  opacity: 0.75;
}
</style>
