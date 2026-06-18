<script setup>
import { computed } from 'vue'

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
  const end = t.due_date
    ? new Date(t.due_date)
    : t.end_date
    ? new Date(t.end_date)
    : null
  return { start, end }
}

const priColor = (p) =>
  ({ 高: 'var(--pri-high)', 中: 'var(--pri-mid)', 低: 'var(--pri-low)' })[p] || 'var(--pri-mid)'

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
    return { start: new Date(now.getFullYear(), now.getMonth(), 1), end: new Date(now.getFullYear(), now.getMonth() + 1, 0) }
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

// 范围跨度大时刻度稀疏（每 N 天一个）
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
  const width = Math.max(((end - start) / totalMs.value) * 100, 1.2)
  return { left, width }
}

function fillOf(t, p) {
  // 完成部分覆盖在横条左侧，宽度 = 横条宽 × 进度
  return p.width * ((t.progress || 0) / 100)
}

function fmt(d) {
  return `${d.getMonth() + 1}/${d.getDate()}`
}
</script>

<template>
  <div class="timeline">
    <div class="tl-head">
      <div>
        <h2 class="gradient-text">时间轴</h2>
        <p class="muted">每条横条 = 起止时间段；颜色 = 优先级；实色填充 = 完成进度。重叠即冲突。</p>
      </div>
      <button class="create-btn" @click="emit('create')"><span>＋</span> 新建任务</button>
    </div>

    <div class="legend muted">
      <span class="dot" style="background: var(--pri-high)"></span>高
      <span class="dot" style="background: var(--pri-mid)"></span>中
      <span class="dot" style="background: var(--pri-low)"></span>低
      <span class="legend-sep">·</span>
      <span>实色=已完成，半透明=未完成</span>
    </div>

    <div v-if="!ranged.length" class="card empty muted">
      还没有带起止时间的任务。在任务里填「开始日期」+「截止日期」，时间轴就能显示。
    </div>

    <div v-else class="tl-scroll">
      <div class="tl-grid" :style="{ minWidth: Math.max(totalDays * 26, 600) + 'px' }">
        <!-- 刻度 -->
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

        <!-- 任务行 -->
        <div class="row" v-for="t in ranged" :key="t.id">
          <div class="label-col">
            <div class="row-title" :title="t.title" @click="emit('open', t)">{{ t.title }}</div>
            <div class="row-sub muted">{{ t.priority }} · {{ t.progress }}%</div>
          </div>
          <div class="track">
            <div
              class="bar"
              :style="{ left: posOf(t).left + '%', width: posOf(t).width + '%', background: priColor(t.priority), opacity: 0.3 }"
              @click="emit('open', t)"
              :title="`${t.title}（${t.priority}，进度 ${t.progress}%）`"
            >
              <span class="bar-text">{{ t.progress }}%</span>
            </div>
            <div
              class="fill"
              :style="{ left: posOf(t).left + '%', width: fillOf(t, posOf(t)) + '%', background: priColor(t.priority) }"
              @click="emit('open', t)"
            >
              <span class="bar-text">{{ t.progress }}%</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <section v-if="unscheduled.length" class="unsched">
      <h3 class="muted">未排期（{{ unscheduled.length }}）</h3>
      <div class="chip-list">
        <span class="chip" v-for="t in unscheduled" :key="t.id" @click="emit('open', t)">
          <span class="dot" :style="{ background: priColor(t.priority) }"></span>{{ t.title }}
        </span>
      </div>
    </section>
  </div>
</template>

<style scoped>
.timeline {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
}
.tl-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}
h2 {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
}
p {
  margin: 6px 0 0;
  font-size: 14px;
}
.create-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 18px;
  border-radius: var(--radius-pill);
  font-weight: 600;
}
.legend {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.legend-sep {
  margin: 0 4px;
}
.empty {
  text-align: center;
  padding: 36px;
}
.tl-scroll {
  flex: 1;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  padding: 8px 0;
  box-shadow: var(--shadow-sm);
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
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}
.label-col {
  width: 160px;
  flex-shrink: 0;
  padding: 0 12px;
}
.scale {
  position: relative;
  flex: 1;
  height: 22px;
}
.tick {
  position: absolute;
  top: 0;
  transform: translateX(-50%);
  font-size: 12px;
  color: var(--text-soft);
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
  opacity: 0.5;
}
.row {
  display: flex;
  align-items: center;
  height: 46px;
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
}
.row-sub {
  font-size: 12px;
}
.track {
  position: relative;
  flex: 1;
  height: 28px;
}
.bar,
.fill {
  position: absolute;
  top: 4px;
  height: 20px;
  border-radius: 999px;
  cursor: pointer;
  display: flex;
  align-items: center;
  padding-left: 8px;
  overflow: hidden;
  transition: filter 0.2s ease;
}
.bar {
  z-index: 1;
}
.fill {
  z-index: 2;
  filter: brightness(1);
}
.bar:hover,
.fill:hover {
  filter: brightness(1.08) drop-shadow(0 2px 6px rgba(0, 0, 0, 0.15));
}
.bar-text {
  font-size: 11px;
  color: #fff;
  font-weight: 700;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
  white-space: nowrap;
}
.unsched {
  margin-top: 4px;
}
.unsched h3 {
  margin: 0 0 8px;
  font-size: 14px;
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
  padding: 5px 12px;
  border-radius: var(--radius-pill);
  background: var(--surface);
  border: 1px solid var(--border);
  font-size: 13px;
  cursor: pointer;
}
.chip:hover {
  background: var(--surface-2);
}
@media (max-width: 720px) {
  .label-col {
    width: 110px;
  }
  .row-sub {
    display: none;
  }
}
</style>
