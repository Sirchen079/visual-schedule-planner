<script setup>
// 日记视图：左栏最近日记列表 + 右栏当日编辑器（Markdown 编辑/预览）。
// 数据自取自管：进入默认定位今天；切换日期前若有未保存修改先静默保存。
import { computed, inject, onBeforeUnmount, onMounted, ref } from 'vue'
import { deleteEntry, getEntry, listEntries, upsertEntry } from '../api/journal'
import { journalDraft } from '../api/ai'
import { getSettings } from '../api/settings'
import { askAssistant } from '../utils/assistant'
import ArtIcon from '../components/ArtIcon.vue'
import MarkdownText from '../components/MarkdownText.vue'
import AppSpinner from '../components/ui/AppSpinner.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import PageHeader from '../components/ui/PageHeader.vue'
import SegmentedControl from '../components/ui/SegmentedControl.vue'

// 全局 toast 与应用内确认对话框(App.vue provide);提供降级以防组件树外调用
const toast = inject('toast', { success: () => {}, error: () => {}, info: () => {}, undo: () => {} })
const confirmDialog = inject('confirm-dialog', (o) => Promise.resolve(window.confirm(o.message || '')))

// ---- 内嵌 AI 动作：「AI 本日小结」生成草稿写入编辑器，置 dirty 待用户手动保存 ----
const aiAvailable = inject('ai-available', ref(false))
const inlineAiEnabled = ref(false)
const draftBusy = ref(false)

async function aiDraft() {
  if (draftBusy.value || !aiAvailable.value) return
  draftBusy.value = true
  try {
    const res = await journalDraft(currentDate.value)
    const text = (res?.content || '').trim()
    if (text) {
      // 已有内容则空行分隔追加到末尾；空白则直接填入
      content.value = content.value.trim() ? `${content.value.trimEnd()}\n\n${text}` : text
    }
    if (res?.source === 'rule') {
      toast.info('未启用 AI 配置，已用模板生成')
    } else {
      toast.success('已生成小结，确认后记得保存')
    }
  } catch (e) {
    toast.error(`生成小结失败：${e.message}`)
  } finally {
    draftBusy.value = false
  }
}

// 「问助手回顾」：让 AI 读最近日记，做情绪与主题回顾并给出跟进建议
function reviewJournal() {
  askAssistant(
    '读读我最近的日记（用 list_journal_entries 查看），帮我做个回顾：' +
      '情绪走向如何、反复出现的主题是什么、有哪些值得跟进处理的事——需要落成任务的请直接帮我建。'
  )
}

const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六']

function todayStr() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

// 'YYYY-MM-DD' 按本地时区解析（避免 new Date(str) 走 UTC 导致日期偏移）
function parseDay(dateStr) {
  return new Date(`${dateStr}T00:00:00`)
}

function formatTitle(dateStr) {
  const d = parseDay(dateStr)
  return `${d.getMonth() + 1}月${d.getDate()}日 星期${WEEKDAYS[d.getDay()]}`
}

function formatListDate(dateStr) {
  const d = parseDay(dateStr)
  return `${d.getMonth() + 1}月${d.getDate()}日 周${WEEKDAYS[d.getDay()]}`
}

function formatTime(d) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const entries = ref([])
const listLoading = ref(true)
const currentDate = ref(todayStr())
const content = ref('')
const mood = ref(null)
const existsOnServer = ref(false)
const entryLoading = ref(false)
const saving = ref(false)
const lastSavedAt = ref(null)
const mode = ref('edit') // edit | preview
// 已保存快照：与当前编辑值比较得出 dirty
const savedSnapshot = ref({ content: '', mood: null })

const MOOD_OPTIONS = [
  { value: '好', label: '好' },
  { value: '平', label: '平' },
  { value: '差', label: '差' },
  { value: null, label: '不设' },
]
const modeOptions = [
  { value: 'edit', label: '编辑', icon: 'task' },
  { value: 'preview', label: '预览', icon: 'search' },
]

const isToday = computed(() => currentDate.value === todayStr())
const dirty = computed(
  () => content.value !== savedSnapshot.value.content || mood.value !== savedSnapshot.value.mood
)
const saveHint = computed(() => {
  if (saving.value) return '保存中…'
  if (dirty.value) return '未保存修改'
  if (lastSavedAt.value) return `已保存 ${formatTime(lastSavedAt.value)}`
  return ''
})

async function loadList() {
  try {
    entries.value = await listEntries(30)
  } catch (e) {
    toast.error(`日记列表加载失败：${e.message}`)
  } finally {
    listLoading.value = false
  }
}

function applyEntry(entry) {
  content.value = entry?.content || ''
  mood.value = entry?.mood || null
  existsOnServer.value = !!entry
  savedSnapshot.value = { content: content.value, mood: mood.value }
  lastSavedAt.value = entry?.updated_at ? new Date(entry.updated_at) : null
}

