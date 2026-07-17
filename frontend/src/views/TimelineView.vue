<script setup>
import { computed, ref } from 'vue'
import ArtIcon from '../components/ArtIcon.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import PageHeader from '../components/ui/PageHeader.vue'

const props = defineProps({
  tasks: { type: Array, required: true },
})
const emit = defineEmits(['open', 'create'])

const DAY = 86_400_000

function span(t) {
  const start = t.start_date
    ? new Date(t.start_date)
    : t.created_at
    ? new Date(t.created_at)
    : null
  const end = t.end_date
    ? new Date(t.end_date)
    : t.due_date
    ? new Date(t.due_date)
    : null
  return { start, end }
}

const priMeta = (p) =>
  ({
    高: { color: 'var(--pri-high)' },
    中: { color: 'var(--pri-mid)' },
    低: { color: 'var(--pri-low)' },
  })[p] || { color: 'var(--pri-mid)' }

const ranged = computed(() =>
  props.tasks.filter((t) => {
    const { start, end } = span(t)
    return start && end
  })
)
const unscheduled = computed(() =>
  props.tasks.filter((t) => {
    const { start, end } = span(t)
    return !(start && end)
  })
)

const range = computed(() => {
  if (!ranged.value.length) {
    const now = new Date()
    return {
      start: new Date(now.getFullYear(), now.getMonth(), 1),
      end: new Date(now.getFullYear(), now.getMonth() + 1, 0),
    }
  }
  let min = new Date(8640000000000000)
  let max = new Date(0)
  for (const t of ranged.value) {
    const { start, end } = span(t)
    if (start < min) min = start
    if (end > max) max = end
  }
  min = new Date(min.getTime() - DAY)
  max = new Date(max.getTime() + DAY)
  return { start: min, end: max }
})

const totalMs = computed(() => Math.max(range.value.end - range.value.start, DAY))
const totalDays = computed(() => Math.ceil(totalMs.value / DAY))

const tickEvery = computed(() => {
  const d = totalDays.value
  if (d <= 14) return 1
  if (d <= 35) return 2
  if (d <= 75) return 5
  return 10
})

const ticks = computed(() => {
  const every = tickEvery.value
  const arr = []
  for (let i = 0; i <= totalDays.value; i += every) {
    const d = new Date(range.value.start.getTime() + i * DAY)
    arr.push({ date: d, left: (i / totalDays.value) * 100 })
  }
  return arr
})

function posOf(t) {
  const { start, end } = span(t)
  const left = ((start - range.value.start) / totalMs.value) * 100
  const width = Math.max(((end - start) / totalMs.value) * 100, 1.4)
  return { left, width }
}

function fillOf(t, p) {
  return p.width * ((t.progress || 0) / 100)
}

