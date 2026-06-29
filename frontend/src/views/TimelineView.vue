<script setup>
import { computed } from 'vue'
import ArtIcon from '../components/ArtIcon.vue'

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
</script>

<template>
  <div class="timeline workspace-page">
    <div class="tl-head">
      <div class="tl-title">
        <h2 class="page-title">
          <ArtIcon name="timeline" tone="sand" :size="44" tile label="时间轴" />
          <span>时间轴</span>
        </h2>
        <p class="muted">查看任务跨度、并行关系和完成进度。</p>
      </div>
      <button class="create-btn" @click="emit('create')">
        <ArtIcon name="plus" tone="on-accent" :size="20" />
        <span>新建任务</span>
      </button>
    </div>

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

    <div v-if="!ranged.length" class="card empty">
      <div class="empty-title">还没有带起止时间的任务</div>
      <div class="muted">在任务里填写开始日期和结束日期后，这里会显示时间跨度。</div>
    </div>

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
              :title="`${t.title}（${t.priority}，进度 ${t.progress || 0}%）`"
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
  </div>
</template>

<style scoped>
.timeline {
  display: flex;
  flex-direction: column;
  gap: 18px;
  height: 100%;
  max-width: none;
  margin: 0 auto;
}

.tl-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-shrink: 0;
}

.tl-title h2 {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: 0.5px;
  white-space: nowrap;
}

.tl-title p {
  margin: 6px 0 0;
  font-size: 14px;
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
  gap: 5px;
  padding: 11px 22px;
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
  padding: 10px 14px;
  align-self: stretch;
  flex-wrap: wrap;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  font-size: 13px;
  color: var(--text-soft);
  font-weight: 500;
}

.legend-item span:last-child {
  white-space: nowrap;
}

.dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

.legend-sep {
  width: 1px;
  height: 18px;
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

.empty {
  text-align: center;
  padding: 52px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.empty-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
}

.tl-scroll {
  flex: 1;
  overflow: auto;
  padding: 14px 0;
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
  width: 170px;
  flex-shrink: 0;
  padding: 0 14px;
}

.scale {
  position: relative;
  flex: 1;
  height: 26px;
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
  top: 22px;
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
  top: 5px;
  height: 22px;
  border-radius: var(--radius-pill);
  cursor: pointer;
  display: flex;
  align-items: center;
  padding-left: 10px;
  overflow: hidden;
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
  font-size: 11px;
  color: #fff;
  font-weight: 700;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
  white-space: nowrap;
}

.unsched {
  padding: 16px 18px;
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
  gap: 6px;
  padding: 6px 13px;
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
  .tl-head {
    align-items: center;
  }
  .tl-title p {
    display: none;
  }
  .legend {
    gap: 10px 14px;
  }
  .timeline-metrics {
    grid-template-columns: 1fr;
  }
  .legend-sep {
    display: none;
  }
  .label-col {
    width: 120px;
    padding: 0 10px;
  }
  .row-sub {
    display: none;
  }
}
</style>
