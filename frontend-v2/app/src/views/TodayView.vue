<script setup lang="ts">
/**
 * 今日视图（默认落地页夜间书房语言，消费 --bg/--ink token）：
 * - 左侧「现在」面板：衬线大时钟 + 长日期 + 下一节日程 + 今日统计（高密度 ≥3 处差异信息）
 * - 冲突警示带（--terra 系 token）：今日有冲突时出现在「现在」卡下方，可展开列出冲突项
 *   （含近 7 日窗内未来冲突日）；无冲突不渲染。数据随 loadToday 同源刷新
 * - 「今日空闲」卡：free-slots 的 ≥30 分钟整段空档列表；空态给明确文案
 * - 右侧当日时间轴（08:00–21:00，与纸质周历同轴）：暗色日程块 + 琥珀「现在」指示线
 * - 空态：真实无日程时的引导；错误：行内警告 + 重试
 * - 数据：GET /api/schedule/day + /conflicts + /free-slots（后端 RRULE 展开），挂载即拉取；
 *   run 写操作后由壳层刷新
 */
import { computed, onMounted, ref } from 'vue'
import { useIntervalFn } from '@vueuse/core'
import { useScheduleStore } from '../stores/schedule'
import type { ConflictItem } from '../api/schedule'
import { blockPercent, hmToMinutes, hourLines, nowPercent } from '../utils/date'

const schedule = useScheduleStore()

/** 本地时钟（30s 粒度足够「现在」指示与进行中判定） */
const now = ref(new Date())
useIntervalFn(() => (now.value = new Date()), 30_000)

const nowPctRaw = computed(() => nowPercent(now.value))
/** 轴外（凌晨/深夜）钳制到轴端显示，保证「现在」指示永不消失 */
const nowPct = computed(() => (nowPctRaw.value === null ? (now.value.getHours() < 8 ? 0 : 100) : nowPctRaw.value))
const clockText = computed(() => {
  const d = now.value
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
})
const longDate = computed(() => {
  const d = now.value
  const wd = '日一二三四五六'[d.getDay()]
  return `${d.getFullYear()} 年 ${d.getMonth() + 1} 月 ${d.getDate()} 日 · 星期${wd}`
})

interface TodayEntry {
  key: string
  title: string
  location: string | null
  start: string
  end: string
  /** 分钟数（缺时间的条目为 null，排最前） */
  startMin: number | null
  state: 'past' | 'now' | 'next' | 'upcoming'
}

const entries = computed<TodayEntry[]>(() => {
  const items = schedule.today ?? []
  const nowMin = now.value.getHours() * 60 + now.value.getMinutes()
  const withMin = items.map((it, i) => {
    const s = it.start_time ? hmToMinutes(it.start_time) : null
    const e = it.end_time ? hmToMinutes(it.end_time) : null
    return {
      key: `${it.kind}-${it.event_id ?? it.task_id ?? i}`,
      title: it.title,
      location: it.location ?? null,
      start: it.start_time ?? '--:--',
      end: it.end_time ?? '',
      startMin: s,
      hasEnd: e !== null,
      startRaw: s,
    }
  })
  withMin.sort((a, b) => (a.startMin ?? -1) - (b.startMin ?? -1))
  // 状态判定：已结束 / 进行中 / 下一节（未来最早一条）/ 未开始
  let nextAssigned = false
  return withMin.map((it) => {
    if (it.startMin === null) {
      return { key: it.key, title: it.title, location: it.location, start: it.start, end: it.end, startMin: null, state: 'upcoming' as const }
    }
    const endKnown = it.hasEnd ? (hmToMinutes(it.end) ?? it.startMin) : it.startMin
    if (endKnown <= nowMin) {
      return { key: it.key, title: it.title, location: it.location, start: it.start, end: it.end, startMin: it.startMin, state: 'past' as const }
    }
    if (it.startMin <= nowMin) {
      return { key: it.key, title: it.title, location: it.location, start: it.start, end: it.end, startMin: it.startMin, state: 'now' as const }
    }
    if (!nextAssigned) {
      nextAssigned = true
      return { key: it.key, title: it.title, location: it.location, start: it.start, end: it.end, startMin: it.startMin, state: 'next' as const }
    }
    return { key: it.key, title: it.title, location: it.location, start: it.start, end: it.end, startMin: it.startMin, state: 'upcoming' as const }
  })
})