async function loadEntry(date) {
  entryLoading.value = true
  try {
    applyEntry(await getEntry(date))
  } catch (e) {
    if (e.status === 404) {
      applyEntry(null) // 无日记 = 空白新篇
    } else {
      toast.error(`日记加载失败：${e.message}`)
    }
  } finally {
    entryLoading.value = false
  }
}

async function save() {
  // 空白新篇无需落库，避免产生空日记
  if (!existsOnServer.value && !content.value.trim() && !mood.value) return
  saving.value = true
  try {
    const entry = await upsertEntry(currentDate.value, {
      content: content.value,
      mood: mood.value,
    })
    applyEntry(entry)
    lastSavedAt.value = new Date()
    await loadList()
  } catch (e) {
    toast.error(`保存失败：${e.message}`)
  } finally {
    saving.value = false
  }
}

// 切换日期：有未保存修改先静默保存，再加载目标日期
async function selectDate(date) {
  if (entryLoading.value || date === currentDate.value) return
  if (dirty.value) await save()
  currentDate.value = date
  await loadEntry(date)
}

function setMood(value) {
  mood.value = value
}

async function removeEntry() {
  if (!existsOnServer.value) return
  const ok = await confirmDialog({
    title: '删除日记',
    message: `将删除 ${formatTitle(currentDate.value)} 的日记，删除后不可恢复。`,
    confirmText: '删除',
    danger: true,
  })
  if (!ok) return
  try {
    await deleteEntry(currentDate.value)
    applyEntry(null)
    await loadList()
    toast.success('日记已删除')
  } catch (e) {
    if (e.status === 404) {
      applyEntry(null) // 服务端本就不存在，按已删除处理
    } else {
      toast.error(`删除失败：${e.message}`)
    }
  }
}

onMounted(async () => {
  await Promise.all([loadList(), loadEntry(currentDate.value)])
  // 内嵌 AI 开关读取一次（功能面板「内嵌 AI 动作」，默认开启）
  try {
    const s = await getSettings()
    inlineAiEnabled.value = s.feature_inline_ai_enabled !== 'false'
  } catch {
    // 读取失败按关闭处理，不展示按钮
  }
})

// 离开视图时兜底：有未保存修改静默保存，避免丢稿
onBeforeUnmount(() => {
  if (dirty.value) void save()
})
</script>

<template>
  <div class="journal workspace-page">
    <PageHeader icon="file" title="日记" subtitle="每天一篇，记下决定、情绪与灵感。">
      <template #actions>
        <button class="ghost" @click="reviewJournal">问助手回顾</button>
      </template>
    </PageHeader>

    <div class="journal-body">
      <aside class="journal-list card">
        <div class="list-head">
          <h3>最近日记</h3>
          <button type="button" class="ghost today-btn" @click="selectDate(todayStr())">今天</button>
        </div>
        <div v-if="listLoading" class="list-loading">
          <AppSpinner size="md" label="加载中" />
        </div>
        <EmptyState
          v-else-if="!entries.length"
          compact
          icon="file"
          title="还没有日记"
          hint="点右上角「今天」，写下第一篇。"
        />
        <div v-else class="entry-list">
          <button
            v-for="e in entries"
            :key="e.id"
            type="button"
            class="entry-item"
            :class="{ active: e.date === currentDate }"
            @click="selectDate(e.date)"
          >
            <span class="entry-date-row">
              <span class="entry-date">{{ formatListDate(e.date) }}</span>
              <span v-if="e.mood" class="mood-badge" :data-mood="e.mood">{{ e.mood }}</span>
            </span>
            <span class="entry-preview">{{ e.preview || '（无内容）' }}</span>
          </button>
        </div>
      </aside>

      <section class="journal-editor card">
        <div v-if="entryLoading" class="editor-loading">
          <AppSpinner size="lg" label="加载中" />
        </div>
        <template v-else>
          <header class="editor-head">
            <h2 class="editor-title">{{ formatTitle(currentDate) }}</h2>
            <span v-if="isToday" class="tag today-tag">今天</span>
          </header>

          <div class="mood-row">
            <span class="mood-label">心情</span>
            <div class="mood-chips" role="radiogroup" aria-label="心情">
              <button
                v-for="m in MOOD_OPTIONS"
                :key="String(m.value)"
                type="button"
                role="radio"
                :aria-checked="mood === m.value ? 'true' : 'false'"
                class="mood-chip"
                :class="{ active: mood === m.value }"
                @click="setMood(m.value)"
              >
                {{ m.label }}
              </button>
            </div>
          </div>

          <textarea
            v-if="mode === 'edit'"
            v-model="content"
            class="editor-textarea"
            placeholder="今天发生了什么？值得记住的决定、情绪、灵感……"
          ></textarea>
          <div v-else class="editor-preview">
            <MarkdownText v-if="content.trim()" :content="content" />
            <p v-else class="muted">还没有内容，切到「编辑」开始记录。</p>
          </div>

          <footer class="editor-toolbar">
            <button type="button" class="save-btn" :disabled="saving || !dirty" @click="save">
              保存
            </button>
            <span class="save-hint muted">{{ saveHint }}</span>
            <button
              v-if="inlineAiEnabled"
              type="button"
              class="ghost draft-btn"
              :disabled="draftBusy || !aiAvailable"
              :title="aiAvailable ? '让 AI 根据今天的任务与记录起草本日小结' : '需先在助手中启用模型配置'"
              @click="aiDraft"
            >
              {{ draftBusy ? '生成中…' : 'AI 本日小结' }}
            </button>
            <div class="toolbar-right">
              <SegmentedControl v-model="mode" :options="modeOptions" size="sm" />
              <button
                v-if="existsOnServer"
                type="button"
                class="ghost delete-btn"
                @click="removeEntry"
              >
                删除本篇
              </button>
            </div>
          </footer>
        </template>
      </section>
    </div>
  </div>
