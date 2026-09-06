<script setup lang="ts">
/**
 * 纸质日视图（M2.5）：单日时间轴，排版延续 final-calendar 的纸面出版语言——
 * 刊头（kicker / 大衬线 h1 / folio / mast-rule）+ 42px 时间轴单栏分栏。
 * - 数据：GET /api/schedule/events/expand?start=end=当日（与周/月视图同源）
 * - 课程块可点击 → 详情便签卡；审批幽灵块投影当日（多个并存）
 * - 查看的是今天时画「现在」指示线（轴外钳制到轴端，永不消失）
 */
import { fitsCalendarAxis, occurrenceTime } from '../../utils/eventPlacement'
import { computed, onMounted, ref } from 'vue'
import { useIntervalFn } from '@vueuse/core'
import { useRunStore } from '../../stores/run'
import { groupOccurrencesByDate, projectGhosts, useScheduleStore } from '../../stores/schedule'
import type { EventOccurrence } from '../../api/schedule'
import { blockPercent, cnNumber, hourLines, nowPercent, parseIsoDate, toIsoDate } from '../../utils/date'

const emit = defineEmits<{ (e: 'open', occ: EventOccurrence): void }>()

const schedule = useScheduleStore()
const run = useRunStore()

/** 本地时钟（「现在」指示线 30s 粒度） */
const now = ref(new Date())
useIntervalFn(() => (now.value = new Date()), 30_000)
const todayIso = computed(() => toIsoDate(now.value))

const date = computed(() => schedule.dayDate)
const items = computed(() => schedule.dayItems)
const timedItems = computed(() => items.value.filter(fitsCalendarAxis))
const otherItems = computed(() => items.value.filter(item => !fitsCalendarAxis(item)))

const WEEKDAY = computed(() => {
  if (!date.value) return ''
  return `星期${'日一二三四五六'[parseIsoDate(date.value).getDay()]}`
})

const headTitle = computed(() => {
  if (!date.value) return ''
  const [, m, d] = date.value.split('-')
  return `${Number(m)} 月 ${Number(d)} 日`
})

/** 当日时间跨度（首节开始 → 末节结束），无课时为空串 */
const span = computed(() => {
  if (!timedItems.value.length) return ''
  const first = timedItems.value[0]
  const last = timedItems.value[timedItems.value.length - 1]
  return `${first.start_time}–${last.end_time}`
})

/** 审批幽灵块（当日；多个并存，拒绝即消失、批准后转实体块隐去） */
const ghosts = computed(() =>
  projectGhosts(run.approvalLedger, groupOccurrencesByDate(schedule.dayOccurrences), date.value ? [date.value] : null),
)
const pendingCount = computed(() => ghosts.value.filter((g) => g.outcome === null).length)

const nowPctRaw = computed(() => (date.value === todayIso.value ? nowPercent(now.value) : null))
/** 轴外（凌晨/深夜）钳制到轴端显示，保证「现在」指示永不消失 */
const nowPct = computed(() =>
  nowPctRaw.value === null ? (date.value === todayIso.value && now.value.getHours() < 8 ? 0 : 100) : nowPctRaw.value,
)
const clockText = computed(() => {
  const d = now.value
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
})

function blockStyle(start: string, end: string): Record<string, string> | null {
  const bp = blockPercent(start, end)
  return bp ? { top: `${bp.top}%`, height: `${bp.height}%` } : null
}

function ghostStyle(start: string, end: string): Record<string, string> | null {
  return blockStyle(start, end)
}

const hourTicks = hourLines()

onMounted(() => {
  if (!schedule.dayDate) void schedule.loadSingleDay()
})
</script>