const stats = computed(() => {
  const list = entries.value
  const timed = list.filter((e) => e.startMin !== null)
  return {
    total: list.length,
    past: timed.filter((e) => e.state === 'past').length,
    nowCount: timed.filter((e) => e.state === 'now').length,
  }
})

/** 下一节（含倒计时文案） */
const nextEntry = computed(() => {
  const found = entries.value.find((e) => e.state === 'next')
  if (!found || found.startMin === null) return null
  const diff = found.startMin - (now.value.getHours() * 60 + now.value.getMinutes())
  const wait = diff > 0 ? `还有 ${Math.floor(diff / 60) > 0 ? `${Math.floor(diff / 60)} 小时 ` : ''}${diff % 60} 分钟` : ''
  return { title: found.title, start: found.start, location: found.location, wait }
})

function blockStyle(start: string, end: string): Record<string, string> | null {
  const bp = blockPercent(start, end)
  if (!bp) return null
  return { top: `${bp.top}%`, height: `${bp.height}%` }
}

function isPastBlock(end: string): boolean {
  const e = hmToMinutes(end)
  if (e === null) return false
  const nowMin = now.value.getHours() * 60 + now.value.getMinutes()
  return e <= nowMin
}

function isNowBlock(start: string, end: string): boolean {
  const s = hmToMinutes(start)
  const e = hmToMinutes(end)
  if (s === null || e === null) return false
  const nowMin = now.value.getHours() * 60 + now.value.getMinutes()
  return s <= nowMin && nowMin < e
}

const hourTicks = hourLines()

/** 当天冲突提示和空闲时段。 */

/** 警示带展开态（今日冲突项 + 近 7 日窗内未来冲突日） */
const conflictsOpen = ref(false)

/** 冲突项来源徽标：ConflictItemOut 是 event/entry/task 的字段并集，按存在字段判别。 */
function conflictKind(it: ConflictItem): string {
  if (it.event_id != null) return '日程'
  if (it.entry_id != null) return '排期'
  if (it.task_id != null) return '任务'
  return '条目'
}

/** ISO 日期 → 「9/6」式短标签（近 7 日冲突日行）。 */
function shortDate(iso: string): string {
  const [, m, d] = iso.split('-')
  return `${Number(m)}/${Number(d)}`
}

onMounted(() => {
  void schedule.loadToday()
})
</script>