</template>

<style scoped>
.journal {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
/* 根节点已有 gap,去掉 PageHeader 自带下间距避免叠加 */
.journal :deep(.page-header) {
  margin-bottom: 0;
}

.journal-body {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

/* ---- 左栏：日期列表 ---- */
.journal-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

.list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.list-head h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
}

.today-btn {
  padding: 6px 12px;
  font-size: 13px;
  border-radius: var(--radius-sm);
}

.list-loading {
  display: flex;
  justify-content: center;
  padding: 28px 0;
}

.entry-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 60vh;
  overflow: auto;
}

.entry-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
  padding: 10px 12px;
  text-align: left;
  color: var(--text);
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  box-shadow: none;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.entry-item:hover {
  border-color: var(--accent);
  background: var(--surface);
}

.entry-item.active {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.entry-date-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.entry-date {
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
}

.mood-badge {
  flex-shrink: 0;
  padding: 1px 8px;
  border-radius: var(--radius-pill);
  font-size: 11px;
  font-weight: 700;
  background: var(--surface-3);
  color: var(--text-soft);
}

.mood-badge[data-mood='好'] {
  background: var(--success-soft);
  color: var(--success);
}

.mood-badge[data-mood='平'] {
  background: var(--warning-soft);
  color: var(--warning);
}

.mood-badge[data-mood='差'] {
  background: var(--danger-soft);
  color: var(--danger-strong);
}

.entry-preview {
  font-size: 12px;
  color: var(--text-soft);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ---- 右栏：编辑器 ---- */
.journal-editor {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
  min-height: 420px;
}

.editor-loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 320px;
}

.editor-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}

.editor-title {
  margin: 0;
  font-size: 19px;
  font-weight: 800;
  color: var(--text);
}

.today-tag {
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  color: var(--accent-hover);
  border-color: color-mix(in srgb, var(--accent) 22%, transparent);
}

.mood-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.mood-label {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-soft);
  flex-shrink: 0;
}

.mood-chips {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.mood-chip {
  padding: 5px 14px;
  font-size: 13px;
  font-weight: 650;
  color: var(--text-soft);
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  box-shadow: none;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}

.mood-chip:hover:not(.active) {
  color: var(--text);
  background: var(--surface);
  border-color: var(--border-strong);
}

.mood-chip.active {
  color: var(--accent-strong);
  background: var(--accent-soft);
  border-color: color-mix(in srgb, var(--accent) 32%, var(--border));
}

.editor-textarea {
  flex: 1;
  width: 100%;
  min-height: 40vh;
  resize: vertical;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.7;
}

.editor-preview {
  flex: 1;
  min-height: 40vh;
  padding: 4px 2px;
  overflow: auto;
}

.editor-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.save-btn {
  padding: 8px 22px;
}

.save-hint {
  font-size: 12px;
}

.draft-btn {
  padding: 7px 14px;
  font-size: 13px;
  border-radius: var(--radius-sm);
}

.toolbar-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 10px;
}

.delete-btn {
  color: var(--danger);
}

.delete-btn:hover {
  color: var(--danger-strong);
  border-color: color-mix(in srgb, var(--danger) 36%, var(--border));
  background: var(--danger-soft);
}

@media (max-width: 720px) {
  .journal-body {
    grid-template-columns: 1fr;
  }
  .entry-list {
    max-height: 220px;
  }
  .toolbar-right {
    width: 100%;
    justify-content: space-between;
  }
}
</style>
