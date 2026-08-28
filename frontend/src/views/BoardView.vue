<script setup>
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import draggable from 'vuedraggable'
import TaskCard from '../components/TaskCard.vue'
import ArtIcon from '../components/ArtIcon.vue'
import PageHeader from '../components/ui/PageHeader.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import { getDueReminders } from '../api/reminders'
import { updateTask } from '../api/tasks'
import { useWarmGreeting } from '../composables/useWarmGreeting'
import { useOnboarding } from '../composables/useOnboarding'
import { formatQuickHint, parseQuickInput } from '../utils/quickparse'

const props = defineProps({
  tasks: { type: Array, required: true },
})
const emit = defineEmits(['open', 'update-status', 'create', 'quick-create'])
const toast = inject('toast', { success: () => {}, error: () => {}, info: () => {}, undo: () => {} })
const { onboardingDone } = useOnboarding()

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
    // 默认与后端列表序一致：sort_order 升序，再按创建时间倒序（列内手动排序在此基础上生效）
    arr.sort((a, b) => {
      const diff = orderOf(a) - orderOf(b)
      return diff !== 0 ? diff : new Date(b.created_at) - new Date(a.created_at)
    })
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
onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
  clearDragMarks()
})

// 拖拽：跨列移动改状态；同列在「默认排序」下可排序并持久化 sort_order。
// 其他排序（截止/优先级）下列显示顺序与 sort_order 无关，同列拖了也留不住位置，仍禁止以免误导。
// 拖动过程中高亮可投放的目标列，不可投放时给出 not-allowed 光标反馈。
const SORT_EPS = 1e-6 // 相邻 sort_order 差值小于该阈值视为过近，触发整列一次性规整

function orderOf(t) {
  return typeof t?.sort_order === 'number' ? t.sort_order : 0
}

function onMove(evt) {
  const crossColumn = evt.from !== evt.to
  const canDrop = crossColumn || sortBy.value === 'created'
  document
    .querySelectorAll('.col-body.drop-target')
    .forEach((el) => el.classList.remove('drop-target'))
  if (crossColumn && evt.to) evt.to.classList.add('drop-target')
  document.body.classList.toggle('drag-no-drop', !canDrop)
  return canDrop
}

function clearDragMarks() {
  document
    .querySelectorAll('.col-body.drop-target')
    .forEach((el) => el.classList.remove('drop-target'))
  document.body.classList.remove('drag-no-drop')
}

async function onEnd(evt, targetStatus) {
  clearDragMarks()
  const arr = lists.value[targetStatus]
  const item = arr?.[evt.newIndex]
  if (!item) return
  if (evt.from !== evt.to) {
    // 跨列移动：先按落点写入 sort_order，成功后再改状态（避免状态响应带回旧值覆盖本地顺序）
    if (item.status !== targetStatus) {
      const placed = await placeSortOrder(arr, evt.newIndex, item)
      if (placed) emit('update-status', item, targetStatus)
    }
    return
  }
  // 同列排序：默认排序下已被 onMove 放行；位置没变则不产生请求
  if (evt.oldIndex !== evt.newIndex) await placeSortOrder(arr, evt.newIndex, item)
}

// 按落点计算并持久化 sort_order：两张卡之间取均值、列首取最小值-1、列尾取最大值+1。
// 本地乐观更新立即生效；失败 toast 并通知主界面刷新回退。
async function placeSortOrder(arr, index, item) {
  const prev = arr[index - 1]
  const next = arr[index + 1]
  try {
    if (prev && next) {
      const lo = orderOf(prev)
      const hi = orderOf(next)
      // 相邻值相等或过近：按当前顺序把整列一次性规整为 1..n（仅此时才规整，克制）
      if (hi - lo < SORT_EPS) return await normalizeColumn(arr)
      return await applySortOrder(item, (lo + hi) / 2)
    }
    if (prev) return await applySortOrder(item, orderOf(prev) + 1)
    if (next) return await applySortOrder(item, orderOf(next) - 1)
    return true // 列内仅此一张卡，无需调整
  } catch {
    toast.error('排序保存失败，已恢复')
    window.dispatchEvent(new Event('tasks:refresh'))
    return false
  }
}