<template>
  <section class="today-view">
    <!-- 左：「现在」面板 + 统计 -->
    <aside class="tv-side">
      <div class="now-panel">
        <div class="np-kicker">Now · 现在时刻</div>
        <div class="np-clock">{{ clockText }}</div>
        <div class="np-date">{{ longDate }}</div>
        <div v-if="nextEntry" class="np-next">
          <span class="nx-label">下一节</span>
          <span class="nx-title">{{ nextEntry.title }}</span>
          <span class="nx-meta">{{ nextEntry.start }}<template v-if="nextEntry.location"> · {{ nextEntry.location }}</template></span>
          <span v-if="nextEntry.wait" class="nx-wait">{{ nextEntry.wait }}</span>
        </div>
        <div v-else class="np-next np-free">今天再无后续安排</div>
      </div>

      <!-- 冲突警示带（--terra 系 token）：首载检查中 / 检查失败 / 有冲突；无冲突不渲染 -->
      <div v-if="schedule.conflictsError" class="cf-band" data-state="error">
        <div class="cf-headline">冲突检查失败</div>
        <div class="cf-err">{{ schedule.conflictsError }}</div>
        <button class="retry" @click="schedule.loadConflicts()">重试</button>
      </div>
      <div v-else-if="schedule.loadingConflicts && schedule.conflicts === null" class="cf-band" data-state="loading">
        <div class="cf-headline">正在检查日程冲突…</div>
      </div>
      <div v-else-if="schedule.todayConflicts.length > 0" class="cf-band" data-state="conflict">
        <button class="cf-head" @click="conflictsOpen = !conflictsOpen">
          <span class="cf-headline">今天有 {{ schedule.todayConflicts.length }} 组日程时间冲突</span>
          <span class="cf-toggle">{{ conflictsOpen ? '收起' : '展开' }}</span>
        </button>
        <template v-if="conflictsOpen">
          <div class="cf-list">
            <div v-for="(it, i) in schedule.todayConflicts" :key="`${it.event_id ?? it.entry_id ?? it.task_id ?? 'x'}-${i}`" class="cf-item">
              <span class="cf-time">{{ it.start_time ?? '--:--' }}–{{ it.end_time ?? '--:--' }}</span>
              <span class="cf-kind">{{ conflictKind(it) }}</span>
              <span class="cf-title">{{ it.title }}</span>
            </div>
          </div>
          <div v-if="schedule.upcomingConflictDays.length > 0" class="cf-upcoming">
            <div class="cf-up-label">近 7 日还有</div>
            <div v-for="d in schedule.upcomingConflictDays" :key="d.date" class="cf-item">
              <span class="cf-time">{{ shortDate(d.date) }}</span>
              <span class="cf-title">{{ d.items.map((it) => it.title).join('、') }}</span>
            </div>
          </div>
        </template>
      </div>

      <div class="tv-stats">
        <div class="st-row">
          <span class="st-num">{{ stats.total }}</span>
          <span class="st-lbl">今日日程</span>
        </div>
        <div class="st-row">
          <span class="st-num" :data-tone="stats.nowCount > 0 ? 'amber' : ''">{{ stats.nowCount }}</span>
          <span class="st-lbl">进行中</span>
        </div>
        <div class="st-row">
          <span class="st-num">{{ stats.past }}</span>
          <span class="st-lbl">已结束</span>
        </div>
      </div>

      <!-- 今日空闲（free-slots ≥30 分钟整段空档）：计算中 / 失败 / 空 / 有时段，四态齐全 -->
      <div class="tv-free">
        <div class="tf-kicker">Free · 今日空闲</div>
        <div v-if="schedule.loadingFreeSlots && schedule.freeSlots === null" class="tf-line">
          正在计算今日空闲…
        </div>
        <template v-else-if="schedule.freeSlotsError">
          <div class="tf-line" data-tone="error">{{ schedule.freeSlotsError }}</div>
          <button class="retry" @click="schedule.loadFreeSlots()">重试</button>
        </template>
        <div v-else-if="schedule.freeSlots !== null && schedule.freeSlots.length > 0" class="tf-slots">
          <div v-for="(s, i) in schedule.freeSlots" :key="`${s.start}-${i}`" class="tf-slot">
            <span class="tfs-time">{{ s.start }}–{{ s.end }}</span>
            <span class="tfs-min">{{ s.minutes }} 分钟</span>
          </div>
        </div>
        <div v-else class="tf-line">今日无整段空闲（≥30 分钟）</div>
      </div>

      <div class="tv-foot">
        <template v-if="schedule.loadingToday">正在拉取今日日程…</template>
        <template v-else-if="schedule.lastRefreshedAt">数据已就绪 · AI 写操作后自动刷新</template>
      </div>

      <div v-if="schedule.error" class="tv-error">
        <span>{{ schedule.error }}</span>
        <button class="retry" @click="schedule.loadToday()">重试</button>
      </div>
    </aside>

    <!-- 右：当日时间轴 -->
    <div class="tv-main">
      <div class="tv-axis">
        <div class="gutter">
          <span v-for="t in hourTicks" :key="t.hm" :style="{ top: `${t.pct}%` }">{{ t.hm }}</span>
        </div>
        <div class="col" :data-empty="entries.length === 0">
          <!-- 日程块 -->
          <template v-for="e in entries" :key="e.key">
            <div
              v-if="blockStyle(e.start, e.end)"
              class="ev"
              :style="blockStyle(e.start, e.end)!"
              :data-state="isNowBlock(e.start, e.end) ? 'now' : isPastBlock(e.end) ? 'past' : 'todo'"
            >
              <div class="ev-title">{{ e.title }}</div>
              <div v-if="e.location" class="ev-room">{{ e.location }}</div>
              <div class="ev-time">{{ e.start }}–{{ e.end }}</div>
              <span v-if="isNowBlock(e.start, e.end)" class="ev-live">进行中</span>
            </div>
          </template>

          <!-- 现在指示线（轴内实时定位；轴外钳制到轴端，深宵不消失） -->
          <div
            v-if="nowPct !== null"
            class="nowline"
            :style="{ top: `${nowPct}%` }"
            :data-clamped="nowPctRaw === null ? '' : null"
          >
            <span class="nl-dot" />
            <span class="nl-label">{{ clockText }}</span>
          </div>

          <!-- 空态 -->
          <div v-if="!schedule.loadingToday && entries.length === 0" class="tv-empty">
            <div class="te-mark">今日无日程</div>
            <p class="te-line">课表与安排在这里落位。对左侧的知时说一句话，</p>
            <p class="te-line">就能把今天安排上 —— 写操作会先请你批准。</p>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.today-view {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 0;
}

