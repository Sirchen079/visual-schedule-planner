<script setup lang="ts">
/**
 * 周日历：展示后端展开的日程与待审批排期，支持打开事件详情。
 * 全天及轴外事件单独排列，定时事件按时间轴定位。
 */
import { fitsCalendarAxis, occurrenceTime } from '../../utils/eventPlacement'
import { computed, onMounted, ref } from 'vue'
import { useIntervalFn, useResizeObserver } from '@vueuse/core'
import { useRunStore } from '../../stores/run'
import { projectGhosts, useScheduleStore, type GhostProject } from '../../stores/schedule'
import type { EventOccurrence } from '../../api/schedule'
import { blockPercent, cnNumber, hourLines, isoWeekNumber, mondayOf, parseIsoDate, toIsoDate } from '../../utils/date'

const emit = defineEmits<{ (e: 'open', occ: EventOccurrence): void }>()

const schedule = useScheduleStore()
const run = useRunStore()

const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

/** 本地时钟（dateline「今天」与今日列高亮，60s 粒度足够） */
const now = ref(new Date())
useIntervalFn(() => (now.value = new Date()), 60_000)
const todayIso = computed(() => toIsoDate(now.value))

const dates = computed(() => schedule.weekDates)

const summary = computed(() => schedule.weekSummary)

const dateline = computed(() => {
  const ds = dates.value
  if (!ds.length) return ''
  const a = ds[0].split('-')
  const b = ds[6].split('-')
  const left = `${a[0]} 年 ${Number(a[1])} 月 ${Number(a[2])} 日`
  const right = Number(b[2]) !== Number(a[2]) ? `${Number(b[1])} 月 ${Number(b[2])} 日` : `${Number(b[2])} 日`
  return `${left} — ${right} · 第 ${isoWeekNumber(ds[0])} 周`
})

const todayLabel = computed(() => {
  const d = now.value
  return `${d.getMonth() + 1} 月 ${d.getDate()} 日 星期${'日一二三四五六'[d.getDay()]}`
})

function isWeekend(iso: string): boolean {
  const wd = parseIsoDate(iso).getDay()
  return wd === 0 || wd === 6
}

const headTitle = computed(() => `第 ${dates.value.length ? isoWeekNumber(dates.value[0]) : ''} 周`)
const headEm = computed(() => ` — ${cnNumber(summary.value.count)}项日程`)
const otherItems = computed(() => schedule.occurrences.filter(item => !fitsCalendarAxis(item)))

/** 审批幽灵块投影（本显示周内；多个并存，拒绝即消失、批准后转实体块隐去） */
const ghosts = computed(() => projectGhosts(run.approvalLedger, schedule.byDate, dates.value))
const pendingCount = computed(() => ghosts.value.filter((g) => g.outcome === null).length)
const landingCount = computed(() => ghosts.value.filter((g) => g.outcome === 'approved').length)

function ghostsOf(date: string) {
  return ghosts.value.filter((g) => g.date === date)
}

function ghostStyle(start: string, end: string): Record<string, string> | null {
  const bp = blockPercent(start, end)
  return bp ? { top: `${bp.top}%`, height: `${bp.height}%` } : null
}

/** 时间轴像素高（.week 高 − 表头行），ResizeObserver 实测；0 = 未测量（按 full 渲染） */
const weekEl = ref<HTMLElement | null>(null)
const axisH = ref(0)
useResizeObserver(weekEl, (entries) => {
  axisH.value = Math.max(0, entries[0].contentRect.height - 36)
})

/**
 * 短块降级档位（按渲染像素高，而非时长百分比——轴高随窗口高变化）：
 * - full：块够高，完整排版（overflow:hidden 兜底）；
 * - compact：只留标题一行省略（时刻/图章走 title tooltip），防多行文字被生硬切断；
 * - chip：连一行都放不下，只渲染色块本体（幽灵块仍是虚线斜纹），信息全走 tooltip。
 */
type BlockFit = 'full' | 'compact' | 'chip'
function fitOf(start: string, end: string, fullMinPx: number, compactMinPx: number): BlockFit {
  const bp = blockPercent(start, end)
  if (!bp || axisH.value <= 0) return 'full'
  const px = (bp.height / 100) * axisH.value
  if (px < compactMinPx) return 'chip'
  if (px < fullMinPx) return 'compact'
  return 'full'
}

/** 幽灵块：完整排版需 标题+时刻+图章 ≈70px；一行标题 ≈22px */
function ghostFit(start: string, end: string): BlockFit {
  return fitOf(start, end, 70, 22)
}

