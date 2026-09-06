<script setup lang="ts">
/**
 * 纸质月视图（M2.5）：传统月历版面（周首 = 周一，与周视图约定一致）。
 * - 数据：GET /api/schedule/events/expand（覆盖 6 周网格首末）——
 *   /api/schedule/month 实测只含任务负载（task_count），不含 events，月历必须走 expand
 * - 格内：日程数 + 最多两条简要条目 + 「等 N 项」；审批幽灵块以赤陶虚线角标投影
 * - 点击某天 → 切到日视图；月外溢出日灰显；今日高亮 --paper-hi；周末微染 --paper-tint
 */
import type { EventOccurrence } from '../../api/schedule'
import { computed, onMounted, ref } from 'vue'
import { useIntervalFn } from '@vueuse/core'
import { useRunStore } from '../../stores/run'
import { projectGhosts, useScheduleStore } from '../../stores/schedule'
import { cnNumber, monthGrid, parseIsoDate, toIsoDate } from '../../utils/date'

const emit = defineEmits<{ (e: 'pick', date: string): void; (e: 'open', occurrence: EventOccurrence): void }>()

const schedule = useScheduleStore()
const run = useRunStore()

const now = ref(new Date())
useIntervalFn(() => (now.value = new Date()), 60_000)
const todayIso = computed(() => toIsoDate(now.value))

const anchor = computed(() => schedule.monthAnchor)

/** 6×7 网格（ISO 日期） */
const grid = computed(() => (anchor.value ? monthGrid(anchor.value) : []))

const monthLabel = computed(() => {
  if (!anchor.value) return ''
  const [y, m] = anchor.value.split('-')
  return `${y} 年 ${Number(m)} 月`
})

const summary = computed(() => {
  const by = schedule.monthByDate
  let count = 0
  let days = 0
  for (const week of grid.value) {
    for (const d of week) {
      const n = by[d]?.length ?? 0
      count += n
      if (n > 0) days += 1
    }
  }
  return { count, days }
})

const headEm = computed(() => ` — ${cnNumber(summary.value.count)}项日程 · ${summary.value.days}个有课日`)

/** 审批幽灵块（月网格范围内；多个并存） */
const ghosts = computed(() => projectGhosts(run.approvalLedger, schedule.monthByDate, null))
const ghostDates = computed(() => new Set(ghosts.value.map((g) => g.date)))
const pendingCount = computed(() => ghosts.value.filter((g) => g.outcome === null).length)

const WEEK_HEADS = ['一', '二', '三', '四', '五', '六', '日']

function monthOf(iso: string): string {
  return iso.slice(0, 7)
}

function isOutside(iso: string): boolean {
  return anchor.value ? monthOf(iso) !== monthOf(anchor.value) : false
}

function isWeekend(iso: string): boolean {
  const wd = parseIsoDate(iso).getDay()
  return wd === 0 || wd === 6
}

function entriesOf(iso: string) {
  return (schedule.monthByDate[iso] ?? []).slice(0, 2)
}

function moreCount(iso: string): number {
  return Math.max((schedule.monthByDate[iso]?.length ?? 0) - 2, 0)
}

onMounted(() => {
  if (!schedule.monthAnchor) void schedule.loadMonth()
})
</script>