function fmt(d) {
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function fmtDate(d) {
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`
}

// bar 悬浮提示：跟随鼠标的玻璃卡，pointer-events:none 不遮挡拖拽/点击
const tip = ref(null) // { title, priority, progress, startText, endText, x, y }
function showTip(e, t) {
  const { start, end } = span(t)
  tip.value = {
    title: t.title,
    priority: t.priority,
    progress: t.progress || 0,
    startText: start ? fmtDate(start) : '未定',
    endText: end ? fmtDate(end) : '未定',
    x: e.clientX,
    y: e.clientY,
  }
}
function moveTip(e) {
  if (!tip.value) return
  tip.value.x = e.clientX
  tip.value.y = e.clientY
}
function hideTip() {
  tip.value = null
}
</script>

<template>
  <div class="timeline workspace-page">
    <PageHeader
      icon="timeline"
      title="时间轴"
      subtitle="查看任务跨度、并行关系和完成进度。"
    >
      <template #actions>
        <button class="create-btn" @click="emit('create')">
          <ArtIcon name="plus" tone="on-accent" :size="20" />
          <span>新建任务</span>
        </button>
      </template>
    </PageHeader>

    <div class="timeline-metrics">
      <article class="metric-tile">
        <ArtIcon name="timeline" tone="sand" :size="34" tile label="跨度任务" />
        <div>
          <strong>{{ ranged.length }}</strong>
          <span>跨度任务</span>
        </div>
      </article>
      <article class="metric-tile">
        <ArtIcon name="task" tone="aqua" :size="34" tile label="未排期" />
        <div>
          <strong>{{ unscheduled.length }}</strong>
          <span>未排期</span>
        </div>
      </article>
      <article class="metric-tile">
        <ArtIcon name="calendar" tone="mint" :size="34" tile label="时间跨度" />
        <div>
          <strong>{{ totalDays }}</strong>
          <span>覆盖天数</span>
        </div>
      </article>
    </div>

    <div class="legend card">
      <div class="legend-item">
        <ArtIcon name="priority" tone="coral" :size="18" />
        <span>高优先级</span>
      </div>
      <div class="legend-item">
        <ArtIcon name="priority" tone="sand" :size="18" />
        <span>中优先级</span>
      </div>
      <div class="legend-item">
        <ArtIcon name="priority" tone="mint" :size="18" />
        <span>低优先级</span>
      </div>
      <div class="legend-sep"></div>
      <div class="legend-progress">
        <span class="progress-sample">
          <span class="progress-sample-fill"></span>
        </span>
        <span>浅色为跨度，深色为进度</span>
      </div>
    </div>

    <EmptyState
      v-if="!ranged.length"
      icon="timeline"
      title="还没有带起止时间的任务"
      hint="在任务里填写开始日期和结束日期后，这里会显示时间跨度。"
    />

    <div v-else class="tl-scroll card">
      <div class="tl-grid" :style="{ minWidth: Math.max(totalDays * 28, 640) + 'px' }">
        <div class="scale-row">
          <div class="label-col"></div>
          <div class="scale">
            <div
              v-for="(tk, i) in ticks"
              :key="i"
              class="tick"
              :style="{ left: tk.left + '%' }"
            >
              <span>{{ fmt(tk.date) }}</span>
            </div>
          </div>
        </div>

        <div class="row" v-for="t in ranged" :key="t.id">
          <div class="label-col">
            <div class="row-title" :title="t.title" @click="emit('open', t)">{{ t.title }}</div>
            <div class="row-sub muted">{{ t.priority }} · {{ t.progress || 0 }}%</div>
          </div>
          <div class="track">
            <div
              class="bar"
              :style="{
                left: posOf(t).left + '%',
                width: posOf(t).width + '%',
                background: priMeta(t.priority).color,
              }"
              @click="emit('open', t)"
              @mouseenter="showTip($event, t)"
              @mousemove="moveTip"
              @mouseleave="hideTip"
            >
              <span class="bar-text">{{ t.progress || 0 }}%</span>
            </div>
            <div
              class="fill"
              :style="{
                left: posOf(t).left + '%',
                width: fillOf(t, posOf(t)) + '%',
                background: priMeta(t.priority).color,
              }"
              @click="emit('open', t)"
              @mouseenter="showTip($event, t)"
              @mousemove="moveTip"
              @mouseleave="hideTip"
            >
              <span class="bar-text">{{ t.progress || 0 }}%</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <section v-if="unscheduled.length" class="unsched card">
      <h3 class="muted">未排期任务（{{ unscheduled.length }}）</h3>
      <div class="chip-list">
        <span class="chip" v-for="t in unscheduled" :key="t.id" @click="emit('open', t)">
          <span class="dot" :style="{ background: priMeta(t.priority).color }"></span>
          <span>{{ t.title }}</span>
        </span>
      </div>
    </section>

    <Teleport to="body">
      <div v-if="tip" class="tl-tip" :style="{ left: tip.x + 'px', top: tip.y + 'px' }">
        <div class="tl-tip-title">{{ tip.title }}</div>
        <div class="tl-tip-row">{{ tip.startText }} → {{ tip.endText }}</div>
        <div class="tl-tip-row">
          <span class="tl-tip-dot" :style="{ background: priMeta(tip.priority).color }"></span>
          <span>{{ tip.priority }}优先级 · 进度 {{ tip.progress }}%</span>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.timeline {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  max-width: none;
  margin: 0 auto;
}

/* PageHeader 自带 margin-bottom，与页面 flex 间距叠加拿掉 */
.timeline :deep(.page-header) {
  margin-bottom: 0;
  flex-shrink: 0;
}

.timeline-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  flex-shrink: 0;
}

.create-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 24px;
  font-size: 14px;
  font-weight: 600;
}

.create-btn :deep(.art-icon) {
  transition: transform 0.2s ease;
}

.create-btn:hover :deep(.art-icon) {
  transform: rotate(90deg);
}

.legend {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  align-self: stretch;
  flex-wrap: wrap;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  font-size: 13px;
  color: var(--text-soft);
  font-weight: 500;
}

.legend-item span:last-child {
  white-space: nowrap;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.legend-sep {
  width: 1px;
  height: 16px;
  background: var(--border);
}

.legend-progress {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--text-soft);
  font-size: 13px;
  font-weight: 500;
}

.progress-sample {
  position: relative;
  width: 52px;
  height: 8px;
  flex-shrink: 0;
  overflow: hidden;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--pri-mid) 28%, transparent);
}

.progress-sample-fill {
  position: absolute;
  inset: 0 auto 0 0;
  width: 58%;
  border-radius: inherit;
  background: var(--pri-mid);
}

.tl-scroll {
  flex: 1;
  overflow: auto;
  padding: 12px 0;
}

.tl-grid {
  display: flex;
  flex-direction: column;
}

.scale-row {
  display: flex;
  align-items: flex-end;
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--surface);
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 4px;
}

.label-col {
  width: 172px;
  flex-shrink: 0;
  padding: 0 12px;
}

.scale {
  position: relative;
  flex: 1;
  height: 24px;
}

.tick {
  position: absolute;
  top: 0;
  transform: translateX(-50%);
  font-size: 12px;
  color: var(--text-soft);
  font-weight: 600;
  white-space: nowrap;
}

.tick::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 20px;
  bottom: -100vh;
  width: 1px;
  background: var(--border);
  opacity: 0.45;
}

.row {
  display: flex;
  align-items: center;
  height: 52px;
  border-radius: var(--radius-sm);
  transition: background 0.2s ease;
}

.row:hover {
  background: var(--surface-2);
}

.row-title {
  font-weight: 600;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
  transition: color 0.15s ease;
}

.row-title:hover {
  color: var(--accent);
}

.row-sub {
  font-size: 12px;
  margin-top: 2px;
}

.track {
  position: relative;
  flex: 1;
  height: 32px;
}

.bar,
.fill {
  position: absolute;
  top: 4px;
  height: 24px;
  border-radius: var(--radius-pill);
  cursor: pointer;
  display: flex;
  align-items: center;
  padding: 0 12px;
  overflow: hidden;
  container-type: inline-size;
  transition: transform 0.2s ease, filter 0.2s ease;
}

.bar {
  z-index: 1;
  opacity: 0.28;
}

.fill {
  z-index: 2;
}

.bar:hover,
.fill:hover {
  transform: translateY(-1px);
  filter: brightness(1.05);
}

.bar-text {
  min-width: 0;
  font-size: 11px;
  color: #fff;
  font-weight: 700;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 窄条只留色块，文字交给悬浮提示 */
@container (max-width: 60px) {
  .bar-text {
    display: none;
  }
}

/* 悬浮提示卡：fixed 跟随鼠标，teleport 到 body 避免被滚动容器裁剪 */
.tl-tip {
  position: fixed;
  z-index: 100;
  transform: translate(-50%, calc(-100% - 12px));
  pointer-events: none;
  min-width: 180px;
  max-width: 260px;
  padding: 12px 16px;
  border-radius: var(--radius-md);
  background: var(--surface);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-lg), var(--shadow-inset);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}

.tl-tip-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tl-tip-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-soft);
  white-space: nowrap;
}

.tl-tip-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.unsched {
  padding: 16px 20px;
}

.unsched h3 {
  margin: 0 0 12px;
  font-size: 13px;
  font-weight: 600;
}

.chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius-pill);
  background: var(--surface-2);
  border: 1px solid var(--border);
  font-size: 13px;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.chip:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
  background: var(--surface);
}

@media (max-width: 720px) {
  .legend {
    gap: 8px 12px;
  }
  .timeline-metrics {
    grid-template-columns: 1fr;
  }
  .legend-sep {
    display: none;
  }
  .label-col {
    width: 120px;
    padding: 0 8px;
  }
  .row-sub {
    display: none;
  }
}
</style>