/* ---- 左栏 ---- */
.tv-side {
  width: 288px;
  flex: none;
  padding: 22px 18px 18px 22px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  border-right: 1px solid var(--line);
  min-height: 0;
  overflow-y: auto;
}
.now-panel {
  background: var(--bg-raise);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-m);
  padding: 16px 16px 14px;
}
.np-kicker {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ink-3);
  margin-bottom: 10px;
}
.np-clock {
  font-family: var(--serif);
  font-size: 44px;
  font-weight: 600;
  line-height: 1;
  letter-spacing: 0.02em;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
}
.np-date {
  margin-top: 8px;
  font-size: 12.5px;
  color: var(--ink-2);
  letter-spacing: 0.04em;
}
.np-next {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.np-free {
  font-size: 12.5px;
  color: var(--ink-3);
  font-style: italic;
}
.nx-label {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.14em;
  color: var(--amber-dim);
}
.nx-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--ink);
  line-height: 1.4;
}
.nx-meta {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ink-3);
}
.nx-wait {
  font-size: 12px;
  color: var(--amber-soft);
}

.tv-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  overflow: hidden;
}
.st-row {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 12px 4px 10px;
  background: var(--bg-sink);
}
.st-row + .st-row {
  border-left: 1px solid var(--line);
}
.st-num {
  font-family: var(--serif);
  font-size: 22px;
  font-weight: 600;
  line-height: 1;
  color: var(--ink-2);
  font-variant-numeric: tabular-nums;
}
.st-num[data-tone='amber'] {
  color: var(--amber-soft);
}
.st-lbl {
  font-size: 11.5px;
  color: var(--ink-3);
  letter-spacing: 0.08em;
}

.tv-foot {
  font-size: 11.5px;
  color: var(--ink-3);
  letter-spacing: 0.02em;
}
.tv-error {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 12.5px;
  color: var(--terra-soft);
  border: 1px dashed var(--terra-dashed);
  border-radius: var(--radius-s);
  padding: 10px 12px;
}
.retry {
  align-self: flex-start;
  font-size: 12px;
  color: var(--amber-soft);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-s);
  padding: 3px 10px;
}
.retry:hover {
  border-color: var(--line-hover);
}

/* ---- 冲突警示带（--terra 系 token；「现在」卡下方的软性提醒） ---- */
.cf-band {
  display: flex;
  flex-direction: column;
  gap: 5px;
  border: 1px dashed var(--terra-dashed);
  border-radius: var(--radius-m);
  padding: 10px 12px;
  color: var(--terra-soft);
  font-size: 12.5px;
}
.cf-band[data-state='loading'] {
  border-color: var(--line);
  color: var(--ink-3);
}
.cf-band[data-state='error'] .cf-headline,
.cf-band[data-state='conflict'] .cf-headline {
  color: var(--terra-soft);
}
.cf-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  width: 100%;
  text-align: left;
}
.cf-headline {
  font-weight: 600;
  letter-spacing: 0.02em;
}
.cf-toggle {
  margin-left: auto;
  font-size: 11px;
  color: var(--ink-3);
}
.cf-toggle:hover {
  color: var(--ink-2);
}
.cf-err {
  font-size: 12px;
  color: var(--ink-3);
}
.cf-list {
  margin-top: 4px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.cf-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}