<template>
  <div class="paper">
    <!-- 刊头 -->
    <div class="dateline">
      <span>{{ monthLabel }} · 月历网格以周一为一周之首</span>
      <span class="today">今天 <b>{{ todayIso }}</b></span>
    </div>
    <div class="masthead">
      <div>
        <div class="kicker">Monthly Overview · 月历</div>
        <h1>{{ monthLabel }}<em>{{ headEm }}</em></h1>
      </div>
      <div class="folio">
        <div class="cell">
          <div class="num">{{ summary.count }}<small>项</small></div>
          <div class="lbl">本月日程</div>
        </div>
        <div class="cell">
          <div class="num">{{ summary.days }}<small>天</small></div>
          <div class="lbl">有日程日</div>
        </div>
        <div v-if="pendingCount" class="cell">
          <div class="num warn">{{ pendingCount }}<small>项</small></div>
          <div class="lbl">待你批准</div>
        </div>
      </div>
    </div>
    <div class="mast-rule" />

    <!-- 月历格子 -->
    <div class="month">
      <div class="weekhead">
        <span v-for="w in WEEK_HEADS" :key="w">{{ w }}</span>
      </div>
      <div class="cells">
        <template v-for="(week, wi) in grid" :key="'w' + wi">
          <div
            v-for="d in week"
            :key="d"
            class="cell"
            :data-outside="isOutside(d) ? '' : null"
            :data-weekend="isWeekend(d) ? '' : null"
            :data-today="d === todayIso ? '' : null"
            :data-has="entriesOf(d).length ? '' : null"
            :title="`${d} · 查看日视图`"
            tabindex="0" role="group"
            @click="emit('pick', d)" @keydown.enter.self.prevent="emit('pick', d)" @keydown.space.self.prevent="emit('pick', d)"
          >
            <span class="dn">{{ Number(d.slice(8)) }}</span>
            <span v-if="d === todayIso" class="tdy">今</span>
            <span v-if="ghostDates.has(d)" class="ghostmark" :title="'有待审批的新日程'">待批</span>
            <button v-for="o in entriesOf(d)" :key="`${o.event_id}-${o.date}`" class="entry" :title="`修改行程：${o.title}`" @click.stop="emit('open', o)">{{ o.title }}</button>
            <span v-if="moreCount(d) > 0" class="more">等 {{ moreCount(d) }} 项</span>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.entry { text-align:left; width:100%; cursor:pointer; }
.entry:hover,.entry:focus-visible { text-decoration:underline; color:var(--paper-accent-text); }
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

/* 月历格子 */
.month {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.weekhead {
  flex: none;
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  border-bottom: 1px solid var(--paper-line);
}
.weekhead span {
  padding: 0 8px 4px;
  font-size: 11.5px;
  letter-spacing: 0.14em;
  color: var(--paper-ink-3);
}
.cells {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  grid-template-rows: repeat(6, 1fr);
}
.cell {
  position: relative;
  border-left: 1px solid var(--paper-line);
  border-bottom: 1px solid var(--paper-kraft);
  padding: 3px 6px 2px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
  min-height: 0;
  overflow: hidden;
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  color: var(--paper-ink);
}
.cell:nth-child(7n + 1) {
  border-left: none;
}
.cell:hover {
  background: var(--paper-tint);
}
.cell[data-weekend] {
  background-color: var(--paper-tint);
}
.cell:hover[data-weekend] {
  background-color: var(--paper-kraft);
}
.cell[data-today] {
  background-color: var(--paper-hi);
  box-shadow: inset 0 0 0 1.5px var(--paper-accent);
}
.cell[data-outside] {
  color: var(--paper-ink-3);
  background-image: repeating-linear-gradient(-45deg, var(--paper-ghost-tint) 0 5px, transparent 5px 10px);
  background-color: transparent;
}
.cell .dn {
  font-family: var(--serif-paper);
  font-size: 15px;
  font-weight: 600;
  line-height: 1.1;
}
.cell[data-today] .dn {
  color: var(--paper-accent-text);
}
.cell .tdy {
  position: absolute;
  top: 4px;
  right: 6px;
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--paper-accent-text);
  border: 1px solid var(--paper-accent);
  border-radius: 2px;
  padding: 0 3px;
}
.cell .ghostmark {
  position: absolute;
  top: 3px;
  right: 26px;
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--paper-accent-text);
  border: 1px dashed var(--paper-accent);
  border-radius: 2px;
  padding: 0 4px;
  letter-spacing: 0.08em;
}
.cell .entry {
  max-width: 100%;
  font-size: 11px;
  line-height: 1.3;
  color: var(--paper-ink-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding-left: 7px;
  position: relative;
}
/* 条目前的赤陶小点（纸上批注感） */
.cell .entry::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--paper-accent);
}
.cell .more {
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--paper-ink-3);
  letter-spacing: 0.04em;
}
</style>
