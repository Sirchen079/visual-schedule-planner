<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import draggable from 'vuedraggable'
import TaskCard from '../components/TaskCard.vue'
import ArtIcon from '../components/ArtIcon.vue'

const props = defineProps({
  tasks: { type: Array, required: true },
})
const emit = defineEmits(['open', 'update-status', 'create'])

const COLUMNS = ['待办', '进行中', '完成']
const lists = ref({ 待办: [], 进行中: [], 完成: [] })

// 搜索 / 筛选 / 排序（记忆上次选择）
const search = ref(localStorage.getItem('board_search') || '')
const filterPriority = ref(localStorage.getItem('board_fp') || '')
const filterTag = ref(localStorage.getItem('board_ft') || '')
const sortBy = ref(localStorage.getItem('board_sort') || 'created')
const searchInput = ref(null)

const PRI_WEIGHT = { 高: 0, 中: 1, 低: 2 }

const allTags = computed(() => {
  const map = new Map()
  for (const t of props.tasks) {
    for (const tg of t.tags || []) map.set(tg.name, tg)
  }
  return Array.from(map.values())
})

const filtered = computed(() => {
  let arr = props.tasks.slice()
  const q = search.value.trim().toLowerCase()
  if (q) {
    arr = arr.filter(
      (t) =>
        (t.title || '').toLowerCase().includes(q) ||
        (t.notes || '').toLowerCase().includes(q)
    )
  }
  if (filterPriority.value) arr = arr.filter((t) => t.priority === filterPriority.value)
  if (filterTag.value) {
    arr = arr.filter((t) => (t.tags || []).some((tg) => tg.name === filterTag.value))
  }
  if (sortBy.value === 'due') {
    arr.sort((a, b) => {
      if (!a.due_date) return 1
      if (!b.due_date) return -1
      return new Date(a.due_date) - new Date(b.due_date)
    })
  } else if (sortBy.value === 'priority') {
    arr.sort((a, b) => (PRI_WEIGHT[a.priority] ?? 9) - (PRI_WEIGHT[b.priority] ?? 9))
  } else {
    arr.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
  }
  return arr
})

function rebuild() {
  lists.value = { 待办: [], 进行中: [], 完成: [] }
  for (const t of filtered.value) {
    const col = lists.value[t.status]
    if (col) col.push(t)
  }
}
watch(filtered, rebuild, { immediate: true })

watch([search, filterPriority, filterTag, sortBy], () => {
  localStorage.setItem('board_search', search.value)
  localStorage.setItem('board_fp', filterPriority.value)
  localStorage.setItem('board_ft', filterTag.value)
  localStorage.setItem('board_sort', sortBy.value)
})

function focusSearch() {
  searchInput.value?.focus()
}

// 键盘快捷键：/ 聚焦搜索、N 新建（在输入框内不触发）
function onKey(e) {
  const tag = (document.activeElement && document.activeElement.tagName) || ''
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
  if (e.key === '/') {
    e.preventDefault()
    focusSearch()
  } else if (e.key === 'n' || e.key === 'N') {
    e.preventDefault()
    emit('create')
  }
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))

function onEnd(evt, targetStatus) {
  const item = lists.value[targetStatus]?.[evt.newIndex]
  if (item && item.status !== targetStatus) {
    emit('update-status', item, targetStatus)
  }
}

const columnMeta = {
  待办: {
    hint: '暂无待办任务',
    tone: 'todo',
    accent: 'var(--info)',
  },
  进行中: {
    hint: '正在推进的任务会显示在这里',
    tone: 'doing',
    accent: 'var(--accent)',
  },
  完成: {
    hint: '完成后的任务会归到这里',
    tone: 'done',
    accent: 'var(--success)',
  },
}

const boardMetrics = computed(() => [
  { label: '全部任务', value: props.tasks.length, icon: 'board', tone: 'aqua' },
  { label: COLUMNS[0], value: lists.value[COLUMNS[0]]?.length || 0, icon: 'task', tone: 'coral' },
  { label: COLUMNS[1], value: lists.value[COLUMNS[1]]?.length || 0, icon: 'timeline', tone: 'sand' },
  { label: COLUMNS[2], value: lists.value[COLUMNS[2]]?.length || 0, icon: 'overview', tone: 'mint' },
])

const visibleTags = computed(() => allTags.value.slice(0, 7))
</script>