async function applySortOrder(item, value) {
  item.sort_order = value // 乐观更新：本地顺序立即生效
  await updateTask(item.id, { sort_order: value })
  return true
}

async function normalizeColumn(arr) {
  arr.forEach((t, i) => {
    t.sort_order = i + 1
  })
  for (const t of arr) await updateTask(t.id, { sort_order: t.sort_order })
  return true
}

// 排序键 → 中文文案（与工具栏下拉选项一致）
const SORT_LABELS = { created: '默认排序', due: '截止日期', priority: '优先级' }
const sortLabel = computed(() => SORT_LABELS[sortBy.value] || SORT_LABELS.created)

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

// 暖心提醒：时间问候 + 任务安排 + 连续使用时长，右侧栏顶部展示
const { warm } = useWarmGreeting(() => props.tasks)

// 右侧栏快速新建：回车即建到目标列（默认待办，列头 + 号可切换目标列并聚焦）
// 标题支持自然语言语法（明天/下午3点/!高/#标签），输入时实时显示解析提示
const quickTitle = ref('')
const quickStatus = ref('待办')
const quickInput = ref(null)
const quickHints = computed(() => {
  const text = quickTitle.value.trim()
  return text ? formatQuickHint(parseQuickInput(text)) : []
})
function focusQuick(status) {
  quickStatus.value = status
  quickInput.value?.focus()
}

// 整板空态 overlay 只在「新手引导未完成」时出现；引导结束（onboarding_done=1）后
// 永远展示基本界面（空列 + 列底快速新建），即使任务列表为空也不再叠加引导层。
const boardEmpty = computed(() => !props.tasks.length && !onboardingDone.value)

// 空状态引导的次按钮：把自然语言示例填入快速新建框并聚焦，回车即可体验解析
function tryQuickCreate() {
  quickStatus.value = '待办'
  quickTitle.value = '明天下午3点写周报 #工作 !高'
  quickInput.value?.focus()
}
function quickAdd() {
  const text = quickTitle.value.trim()
  if (!text) return
  const parsed = parseQuickInput(text)
  const payload = { title: parsed.title, status: quickStatus.value }
  // 日期序列化与 TaskForm 保持一致：整天对齐到 23:59:59
  if (parsed.due_date) payload.due_date = `${parsed.due_date}T23:59:59`
  if (parsed.due_time) payload.due_time = parsed.due_time
  if (parsed.priority) payload.priority = parsed.priority
  if (parsed.tags.length) payload.tags = parsed.tags
  emit('quick-create', payload)
  quickTitle.value = ''
}

