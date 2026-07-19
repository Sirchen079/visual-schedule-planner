<script setup>
// 命令面板：Ctrl/Cmd+K 唤起。命令源 = 视图跳转 + 动作 + 「新建 xxx」快速建任务 + 任务搜索。
// 键盘上下导航、回车执行、Esc 关闭；过滤为大小写不敏感的包含匹配。
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import ArtIcon from './ArtIcon.vue'
import { searchTasks } from '../api/tasks'

const props = defineProps({
  open: { type: Boolean, default: false },
  tabs: { type: Array, default: () => [] }, // App.vue 导航 tabs：{ key, label, icon }
})
const emit = defineEmits([
  'close',
  'navigate',
  'open-settings',
  'toggle-theme',
  'open-task',
  'create-task',
  'quick-create',
])

const input = ref('')
const inputRef = ref(null)
const listRef = ref(null)
const activeIndex = ref(0)
const results = ref([]) // 任务搜索结果
const searching = ref(false)
let searchTimer = null
let searchSeq = 0

// 快速创建的可选解析注入点：另一个任务落地 src/utils/quickparse.js 后自动生效；
// 用 import.meta.glob 做可选加载——文件不存在时构建不报错、运行走标题兜底。
const quickParseLoaders = import.meta.glob('../utils/quickparse.js')
async function parseQuick(text) {
  try {
    const loader = quickParseLoaders['../utils/quickparse.js']
    const mod = loader ? await loader() : null
    const parsed = mod?.parseQuickInput?.(text)
    if (!parsed?.title) return { title: text }
    // 与 BoardView.quickAdd 的载荷约定一致：只带解析出的字段，日期对齐到 23:59:59
    const payload = { title: parsed.title }
    if (parsed.due_date) payload.due_date = `${parsed.due_date}T23:59:59`
    if (parsed.due_time) payload.due_time = parsed.due_time
    if (parsed.priority) payload.priority = parsed.priority
    if (parsed.tags?.length) payload.tags = parsed.tags
    return payload
  } catch {
    return { title: text }
  }
}

// 「新建 xxx」/「新建任务 xxx」：剩余文本作为任务标题快速创建
const quickCreateItem = computed(() => {
  const m = input.value.trim().match(/^新建(?:任务)?[\s　]+(.+)$/)
  const text = m?.[1]?.trim()
  if (!text) return null
  return {
    id: 'quick-create',
    group: '新建',
    icon: 'plus',
    label: `新建任务「${text}」`,
    hint: '回车快速创建',
    run: async () => emit('quick-create', await parseQuick(text)),
  }
})

const staticCommands = computed(() => [
  ...props.tabs.map((t) => ({
    id: `view-${t.key}`,
    group: '视图',
    icon: t.icon,
    label: `切换到${t.label}`,
    keywords: t.key,
    run: () => emit('navigate', t.key),
  })),
  {
    id: 'new-task',
    group: '动作',
    icon: 'plus',
    label: '新建任务',
    keywords: 'new create xinjian',
    run: () => emit('create-task'),
  },
  {
    id: 'toggle-theme',
    group: '动作',
    icon: 'moon',
    label: '切换深浅色主题',
    keywords: 'theme dark light zhuti',
    run: () => emit('toggle-theme'),
  },
  {
    id: 'gen-report',
    group: '动作',
    icon: 'archive',
    label: '生成日报',
    keywords: 'report daily ribao',
    run: () => emit('navigate', 'report'),
  },
  {
    id: 'open-settings',
    group: '动作',
    icon: 'assistant',
    label: '打开设置',
    keywords: 'settings shezhi',
    run: () => emit('open-settings'),
  },
  {
    id: 'open-trash',
    group: '动作',
    icon: 'trash',
    label: '打开回收站',
    keywords: 'trash recycle huishouzhan',
    run: () => emit('navigate', 'trash'),
  },
])