/** 课程块：完整排版需 教室+标题+时刻 ≈54px；一行标题 ≈20px */
function courseFit(start: string, end: string): BlockFit {
  return fitOf(start, end, 54, 20)
}

/** 幽灵块 tooltip：标题/时刻/重复规则/图章全量信息，窄列省略或短块降级时的兜底 */
function ghostTitle(g: GhostProject): string {
  const parts = [`${g.title}（${g.start}–${g.end} · 新增）`]
  if (g.repeatText) parts.push(g.repeatText)
  parts.push(g.stamp)
  return parts.join(' · ')
}

function itemsOf(date: string): EventOccurrence[] {
  return schedule.byDate[date] ?? []
}

/** 课程块 tooltip：标题 + 查看详情提示 + repeat_note 周次规则（expand 透出时） */
function blockTitle(o: EventOccurrence): string {
  const note = o.repeat_note?.trim()
  return `${o.title} · 查看详情${note ? ` · ${note}` : ''}`
}

function blockStyle(start: string, end: string): Record<string, string> | null {
  const bp = blockPercent(start, end)
  return bp ? { top: `${bp.top}%`, height: `${bp.height}%` } : null
}

/** 教室显示：空值/「待定」原样展示（基准稿：周三课「教室待定」） */
const hourTicks = hourLines()

onMounted(() => {
  if (!schedule.weekAnchor) void schedule.loadWeek(mondayOf(todayIso.value))
})
</script>

<template>
  <div class="paper">
    <!-- 刊头 -->
    <div class="dateline">
      <span>{{ dateline }}</span>
      <span class="today">今天 <b>{{ todayLabel }}</b></span>
    </div>
    <div class="masthead">
      <div>
        <div class="kicker">Weekly Schedule · 周日程</div>
        <h1>{{ headTitle }}<em>{{ headEm }}</em></h1>
      </div>
      <div class="folio">
        <div class="cell">
          <div class="num">{{ summary.count }}<small>项</small></div>
          <div class="lbl">本周日程</div>
        </div>
        <div class="cell">
          <div class="num">{{ summary.days }}<small>天</small></div>
          <div class="lbl">有课日</div>
        </div>
        <div v-if="pendingCount" class="cell">
          <div class="num warn">{{ pendingCount }}<small>项</small></div>
          <div class="lbl">待你批准</div>
        </div>
        <div v-if="landingCount" class="cell">
          <div class="num warn">{{ landingCount }}<small>项</small></div>
          <div class="lbl">批准落地中</div>
        </div>
      </div>
    </div>
    <div class="mast-rule" />

    <div v-if="otherItems.length" class="other-events">
      <span class="other-label">全天与其他时段</span>
      <button v-for="o in otherItems" :key="`${o.event_id}-${o.date}`" @click="emit('open', o)">{{ o.date.slice(5) }} · {{ occurrenceTime(o) }} · {{ o.title }}</button>
    </div>
    <!-- 周视图：细线分栏（列有 min-width 下限，极窄窗口下纸内横向滚动而非挤碎） -->
    <div ref="weekEl" class="week">
      <div class="corner" />
      <div v-for="(d, i) in dates" :key="'h-' + d" class="dayhead">
        <span class="dn">{{ Number(d.slice(8)) }}</span>
        <span class="wd">{{ WEEKDAYS[i] }}</span>
        <span v-if="d === todayIso" class="tag">今天</span>
      </div>

      <div class="gutter">
        <span v-for="t in hourTicks" :key="t.hm" :style="{ top: `${t.pct}%` }">{{ t.hm }}</span>
      </div>

      <div
        v-for="d in dates"
        :key="'c-' + d"
        class="col"
        :data-weekend="isWeekend(d)"
        :data-today="d === todayIso ? '' : null"
      >
        <!-- 课程块（点击看详情便签；tooltip 带上 expand 透出的 repeat_note 周次规则） -->
        <div
          v-for="o in itemsOf(d).filter(fitsCalendarAxis)"
          :key="`${o.event_id}-${o.date}`"
          class="course"
          :style="blockStyle(o.start_time, o.end_time)"
          :data-fit="courseFit(o.start_time, o.end_time)"
          role="button" tabindex="0"
          :title="blockTitle(o)"
          @click="emit('open', o)" @keydown.enter.prevent="emit('open', o)" @keydown.space.prevent="emit('open', o)"
        >
          <div class="room">{{ o.location }}</div>
          <h3>{{ o.title }}</h3>
          <div class="meta">{{ o.start_time }}–{{ o.end_time }}</div>
        </div>

        <!-- 审批幽灵块（与对话内审批卡镜像；可多个并存；args 带重复规则时显示 repeat 行） -->
        <div
          v-for="g in ghostsOf(d)"
          :key="`g-${g.actionId}`"
          class="ghost"
          :style="ghostStyle(g.start, g.end)"
          :data-approved="g.outcome === 'approved' ? '' : null"
          :data-fit="ghostFit(g.start, g.end)"
          :title="ghostTitle(g)"
        >
          <h3>{{ g.title }}</h3>
          <div class="meta">{{ g.start }}–{{ g.end }} · 新增</div>
          <div v-if="g.repeatText" class="meta repeat">{{ g.repeatText }}</div>
          <span class="stamp" :data-state="g.outcome === 'approved' ? 'approved' : 'pending'">{{ g.stamp }}</span>
        </div>

        <!-- 空栏注 -->
        <div
          v-if="!itemsOf(d).length && !ghostsOf(d).length"
          class="empty-note"
          style="top: 36%"
        >
          本版无课<small>REST</small>
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