<template>
  <div class="board workspace-page">
    <div class="board-head">
      <div class="board-title">
        <h2 class="page-title">
          <ArtIcon name="board" tone="aqua" :size="44" tile label="任务看板" />
          <span>任务看板</span>
        </h2>
        <p class="muted">像潮汐一样把任务归位，保持推进节奏清晰。</p>
      </div>
      <button class="create-btn" @click="emit('create')">
        <ArtIcon name="plus" tone="on-accent" :size="20" />
        <span>新建任务</span>
      </button>
    </div>

    <div class="board-toolbar">
      <div class="ctl">
        <ArtIcon class="ctl-icon" name="search" tone="aqua" :size="18" />
        <input ref="searchInput" v-model="search" placeholder="搜索标题或备注…" />
      </div>
      <span class="tb-divider"></span>
      <div class="ctl">
        <ArtIcon class="ctl-icon" name="priority" tone="coral" :size="18" />
        <select v-model="filterPriority">
          <option value="">全部优先级</option>
          <option value="高">高</option>
          <option value="中">中</option>
          <option value="低">低</option>
        </select>
      </div>
      <div class="ctl">
        <ArtIcon class="ctl-icon" name="tag" tone="mint" :size="18" />
        <select v-model="filterTag">
          <option value="">全部标签</option>
          <option v-for="t in allTags" :key="t.name" :value="t.name">{{ t.name }}</option>
        </select>
      </div>
      <div class="ctl">
        <ArtIcon class="ctl-icon" name="sort" tone="sand" :size="18" />
        <select v-model="sortBy">
          <option value="created">最近创建</option>
          <option value="due">截止日期</option>
          <option value="priority">优先级</option>
        </select>
      </div>
    </div>

    <div class="board-metrics">
      <article v-for="metric in boardMetrics" :key="metric.label" class="metric-tile">
        <ArtIcon :name="metric.icon" :tone="metric.tone" :size="34" tile :label="metric.label" />
        <div>
          <strong>{{ metric.value }}</strong>
          <span>{{ metric.label }}</span>
        </div>
      </article>
    </div>

    <div class="board-workspace">
      <div class="columns">
        <div
          class="column"
          v-for="(col, index) in COLUMNS"
          :key="col"
          :class="[columnMeta[col].tone, 'animate-in']"
          :style="{ animationDelay: `${index * 0.06}s` }"
        >
          <div class="col-head">
            <div class="col-title">
              <span class="col-status" :style="{ background: columnMeta[col].accent }"></span>
              <span class="col-name">{{ col }}</span>
            </div>
            <span class="count">{{ lists[col].length }}</span>
          </div>

          <draggable
            :list="lists[col]"
            group="tasks"
            item-key="id"
            :animation="220"
            ghost-class="ghost"
            chosen-class="chosen"
            drag-class="dragging"
            class="col-body"
            :class="{ empty: !lists[col].length }"
            @end="(e) => onEnd(e, col)"
          >
            <template #item="{ element }">
              <TaskCard :task="element" @click="emit('open', element)" />
            </template>
            <template #footer>
              <div v-if="!lists[col].length" class="empty-hint muted">
                <span>{{ columnMeta[col].hint }}</span>
              </div>
            </template>
          </draggable>

          <div class="col-foot" :style="{ background: columnMeta[col].accent }"></div>
        </div>
      </div>

      <aside class="board-insight section-panel">
        <div class="insight-head">
          <ArtIcon name="sort" tone="aqua" :size="38" tile label="看板节奏" />
          <div>
            <h3>看板节奏</h3>
            <p class="muted">把筛选、标签和推进状态放在同一侧观察。</p>
          </div>
        </div>
        <div class="insight-block">
          <strong>当前排序</strong>
          <span>{{ sortBy }}</span>
        </div>
        <div class="tag-cloud" v-if="visibleTags.length">
          <span
            v-for="tag in visibleTags"
            :key="tag.name"
            class="tag-chip"
            :style="{ '--tag-color': tag.color || 'var(--accent)' }"
          >
            {{ tag.name }}
          </span>
        </div>
        <div v-else class="workspace-empty compact-empty">
          <ArtIcon name="tag" tone="mint" :size="46" tile label="标签" />
          <span>还没有标签，任务增加后这里会成为快速导航区。</span>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.board {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 16px;
  max-width: none;
  margin: 0 auto;
}

.board-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-shrink: 0;
}

.board-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  flex-shrink: 0;
  padding: 10px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-xs), var(--shadow-inset);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}