const filteredCommands = computed(() => {
  const q = input.value.trim().toLowerCase()
  if (!q) return staticCommands.value
  return staticCommands.value.filter((c) =>
    `${c.label} ${c.keywords || ''}`.toLowerCase().includes(q)
  )
})

function taskHint(t) {
  const parts = [t.status]
  if (t.priority) parts.push(`${t.priority}优先级`)
  if (t.due_date) {
    const d = new Date(t.due_date)
    parts.push(`截止 ${d.getMonth() + 1}/${d.getDate()}`)
  }
  return parts.filter(Boolean).join(' · ')
}

const taskItems = computed(() =>
  results.value.map((t) => ({
    id: `task-${t.id}`,
    group: '任务',
    icon: 'task',
    label: t.title,
    hint: taskHint(t),
    run: () => emit('open-task', t),
  }))
)

const flatItems = computed(() => {
  const items = []
  if (quickCreateItem.value) items.push(quickCreateItem.value)
  items.push(...filteredCommands.value, ...taskItems.value)
  return items
})

// 分组展示，同时给每项标注扁平索引供键盘导航高亮
const sections = computed(() => {
  const out = []
  const byGroup = new Map()
  flatItems.value.forEach((item, i) => {
    if (!byGroup.has(item.group)) {
      const section = { name: item.group, items: [] }
      byGroup.set(item.group, section)
      out.push(section)
    }
    byGroup.get(item.group).items.push({ ...item, index: i })
  })
  return out
})

// 任务搜索：≥2 字符触发，250ms 防抖；seq 防止慢响应覆盖新结果
watch(input, (v) => {
  clearTimeout(searchTimer)
  const q = v.trim()
  if (q.length < 2) {
    results.value = []
    searching.value = false
    return
  }
  searching.value = true
  searchTimer = setTimeout(async () => {
    const seq = ++searchSeq
    try {
      const list = await searchTasks({ q })
      if (seq !== searchSeq) return
      results.value = (list || []).slice(0, 8)
    } catch {
      if (seq === searchSeq) results.value = []
    } finally {
      if (seq === searchSeq) searching.value = false
    }
  }, 250)
})

watch(flatItems, () => {
  activeIndex.value = 0
})

watch(
  () => props.open,
  async (v) => {
    clearTimeout(searchTimer)
    if (v) {
      input.value = ''
      results.value = []
      searching.value = false
      activeIndex.value = 0
      // Esc 用 window 捕获阶段处理：面板可能叠在 BaseModal(z-index 更低) 之上，
      // 需先于其 document 捕获监听关掉面板而不是底层弹窗
      window.addEventListener('keydown', onGlobalEsc, true)
      await nextTick()
      inputRef.value?.focus()
    } else {
      window.removeEventListener('keydown', onGlobalEsc, true)
    }
  }
)
onBeforeUnmount(() => window.removeEventListener('keydown', onGlobalEsc, true))

function onGlobalEsc(e) {
  if (e.key !== 'Escape') return
  e.stopPropagation()
  e.preventDefault()
  close()
}

function close() {
  emit('close')
}

async function execute(index) {
  const item = flatItems.value[index]
  if (!item) return
  close()
  await item.run()
}

async function move(delta) {
  const len = flatItems.value.length
  if (!len) return
  activeIndex.value = (activeIndex.value + delta + len) % len
  await nextTick()
  listRef.value?.querySelector('.cmd-item.active')?.scrollIntoView({ block: 'nearest' })
}