<template>
  <div class="paper day-paper">
    <!-- 刊头 -->
    <div class="dateline">
      <span>{{ date ? `${date.slice(0, 4)} 年 ${Number(date.slice(5, 7))} 月 ${Number(date.slice(8))} 日 · ${WEEKDAY}` : '' }}</span>
      <span class="today">今天 <b>{{ todayIso === date ? '正在查看' : `${now.getMonth() + 1} 月 ${now.getDate()} 日` }}</b></span>
    </div>
    <div class="masthead">
      <div>
        <div class="kicker">Daily Schedule · 单日日程</div>
        <h1>{{ headTitle }}<em> — {{ WEEKDAY }} · {{ cnNumber(items.length) }}项日程</em></h1>
      </div>
      <div class="folio">
        <div class="cell">
          <div class="num">{{ items.length }}<small>项</small></div>
          <div class="lbl">当日日程</div>
        </div>
        <div class="cell">
          <div class="num small-num">{{ span || '—' }}</div>
          <div class="lbl">时间跨度</div>
        </div>
        <div v-if="pendingCount" class="cell">
          <div class="num warn">{{ pendingCount }}<small>项</small></div>
          <div class="lbl">待你批准</div>
        </div>
      </div>
    </div>
    <div class="mast-rule" />

    <div v-if="otherItems.length" class="other-events">
      <span class="other-label">全天与其他时段</span>
      <button v-for="o in otherItems" :key="`${o.event_id}-${o.date}`" @click="emit('open', o)">{{ occurrenceTime(o) }} · {{ o.title }}</button>
    </div>
    <!-- 单日时间轴 -->
    <div class="dayaxis">
      <div class="gutter">
        <span v-for="t in hourTicks" :key="t.hm" :style="{ top: `${t.pct}%` }">{{ t.hm }}</span>
      </div>
      <div class="col" :data-today="date === todayIso ? '' : null">
        <!-- 课程块 -->
        <div
          v-for="o in timedItems"
          :key="`${o.event_id}-${o.date}`"
          class="course"
          :style="blockStyle(o.start_time, o.end_time)"
          role="button" tabindex="0"
          :title="`${o.title} · 查看详情`"
          @click="emit('open', o)" @keydown.enter.prevent="emit('open', o)" @keydown.space.prevent="emit('open', o)"
        >
          <div class="room">{{ o.location }}</div>
          <h3>{{ o.title }}</h3>
          <div class="meta">{{ o.start_time }}–{{ o.end_time }}</div>
        </div>

        <!-- 审批幽灵块 -->
        <div
          v-for="g in ghosts"
          :key="`g-${g.actionId}`"
          class="ghost"
          :style="ghostStyle(g.start, g.end)"
          :data-approved="g.outcome === 'approved' ? '' : null"
        >
          <h3>{{ g.title }}</h3>
          <div class="meta">{{ g.start }}–{{ g.end }} · 新增</div>
          <span class="stamp" :data-state="g.outcome === 'approved' ? 'approved' : 'pending'">{{ g.stamp }}</span>
        </div>

        <!-- 现在指示线（仅查看今天；轴外钳制到轴端，深宵不消失） -->
        <div
          v-if="date === todayIso"
          class="nowline"
          :style="{ top: `${nowPct}%` }"
          :data-clamped="nowPctRaw === null ? '' : null"
        >
          <span class="nl-dot" />
          <span class="nl-label">{{ clockText }}</span>
        </div>

        <!-- 空态 -->
        <div v-if="!items.length && !ghosts.length" class="empty-note" style="top: 36%">
          本日无课<small>REST</small>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>

.other-events { flex:none; display:flex; flex-wrap:wrap; gap:6px; max-height:120px; overflow:auto; padding:6px 2px 10px; font-size:12px; }
.other-events .other-label { width:100%; color:var(--paper-ink-3); font-size:11px; }
.other-events button { text-align:left; padding:6px 9px; border:1px solid var(--paper-line); border-radius:5px; color:var(--paper-ink); background:var(--paper-hi); }
.other-events button:hover,.other-events button:focus-visible { border-color:var(--paper-accent); outline:1px solid var(--paper-accent); }

/* 纸面卡片基座与周历一致（.paper 类名共享最终样式由全局? 否——本组件独立成纸）：
   这里复刻同一纸面质感，全部取 --paper-* token，与 PaperCalendar 保持一致 */
.paper {
  position: relative;
  width: 100%;
  height: 100%;
  background: var(--paper-bg);
  color: var(--paper-ink);
  border-radius: 3px;
  padding: 14px 18px;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--paper-edge);
  box-shadow:
    inset 0 1px 0 var(--paper-inset-hi),
    0 2px 6px var(--shadow-desk-near),
    0 14px 34px var(--shadow-desk-mid),
    0 34px 80px var(--shadow-desk-far);
}
.paper::after {
  content: '';
  position: absolute;
  inset: 7px;
  border: 1px solid var(--paper-frame-line);
  border-radius: 2px;
  pointer-events: none;
}