.ctl {
  position: relative;
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
}

.ctl:first-child {
  flex: 1;
  min-width: 200px;
  max-width: 320px;
}

.ctl-icon {
  position: absolute;
  left: 12px;
  pointer-events: none;
  z-index: 1;
}

.ctl input {
  width: 100%;
  padding-left: 36px;
  height: 40px;
  border-radius: var(--radius-sm);
  font-size: 13px;
}

.ctl select {
  width: auto;
  padding-left: 36px;
  padding-right: 30px;
  height: 40px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  cursor: pointer;
}

.tb-divider {
  width: 1px;
  height: 22px;
  background: var(--border-strong);
  opacity: 0.55;
  flex-shrink: 0;
}

.board-title h2 {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: 0.5px;
  white-space: nowrap;
}

.board-title p {
  margin: 6px 0 0;
  font-size: 14px;
}

.board-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  flex-shrink: 0;
}

.board-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 14px;
  flex: 1;
  min-height: 0;
}

.create-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 11px 22px;
  border-radius: var(--radius-sm);
  font-size: 14px;
  font-weight: 600;
}

.create-btn :deep(.art-icon) {
  transition: transform 0.2s ease;
}

.create-btn:hover :deep(.art-icon) {
  transform: rotate(90deg);
}

.columns {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  flex: 1;
  min-height: 0;
}

.board-insight {
  display: grid;
  gap: 14px;
  align-content: start;
  padding: 16px;
}

.insight-head {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.insight-head h3 {
  margin: 0 0 4px;
  font-size: 17px;
}

.insight-block {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-2);
}

.insight-block strong {
  color: var(--text);
}

.insight-block span {
  color: var(--text-soft);
  font-size: 12px;
  font-weight: 800;
}

.tag-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag-chip {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 10px;
  border-radius: var(--radius-pill);
  border: 1px solid color-mix(in srgb, var(--tag-color) 28%, var(--border));
  background: color-mix(in srgb, var(--tag-color) 12%, white);
  color: color-mix(in srgb, var(--tag-color) 74%, #14303f);
  font-size: 12px;
  font-weight: 800;
}

.compact-empty {
  min-height: 180px;
  gap: 10px;
  color: var(--text-soft);
  font-size: 12px;
  font-weight: 700;
}

.column {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px;
  background: linear-gradient(180deg, var(--surface), var(--surface-2));
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  box-shadow: var(--shadow-xs), var(--shadow-inset);
  position: relative;
  overflow: hidden;
}

.column::before {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 4px;
  background: var(--info);
}

.column.doing::before {
  background: var(--accent);
}

.column.done::before {
  background: var(--success);
}

.col-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  padding: 0 4px;
}

.col-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.col-status {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  box-shadow: 0 0 0 4px color-mix(in srgb, currentColor 12%, transparent);
  flex-shrink: 0;
}

.col-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
}

.count {
  background: var(--surface);
  color: var(--text-soft);
  border-radius: var(--radius-pill);
  padding: 3px 11px;
  font-size: 12px;
  font-weight: 700;
  border: 1px solid var(--border);
  box-shadow: none;
  min-width: 28px;
  text-align: center;
}

.col-body {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 80px;
  padding: 4px;
  border-radius: var(--radius-sm);
}

.col-body.empty {
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.col-body:deep(.sortable-ghost) {
  opacity: 0.35;
  background: var(--accent-soft);
  border: 2px dashed var(--accent);
  border-radius: var(--radius-sm);
}

.col-body:deep(.sortable-drag) {
  opacity: 0.96;
  box-shadow: var(--shadow-lg);
}

.empty-hint {
  text-align: center;
  padding: 32px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  opacity: 0.75;
}

.col-foot {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 4px;
  opacity: 0.6;
  border-radius: 0 0 var(--radius) var(--radius);
}

@media (max-width: 960px) {
  .board-workspace {
    grid-template-columns: 1fr;
  }

  .board-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .columns {
    grid-template-columns: 1fr;
    grid-auto-rows: minmax(200px, 1fr);
  }
}

@media (max-width: 640px) {
  .board-toolbar {
    gap: 12px;
  }
  .tb-divider {
    display: none;
  }
  .ctl:first-child {
    max-width: none;
  }
  .board-head {
    align-items: center;
  }
  .board-metrics {
    grid-template-columns: 1fr;
  }
  .board-title p {
    display: none;
  }
}
</style>