function onKeydown(e) {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    move(1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    move(-1)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    execute(activeIndex.value)
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="palette">
      <div v-if="open" class="palette-overlay" @mousedown.self="close" @keydown="onKeydown">
        <div class="palette" role="dialog" aria-modal="true" aria-label="命令面板">
          <div class="input-row">
            <ArtIcon name="search" tone="pearl" :size="17" />
            <input
              ref="inputRef"
              v-model="input"
              type="text"
              placeholder="搜索任务、切换视图、执行命令…（试试「新建 买牛奶」）"
            />
            <kbd class="esc-hint">Esc</kbd>
          </div>

          <div ref="listRef" class="list">
            <div v-for="section in sections" :key="section.name" class="group">
              <p class="group-name muted">{{ section.name }}</p>
              <button
                v-for="item in section.items"
                :key="item.id"
                type="button"
                class="cmd-item"
                :class="{ active: item.index === activeIndex }"
                @mouseenter="activeIndex = item.index"
                @click="execute(item.index)"
              >
                <ArtIcon :name="item.icon" tone="pearl" :size="17" />
                <span class="cmd-label">{{ item.label }}</span>
                <span v-if="item.hint" class="cmd-hint muted">{{ item.hint }}</span>
              </button>
              <p v-if="section.name === '任务' && searching" class="group-empty muted">搜索中…</p>
            </div>
            <p v-if="!flatItems.length" class="empty muted">没有匹配的命令或任务</p>
          </div>

          <div class="foot muted">
            <span><kbd>↑</kbd><kbd>↓</kbd> 选择</span>
            <span><kbd>Enter</kbd> 执行</span>
            <span><kbd>Esc</kbd> 关闭</span>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.palette-overlay {
  position: fixed;
  inset: 0;
  z-index: 310;
  background: var(--overlay-bg);
  backdrop-filter: blur(7px);
  -webkit-backdrop-filter: blur(7px);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 12vh 20px 24px;
}

.palette {
  width: 560px;
  max-width: 94vw;
  max-height: min(560px, 72vh);
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl), var(--shadow-inset);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  overflow: hidden;
}

.input-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.input-row input {
  flex: 1;
  min-width: 0;
  border: none;
  background: transparent;
  box-shadow: none;
  padding: 0;
  font-size: 15px;
  color: var(--text);
}
.input-row input:focus {
  outline: none;
  border: none;
  box-shadow: none;
}
.esc-hint {
  flex-shrink: 0;
  padding: 3px 8px;
  border-radius: 6px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  font-size: 11px;
  font-weight: 700;
  color: var(--text-soft);
}

.list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px;
}

.group + .group {
  margin-top: 6px;
}
.group-name {
  margin: 6px 8px 4px;
  font-size: 11px;
  font-weight: 700;
}
.group-empty {
  margin: 4px 10px 8px;
  font-size: 12px;
}

.cmd-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 9px 10px;
  border-radius: var(--radius-sm);
  background: transparent;
  border: 1px solid transparent;
  box-shadow: none;
  text-align: left;
  color: var(--text);
  font-size: 14px;
}
.cmd-item:hover,
.cmd-item.active {
  background: var(--accent-soft);
  border-color: color-mix(in srgb, var(--accent) 22%, var(--border));
  transform: none;
  box-shadow: none;
}
.cmd-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
}
.cmd-hint {
  flex-shrink: 0;
  font-size: 12px;
}

.empty {
  text-align: center;
  padding: 28px 12px;
  font-size: 13px;
}

.foot {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 9px 16px;
  border-top: 1px solid var(--border);
  font-size: 12px;
  flex-shrink: 0;
}
.foot span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.foot kbd {
  padding: 2px 6px;
  border-radius: 5px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  font-size: 11px;
  font-weight: 700;
  color: var(--text-soft);
}

.palette-enter-active,
.palette-leave-active {
  transition: opacity 0.18s ease;
}
.palette-enter-active .palette,
.palette-leave-active .palette {
  transition: opacity 0.18s ease, transform 0.22s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.palette-enter-from,
.palette-leave-to {
  opacity: 0;
}
.palette-enter-from .palette,
.palette-leave-to .palette {
  opacity: 0;
  transform: translateY(-10px) scale(0.98);
}

@media (max-width: 640px) {
  .palette-overlay {
    padding-top: 8vh;
  }
  .foot {
    display: none;
  }
}
</style>