.dateline {
  display: flex;
  align-items: baseline;
  font-size: 12px;
  color: var(--paper-ink-3);
  letter-spacing: 0.05em;
  padding: 2px 2px 6px;
}
.dateline .today {
  margin-left: auto;
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.dateline .today b {
  font-weight: 600;
  color: var(--paper-ink-2);
}
.masthead {
  display: flex;
  align-items: flex-end;
  gap: 20px;
  padding: 0 2px 8px;
}
.masthead .kicker {
  font-family: var(--mono);
  font-size: 11.5px;
  letter-spacing: 0.18em;
  color: var(--paper-accent-text);
  text-transform: uppercase;
  margin-bottom: 5px;
}
.masthead h1 {
  font-family: var(--serif-paper);
  font-weight: 600;
  font-size: 34px;
  line-height: 1.04;
  letter-spacing: -0.015em;
}
.masthead h1 em {
  font-style: italic;
  font-weight: 500;
  font-size: 0.62em;
  color: var(--paper-ink-2);
}
.folio {
  margin-left: auto;
  display: flex;
  align-self: flex-end;
}
.folio .cell {
  padding: 2px 0 2px 14px;
  border-left: 1px solid var(--paper-line);
  min-width: 74px;
}
.folio .num {
  font-family: var(--serif-paper);
  font-size: 22px;
  font-weight: 600;
  line-height: 1.1;
}
.folio .num small {
  font-size: 13px;
  font-weight: 500;
  margin-left: 1px;
}
.folio .num.warn {
  color: var(--paper-accent-text);
}
.folio .num.small-num {
  font-size: 16px;
  font-family: var(--mono);
  padding-top: 4px;
}
.folio .lbl {
  font-size: 11.5px;
  color: var(--paper-ink-3);
  margin-top: 2px;
  letter-spacing: 0.06em;
}
.mast-rule {
  flex: none;
  border-top: 3px solid var(--paper-ink);
  border-bottom: 1px solid var(--paper-ink);
  height: 6px;
  margin: 0 2px 10px;
}

/* 单日时间轴：42px 刻度 + 单栏 */
.dayaxis {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 42px 1fr;
}
.gutter {
  position: relative;
  min-height: 0;
}
.gutter span {
  position: absolute;
  right: 8px;
  transform: translateY(-6px);
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--paper-ink-3);
}
.col {
  position: relative;
  margin: 0 6px 0 12px;
  border-left: 1px solid var(--paper-line);
  border-bottom: 1px solid var(--paper-kraft);
  min-height: 0;
  background-image: linear-gradient(to bottom, var(--paper-kraft) 0 1px, transparent 1px);
  background-size: 100% calc(100% / 13);
}
.col[data-today] {
  background-color: var(--paper-hi);
}

.course {
  position: absolute;
  left: 3px;
  right: 4px;
  background: var(--paper-hi);
  border: 1px solid var(--paper-line);
  border-radius: 3px;
  padding: 6px 10px;
  box-shadow: 0 1px 0 var(--paper-block-shadow);
  overflow: hidden;
  cursor: pointer;
  text-align: left;
  z-index: 1;
}
.course:hover {
  border-color: var(--paper-accent);
}
.course:focus-visible {
  outline: 1.5px solid var(--paper-accent);
  outline-offset: 1px;
}
.course .room {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--paper-accent-text);
  letter-spacing: 0.02em;
  line-height: 1.25;
}
.course h3 {
  font-family: var(--serif-paper);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.25;
  margin: 2px 0;
}
.course .meta {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--paper-ink-3);
  line-height: 1.25;
}

.ghost {
  position: absolute;
  left: 3px;
  right: 4px;
  border: 1.5px dashed var(--paper-accent);
  border-radius: 3px;
  background: repeating-linear-gradient(-45deg, var(--paper-ghost-tint) 0 6px, transparent 6px 12px);
  padding: 5px 8px;
  overflow: hidden;
  z-index: 2;
}
.ghost[data-approved='true'] {
  opacity: 0.85;
}
.ghost h3 {
  font-family: var(--serif-paper);
  font-size: 12.5px;
  font-weight: 600;
  color: var(--paper-accent-text);
  line-height: 1.3;
}
.ghost .meta {
  font-size: 11.5px;
  color: var(--paper-accent-text);
  line-height: 1.4;
  margin-top: 1px;
}
.ghost .stamp {
  display: inline-block;
  margin-top: 5px;
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--paper-accent-text);
  border: 1px solid var(--paper-accent);
  border-radius: 2px;
  padding: 1px 6px;
  letter-spacing: 0.08em;
}
.ghost .stamp[data-state='approved'] {
  border-style: solid;
  background: var(--paper-ghost-tint);
}

.nowline {
  position: absolute;
  left: 0;
  right: 0;
  height: 0;
  border-top: 1.5px solid var(--paper-accent);
  z-index: 3;
}
.nl-dot {
  position: absolute;
  left: -4px;
  top: -4.5px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--paper-accent);
}
.nl-label {
  position: absolute;
  right: 6px;
  top: -10px;
  font-family: var(--mono);
  font-size: 10.5px;
  font-weight: 600;
  color: var(--paper-hi);
  background: var(--paper-accent);
  border-radius: 3px;
  padding: 1px 6px;
  line-height: 1.4;
}
.nowline[data-clamped] {
  border-top-style: dashed;
  opacity: 0.75;
}

.empty-note {
  position: absolute;
  left: 0;
  right: 0;
  text-align: center;
  font-family: var(--serif-paper);
  font-style: italic;
  font-size: 12.5px;
  color: var(--paper-ink-3);
}
.empty-note small {
  display: block;
  font-style: normal;
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--paper-ink-3);
  margin-top: 3px;
  letter-spacing: 0.1em;
}
</style>