/* ---- 纸面卡片：深色书桌上摊开的一张纸 ---- */
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
  /* 尺寸容器：窄列/窄窗的降级样式走 container query（列宽 = (容器宽 − 42px 轴) / 7） */
  container-type: inline-size;
  container-name: paper;
  box-shadow:
    inset 0 1px 0 var(--paper-inset-hi),
    0 2px 6px var(--shadow-desk-near),
    0 14px 34px var(--shadow-desk-mid),
    0 34px 80px var(--shadow-desk-far);
}
/* 裱边：纸内一圈发丝印刷线 */
.paper::after {
  content: '';
  position: absolute;
  inset: 7px;
  border: 1px solid var(--paper-frame-line);
  border-radius: 2px;
  pointer-events: none;
}

/* ---- 刊头（A 的出版语言） ---- */
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

/* ---- 周视图（细线分栏，占满纸面剩余高度） ----
   列宽下限 76px：壳层对话列常驻 570px，窗口 ~900px 时纸面仅 ~250px，
   若纯 1fr 挤压每列只剩 ~24px，任何文字处理都无法体面 —— 此时纸内横向滚动，
   正常宽度下 minmax(…,1fr) 与原 1fr 行为一致（设计稿基准不变）。 */
.week {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 42px repeat(7, minmax(76px, 1fr));
  grid-template-rows: 36px 1fr;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: thin;
  scrollbar-color: var(--paper-line) var(--paper-bg);
}
/* 时间轴与左上角在横向滚动时钉住，遮住滑入的日栏（z 高于幽灵块 z:2） */
.corner {
  position: sticky;
  left: 0;
  z-index: 3;
  background: var(--paper-bg);
}
.gutter {
  position: sticky;
  left: 0;
  z-index: 3;
  background: var(--paper-bg);
  min-height: 0;
}
.dayhead {
  height: 36px;
  min-width: 0;
  display: flex;
  align-items: flex-end;
  gap: 6px;
  padding: 0 7px 5px;
  border-left: 1px solid var(--paper-line);
}
/* 头部单元格不换行、不收缩变形：窄窗下由下方 container query 整体堆叠，而非挤压错位 */
.dayhead .dn,
.dayhead .wd,
.dayhead .tag {
  flex: none;
  white-space: nowrap;
}
.dayhead .wd {
  font-size: 11.5px;
  color: var(--paper-ink-3);
  padding-bottom: 2px;
  letter-spacing: 0.08em;
}
.dayhead .dn {
  font-family: var(--serif-paper);
  font-size: 22px;
  font-weight: 600;
  line-height: 1;
  letter-spacing: -0.01em;
}
.dayhead .tag {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--paper-accent-text);
  padding-bottom: 2px;
  margin-left: auto;
}
.col {
  position: relative;
  border-left: 1px solid var(--paper-line);
  border-bottom: 1px solid var(--paper-kraft);
  min-height: 0;
  background-image: linear-gradient(to bottom, var(--paper-kraft) 0 1px, transparent 1px);
  background-size: 100% calc(100% / 13);
}
.col[data-weekend='true'] {
  background-color: var(--paper-tint);
}
/* 今日列高亮（置后声明：周末且是今天时今日优先） */
.col[data-today] {
  background-color: var(--paper-hi);
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
/* 首末刻度标签收进轴内：.week 纵向 hidden 裁切，居中写法会让 08:00/21:00 溢出被切 */
.gutter span:first-child {
  transform: translateY(0);
}
.gutter span:last-child {
  transform: translateY(-15px);
}

.course {
  position: absolute;
  left: 3px;
  right: 4px;
  background: var(--paper-hi);
  border: 1px solid var(--paper-line);
  border-radius: 3px;
  padding: 4px 7px;
  box-shadow: 0 1px 0 var(--paper-block-shadow);
  overflow: hidden;
  cursor: pointer;
  text-align: left;
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
  font-size: 11.5px;
  font-weight: 600;
  line-height: 1.22;
  margin: 1px 0;
}
.course .meta {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--paper-ink-3);
  line-height: 1.25;
}