.cf-time {
  flex: none;
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--terra-soft);
  font-variant-numeric: tabular-nums;
}
.cf-kind {
  flex: none;
  font-size: 10.5px;
  line-height: 1.6;
  color: var(--ink-3);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-pill);
  padding: 0 7px;
}
.cf-title {
  color: var(--ink-2);
  font-size: 12.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cf-upcoming {
  margin-top: 6px;
  padding-top: 8px;
  border-top: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.cf-up-label {
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.14em;
  color: var(--ink-3);
}

/* ---- 今日空闲（free-slots 空档段） ---- */
.tv-free {
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: var(--bg-sink);
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  padding: 12px 14px;
}
.tf-kicker {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.tf-slots {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.tf-slot {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.tfs-time {
  font-family: var(--mono);
  font-size: 12.5px;
  color: var(--ink-2);
  font-variant-numeric: tabular-nums;
}
.tfs-min {
  font-size: 11.5px;
  color: var(--ink-3);
}
.tf-line {
  font-size: 12.5px;
  font-style: italic;
  color: var(--ink-3);
}
.tf-line[data-tone='error'] {
  font-style: normal;
  color: var(--terra-soft);
}

/* ---- 右栏：当日时间轴（与纸质周历同轴 08:00–21:00） ---- */
.tv-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  padding: 18px 20px 18px;
  overflow: auto;
}
.tv-axis {
  height: 100%;
  min-height: 560px;
  display: grid;
  grid-template-columns: 42px 1fr;
}
.gutter {
  position: relative;
}
.gutter span {
  position: absolute;
  right: 8px;
  transform: translateY(-6px);
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ink-3);
}
.col {
  position: relative;
  border-left: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  background-image: linear-gradient(to bottom, var(--line) 0 1px, transparent 1px);
  background-size: 100% calc(100% / 13);
  min-height: 0;
}

.ev {
  position: absolute;
  left: 12px;
  right: 16px;
  background: var(--bg-raise);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-s);
  padding: 7px 11px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.ev[data-state='past'] {
  opacity: 0.5;
}
.ev[data-state='now'] {
  border-color: var(--amber-dim);
  box-shadow: var(--shadow-now);
}
.ev-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink);
  line-height: 1.3;
}
.ev-room {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--amber-dim);
  letter-spacing: 0.02em;
}
.ev-time {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ink-3);
}
.ev-live {
  position: absolute;
  right: 9px;
  top: 8px;
  font-size: 11px;
  font-weight: 600;
  color: var(--amber-soft);
  border: 1px solid var(--amber-border);
  border-radius: var(--radius-pill);
  padding: 1px 8px;
}

.nowline {
  position: absolute;
  left: 0;
  right: 0;
  height: 0;
  border-top: 1.5px solid var(--amber);
  z-index: 3;
}
.nl-dot {
  position: absolute;
  left: -4px;
  top: -4.5px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--amber);
  box-shadow: 0 0 0 3px var(--amber-ring);
}
.nl-label {
  position: absolute;
  right: 6px;
  top: -10px;
  font-family: var(--mono);
  font-size: 10.5px;
  font-weight: 600;
  color: var(--btn-ok-text);
  background: var(--amber);
  border-radius: 3px;
  padding: 1px 6px;
  line-height: 1.4;
}
.nowline[data-clamped] {
  border-top-style: dashed;
  opacity: 0.75;
}

.tv-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  text-align: center;
  padding: 0 40px;
}
.te-mark {
  font-family: var(--serif);
  font-size: 24px;
  font-weight: 600;
  letter-spacing: 0.14em;
  color: var(--ink-2);
  margin-bottom: 8px;
}
.te-line {
  font-size: 13px;
  color: var(--ink-3);
  line-height: 1.8;
}
</style>