// 临期/逾期任务（与提醒同源：24h 内到期 + 已逾期），点击直接打开编辑
const dueSoon = ref({ upcoming: [], overdue: [] })
async function loadDueSoon() {
  try {
    dueSoon.value = await getDueReminders(24)
  } catch {
    // 提醒接口不可用时静默降级，右侧栏仅不展示该块
  }
}
onMounted(loadDueSoon)
watch(() => props.tasks, loadDueSoon)
const dueItems = computed(() =>
  [
    ...dueSoon.value.overdue.map((t) => ({ ...t, _overdue: true })),
    ...dueSoon.value.upcoming,
  ].slice(0, 6)
)
function fmtDue(d) {
  if (!d) return ''
  return new Date(d).toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<template>
  <div class="board workspace-page">
    <PageHeader
      icon="board"
      title="任务看板"
      subtitle="像潮汐一样把任务归位，保持推进节奏清晰。"
    >
      <template #actions>
        <button class="create-btn" @click="emit('create')">
          <ArtIcon name="plus" tone="on-accent" :size="20" />
          <span>新建任务</span>
        </button>
      </template>
    </PageHeader>

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
          <option value="created">默认排序</option>
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
      <div class="columns" :class="{ 'all-empty': boardEmpty }">
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
            <button
              class="col-add"
              :title="`快速新建到「${col}」`"
              :aria-label="`快速新建到${col}`"
              @click="focusQuick(col)"
            >
              <ArtIcon name="plus" tone="pearl" :size="13" />
            </button>
          </div>

          <draggable
            :list="lists[col]"
            group="tasks"
            item-key="id"
            :animation="220"
            :move="onMove"
            ghost-class="ghost"
            chosen-class="chosen"
            drag-class="dragging"
            class="col-body"
            :class="{ empty: !lists[col].length }"
            @end="(e) => onEnd(e, col)"
          >
            <template #item="{ element }">
              <TaskCard
                :task="element"
                @click="emit('open', element)"
                @quick-status="(t, s) => emit('update-status', t, s)"
              />
            </template>
            <template #footer>
              <div v-if="!lists[col].length" key="empty-hint" class="empty-hint muted">
                <span>{{ columnMeta[col].hint }}</span>
                <button class="empty-add" @click="focusQuick(col)">＋ 快速新建</button>
              </div>
            </template>
          </draggable>

          <div class="col-foot" :style="{ background: columnMeta[col].accent }"></div>
        </div>

        <!-- 整板空状态：叠加在列区域上方的新手引导，列结构保留在底层 -->
        <div v-if="boardEmpty" class="board-empty-overlay">
          <EmptyState
            icon="board"
            title="从第一件事开始"
            hint="知时支持自然语言创建：时间、优先级、标签写在标题里就能自动识别。"
          >
            <button type="button" @click="emit('create')">创建第一个任务</button>
            <button class="ghost" type="button" @click="tryQuickCreate">试试自然语言创建</button>
          </EmptyState>
        </div>
      </div>

      <div class="board-side">
        <section class="warmth-panel section-panel" :class="`mood-${warm.mood}`">
          <ArtIcon :name="warm.icon" :tone="warm.tone" :size="34" tile :label="warm.title" />
          <div class="warmth-text">
            <strong>{{ warm.title }}</strong>
            <p v-for="(line, i) in warm.lines" :key="i">{{ line }}</p>
          </div>
        </section>

        <aside class="board-insight section-panel">
          <div class="insight-head">
            <ArtIcon name="sort" tone="aqua" :size="38" tile label="看板节奏" />
            <div>
              <h3>看板节奏</h3>
              <p class="muted">快速新建、临期任务与标签导航放在手边。</p>
            </div>
          </div>

          <div class="quick-add">
            <input
              ref="quickInput"
              v-model="quickTitle"
              placeholder="快速新建，回车创建"
              @keydown.enter.prevent="quickAdd"
            />
            <select v-model="quickStatus" title="新建到哪一列" aria-label="新建到哪一列">
              <option v-for="col in COLUMNS" :key="col" :value="col">{{ col }}</option>
            </select>
          </div>
          <div v-if="quickHints.length" class="quick-hints">
            <span v-for="hint in quickHints" :key="hint" class="quick-hint">{{ hint }}</span>
          </div>

          <div class="due-block" v-if="dueItems.length">
            <p class="due-title muted">临期任务 · {{ dueItems.length }}</p>
            <button
              v-for="t in dueItems"
              :key="t.id"
              class="due-item"
              :class="{ overdue: t._overdue }"
              :title="t.title"
              @click="emit('open', t)"
            >
              <span class="due-dot"></span>
              <span class="due-name">{{ t.title }}</span>
              <span class="due-date">{{ t._overdue ? '已逾期' : fmtDue(t.due_date) }}</span>
            </button>
          </div>

          <div class="insight-block">
            <strong>当前排序</strong>
            <span>{{ sortLabel }}</span>
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

/* PageHeader 自带 margin-bottom，这里交给 .board 的 gap 统一节奏 */
.board :deep(.page-header) {
  margin-bottom: 0;
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
  position: relative;
}

/* 整板空状态覆盖层：半透明虚化底层空列，居中承载引导卡 */
.board-empty-overlay {
  position: absolute;
  inset: 0;
  z-index: 6;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  border-radius: var(--radius);
  background: color-mix(in srgb, var(--surface) 66%, transparent);
  backdrop-filter: blur(5px);
  -webkit-backdrop-filter: blur(5px);
}

.board-empty-overlay :deep(.empty-state) {
  width: min(440px, 100%);
  background: var(--surface);
  box-shadow: var(--shadow-lg);
}

.columns.all-empty .column {
  opacity: 0.55;
}

.board-insight {
  display: grid;
  gap: 14px;
  align-content: start;
  padding: 16px;
}

/* 右栏：暖心提醒独立板块 + 看板节奏 */
.board-side {
  display: grid;
  gap: 14px;
  align-content: start;
  min-width: 0;
}

/* 暖心提醒独立板块：暖色渐变 + 左侧竖条 + 图标呼吸光晕，与「看板节奏」拉开视觉层级 */
.warmth-panel {
  position: relative;
  display: flex;
  gap: 13px;
  align-items: flex-start;
  padding: 16px 18px 16px 20px;
  overflow: hidden;
  border-color: color-mix(in srgb, var(--warning) 34%, var(--border));
  background:
    radial-gradient(circle at 88% -20%, color-mix(in srgb, var(--warning) 22%, transparent), transparent 55%),
    linear-gradient(
      120deg,
      color-mix(in srgb, var(--warning) 13%, var(--surface)),
      color-mix(in srgb, var(--danger) 7%, var(--surface))
    );
  box-shadow:
    var(--shadow-sm),
    var(--shadow-inset),
    0 0 26px color-mix(in srgb, var(--warning) 13%, transparent);
  animation: warmth-in 0.5s ease both;
}

/* 左侧暖色竖条（板块的身份标识） */
.warmth-panel::after {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: linear-gradient(180deg, var(--warning), var(--danger));
}

/* 夜晚：换成静谧蓝调 */
.warmth-panel.mood-night,
.warmth-panel.mood-late {
  border-color: color-mix(in srgb, var(--accent) 36%, var(--border));
  background:
    radial-gradient(circle at 88% -20%, color-mix(in srgb, var(--accent) 20%, transparent), transparent 55%),
    linear-gradient(
      120deg,
      color-mix(in srgb, var(--accent) 11%, var(--surface)),
      color-mix(in srgb, var(--surface-3) 55%, var(--surface))
    );
  box-shadow:
    var(--shadow-sm),
    var(--shadow-inset),
    0 0 26px color-mix(in srgb, var(--accent) 14%, transparent);
}

.warmth-panel.mood-night::after,
.warmth-panel.mood-late::after {
  background: linear-gradient(180deg, var(--accent), var(--accent-strong));
}

/* 深夜：更沉、更暗，只留一点月光 */
.warmth-panel.mood-late {
  background:
    radial-gradient(circle at 15% 0%, color-mix(in srgb, var(--accent) 14%, transparent), transparent 50%),
    linear-gradient(120deg, color-mix(in srgb, var(--surface-3) 70%, var(--surface)), var(--surface));
  box-shadow: var(--shadow-xs), var(--shadow-inset);
}

/* 图标呼吸光晕，让板块"活"起来但不吵 */
.warmth-panel :deep(.art-icon.tile) {
  animation: warmth-breathe 3.2s ease-in-out infinite;
}

@keyframes warmth-in {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

@keyframes warmth-breathe {
  0%,
  100% {
    box-shadow: var(--shadow-xs), var(--shadow-inset), 0 0 8px var(--icon-glow);
  }
  50% {
    box-shadow: var(--shadow-xs), var(--shadow-inset), 0 0 22px var(--icon-glow);
  }
}

.warmth-text {
  min-width: 0;
  display: grid;
  gap: 5px;
}

.warmth-text strong {
  color: var(--text);
  font-size: 16px;
  font-weight: 800;
}

.warmth-text p {
  margin: 0;
  color: var(--text-soft);
  font-size: 12.5px;
  line-height: 1.6;
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
  background: color-mix(in srgb, var(--tag-color) 12%, var(--surface-solid));
  color: color-mix(in srgb, var(--tag-color) 70%, var(--text));
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
  margin-left: auto;
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

/* 列头快速新建：平时收起，悬停列时浮现，保持表头干净 */
.col-add {
  width: 26px;
  height: 26px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  color: var(--text-muted);
  border-radius: 8px;
  box-shadow: none;
  opacity: 0;
  transition: opacity 0.15s ease, background 0.15s ease, color 0.15s ease;
}

.column:hover .col-add,
.col-add:focus-visible {
  opacity: 1;
}

.col-add:hover {
  background: var(--accent-soft);
  color: var(--accent-strong);
}

/* 右侧栏：快速新建（回车创建到目标列） */
.quick-add {
  display: flex;
  gap: 8px;
}

.quick-add input {
  flex: 1;
  min-width: 0;
  height: 38px;
  font-size: 13px;
}

.quick-add select {
  width: 82px;
  height: 38px;
  padding: 0 8px;
  font-size: 12px;
  cursor: pointer;
}

/* 快速新建的解析提示 chips */
.quick-hints {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.quick-hint {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 9px;
  border-radius: var(--radius-pill);
  background: var(--accent-soft);
  color: var(--accent-strong);
  font-size: 11px;
  font-weight: 700;
}

/* 右侧栏：临期/逾期任务块 */
.due-block {
  display: grid;
  gap: 6px;
}

.due-title {
  margin: 0;
  font-size: 12px;
  font-weight: 700;
}

.due-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: var(--radius-xs);
  background: var(--surface-2);
  border: 1px solid var(--border);
  color: var(--text);
  font-size: 13px;
  font-weight: 600;
  text-align: left;
  box-shadow: none;
}

.due-item:hover {
  background: var(--accent-soft);
  border-color: var(--border-strong);
  box-shadow: none;
}

.due-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--warning);
  flex-shrink: 0;
}

.due-item.overdue .due-dot {
  background: var(--danger);
}

.due-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.due-date {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 700;
  color: var(--text-muted);
}

.due-item.overdue .due-date {
  color: var(--danger);
}

/* 空列快捷入口 */
.empty-add {
  background: transparent;
  color: var(--accent);
  border: 1px dashed var(--border-strong);
  padding: 6px 14px;
  font-size: 12px;
  box-shadow: none;
}

.empty-add:hover {
  background: var(--accent-soft);
  color: var(--accent-strong);
  border-color: var(--accent);
  box-shadow: none;
}

.col-body {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 80px;
  padding: 4px;
  border-radius: var(--radius-sm);
  outline: 2px dashed transparent;
  outline-offset: -4px;
  transition: outline-color 0.15s ease, background-color 0.15s ease;
}

/* 拖动中可投放的目标列高亮 */
.col-body.drop-target {
  outline-color: var(--accent);
  background-color: color-mix(in srgb, var(--accent) 7%, transparent);
}

.col-body.empty {
  display: flex;
  flex-direction: column;
  justify-content: center;
}

/* 与 draggable 的 ghost-class / drag-class 对应 */
.col-body:deep(.ghost) {
  opacity: 0.35;
  background: var(--accent-soft);
  border: 2px dashed var(--accent);
  border-radius: var(--radius-sm);
}

.col-body:deep(.dragging) {
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
  .board-metrics {
    grid-template-columns: 1fr;
  }
}
</style>

<style>
/* 同列禁止投放的全局光标反馈（挂在 body 上，无法 scoped） */
body.drag-no-drop,
body.drag-no-drop * {
  cursor: not-allowed !important;
}
</style>