/* 待批准的幽灵块（与对话内审批卡互为镜像） */
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
/* 幽灵块的重复规则行（repeat_note/rrule 文案）：mono 小字与时刻行区分 */
.ghost .meta.repeat {
  font-family: var(--mono);
  font-size: 11px;
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
/* 已批准、等待落库实体化的幽灵块：实线章 + 更淡的斜纹底，与「待批准」区分 */
.ghost .stamp[data-state='approved'] {
  border-style: solid;
  background: var(--paper-ghost-tint);
}
.ghost[data-approved='true'] {
  opacity: 0.85;
}
/* ---- 短块降级（data-fit 按渲染像素高三档，见脚本 fitOf）----
   避免 overflow:hidden 把多行文字切半；虚线边框与 ghost 语义不变，信息走 title tooltip */
/* compact：只留标题一行省略 */
.ghost[data-fit='compact'] {
  padding: 2px 6px;
  display: flex;
  align-items: center;
}
.ghost[data-fit='compact'] h3 {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ghost[data-fit='compact'] .meta,
.ghost[data-fit='compact'] .stamp {
  display: none;
}
/* chip：一行都放不下 → 只渲染色块本体（虚线斜纹仍在），信息全走 tooltip */
.ghost[data-fit='chip'] {
  padding: 1px 4px;
}
.ghost[data-fit='chip'] h3,
.ghost[data-fit='chip'] .meta,
.ghost[data-fit='chip'] .stamp {
  display: none;
}
.course[data-fit='compact'] {
  padding: 2px 6px;
  display: flex;
  align-items: center;
}
.course[data-fit='compact'] h3 {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.course[data-fit='compact'] .room,
.course[data-fit='compact'] .meta {
  display: none;
}
.course[data-fit='chip'] {
  padding: 1px 4px;
}
.course[data-fit='chip'] .room,
.course[data-fit='chip'] h3,
.course[data-fit='chip'] .meta {
  display: none;
}
/* ---- 窄列降级（container query，按纸面容器宽而非窗口宽生效） ----
   每列宽 ≈ (容器宽 − 42px 时间轴) / 7：容器 ≤ 950px 即每列 ≲130px，
   幽灵块/课程块文字由「换行 + 生硬裁切」改为单行省略，全量信息走 title tooltip。 */
@container paper (max-width: 950px) {
  .ghost {
    padding: 4px 6px;
  }
  .ghost h3,
  .ghost .meta {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  /* 重复规则行整行收起（tooltip 兜底），图章收紧内边距保持可见 */
  .ghost .meta.repeat {
    display: none;
  }
  .ghost .stamp {
    padding: 1px 4px;
  }
  .course h3,
  .course .meta,
  .course .room {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}
/* 更窄（容器 ≤ 880px，每列 ≲120px）：头部「日期 + 星期」堆叠为两行（日期字号降级），
   今日徽标绝对定位到本格右上角——不再三者挤一行导致换行错位。 */
@container paper (max-width: 880px) {
  .dayhead {
    position: relative;
    flex-direction: column;
    align-items: flex-start;
    gap: 1px;
    padding: 0 6px 3px;
  }
  .dayhead .dn {
    font-size: 17px;
  }
  .dayhead .wd {
    padding-bottom: 0;
    line-height: 1.15;
  }
  .dayhead .tag {
    position: absolute;
    right: 6px;
    bottom: 3px;
    margin-left: 0;
    padding-bottom: 0;
  }
  /* 刊头同档降级：两短语整段换行不交错（今天短语保持完整），h1 字号降级、folio 允许换行 */
  .dateline {
    flex-wrap: wrap;
    row-gap: 2px;
  }
  .dateline .today {
    white-space: nowrap;
    margin-left: auto;
  }
  .masthead {
    flex-wrap: wrap;
    row-gap: 8px;
  }
  .masthead h1 {
    font-size: 24px;
  }
  .folio {
    flex-wrap: wrap;
    justify-content: flex-end;
    row-gap: 4px;
  }
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
