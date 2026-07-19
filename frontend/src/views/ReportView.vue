<script setup>
import { computed, inject, onMounted, ref, watch } from 'vue'
import { deleteReport, generateReport, getReport, listReports } from '../api/ai'
import { getSettings } from '../api/settings'
import ArtIcon from '../components/ArtIcon.vue'
import MarkdownText from '../components/MarkdownText.vue'
import AppSpinner from '../components/ui/AppSpinner.vue'
import PageHeader from '../components/ui/PageHeader.vue'
import SegmentedControl from '../components/ui/SegmentedControl.vue'

const emit = defineEmits(['changed'])
// 全局 toast 与应用内确认对话框(App.vue provide);提供降级以防组件树外调用
const toast = inject('toast', { success: () => {}, error: () => {}, info: () => {}, undo: () => {} })
const confirmDialog = inject('confirm-dialog', (o) => Promise.resolve(window.confirm(o.message || '')))

const reportType = ref('daily') // daily / weekly
const typeOptions = [
  { value: 'daily', label: '日报', icon: 'calendar' },
  { value: 'weekly', label: '周报', icon: 'timeline' },
]
const targetDate = ref(todayStr())
const reports = ref([])
const current = ref(null)
const busy = ref(false)
const error = ref('')
// 报告个性化设置（来自应用设置，带默认值兜底）
const settings = ref({ taskLimit: 50, timeout: 180, historyFilter: true })

function todayStr() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

const typeLabel = computed(() => (reportType.value === 'daily' ? '日报' : '周报'))

function typeLabelOf(r) {
  return r.report_type === 'daily' ? '日报' : '周报'
}

function formatDate(iso) {
  return (iso || '').slice(0, 10)
}

async function loadSettings() {
  try {
    const s = await getSettings()
    settings.value = {
      taskLimit: Number(s.report_task_limit ?? 50) || 50,
      timeout: Number(s.report_timeout_seconds ?? 180) || 180,
      historyFilter: s.report_history_filter !== 'false',
    }
  } catch {
    // 读取失败时沿用默认值
  }
}

async function loadReports() {
  try {
    const type = settings.value.historyFilter ? reportType.value : null
    reports.value = await listReports(type)
  } catch (e) {
    error.value = e.message
  }
}

onMounted(async () => {
  await loadSettings()
  await loadReports()
})

// 历史过滤开启时，切换日报/周报需刷新列表
watch(reportType, () => {
  if (settings.value.historyFilter) loadReports()
})

async function generate() {
  busy.value = true
  error.value = ''
  try {
    current.value = await generateReport(
      { report_type: reportType.value, target_date: targetDate.value || null },
      settings.value.timeout * 1000,
    )
    await loadReports()
    emit('changed')
    toast.success('报告已生成')
  } catch (e) {
    toast.error(`生成${typeLabel.value}失败：${e.message}`)
  } finally {
    busy.value = false
  }
}

async function viewReport(id) {
  try {
    const r = await getReport(id)
    current.value = r
    if (r) reportType.value = r.report_type
  } catch (e) {
    error.value = e.message
  }
}

async function removeReport(id) {
  const ok = await confirmDialog({
    title: '删除报告',
    message: '删除后不可恢复，确定删除这份报告吗？',
    confirmText: '删除',
    danger: true,
  })
  if (!ok) return
  try {
    await deleteReport(id)
    if (current.value?.id === id) current.value = null
    await loadReports()
    toast.success('报告已删除')
  } catch (e) {
    toast.error(`删除失败：${e.message}`)
  }
}

async function copyContent() {
  if (!current.value?.content) return
  try {
    await navigator.clipboard.writeText(current.value.content)
    toast.success('已复制到剪贴板')
  } catch {
    toast.error('复制失败，请手动选择文本复制')
  }
}
</script>

<template>
  <div class="report-view workspace-page">
    <PageHeader icon="archive" title="日报周报" subtitle="由 AI 汇总你的任务进展，一键生成日报与周报。" />

    <section class="toolbar card">
      <SegmentedControl v-model="reportType" :options="typeOptions" />
      <input v-model="targetDate" type="date" />
      <button type="button" :disabled="busy" @click="generate">
        {{ busy ? '生成中…' : `生成${typeLabel}` }}
      </button>
      <button v-if="current" type="button" class="ghost" @click="copyContent">复制全文</button>
    </section>

    <p v-if="error" class="error">{{ error }}</p>

    <div class="body">
      <section class="content card">
        <div v-if="busy" class="loading-overlay">
          <AppSpinner size="lg" :label="`正在生成${typeLabel}…`" />
        </div>
        <article v-if="current" class="report-article" :class="{ dimmed: busy }">
          <header>
            <h2>{{ current.title }}</h2>
            <span class="meta">{{ current.period_start }} ~ {{ current.period_end }} · {{ current.model_name }}</span>
          </header>
          <MarkdownText :content="current.content" />
        </article>
        <div v-else-if="!busy" class="placeholder">
          <p>选择类型与日期，点「生成{{ typeLabel }}」由 AI 汇总你的任务；或从右侧查看历史报告。</p>
        </div>
      </section>

      <aside class="history card">
        <h3>
          历史报告
          <span v-if="settings.historyFilter" class="filter-tag">仅{{ typeLabel }}</span>
        </h3>
        <div class="hist-list">
          <button
            v-for="r in reports"
            :key="r.id"
            type="button"
            class="hist-item"
            :class="{ active: current?.id === r.id }"
            @click="viewReport(r.id)"
          >
            <span class="hist-title">{{ r.title }}</span>
            <span class="hist-meta">{{ typeLabelOf(r) }} · {{ formatDate(r.created_at) }}</span>
            <span class="hist-del" title="删除" @click.stop="removeReport(r.id)">
              <ArtIcon name="close" tone="pearl" :size="14" />
            </span>
          </button>
          <p v-if="!reports.length" class="muted">暂无历史报告</p>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.report-view {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
}
/* 根节点已有 gap,去掉 PageHeader 自带下间距避免叠加 */
.report-view :deep(.page-header) {
  margin-bottom: 0;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
/* 全局 input 为 width:100%,工具条内恢复自适应宽度 */
.toolbar input[type='date'] {
  width: auto;
}
.error {
  color: var(--danger);
  margin: 0;
}
.body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 16px;
}
.content {
  position: relative;
  overflow: auto;
  min-height: 0;
}
.loading-overlay {
  position: absolute;
  inset: 0;
  z-index: 3;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--surface) 72%, transparent);
  border-radius: var(--radius-md);
}
.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-soft);
  min-height: 240px;
  text-align: center;
}
.report-article.dimmed {
  opacity: 0.45;
}
.report-article header {
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}
.report-article h2 {
  margin: 0 0 6px;
  font-size: 19px;
  color: var(--text);
}
.meta {
  font-size: 13px;
  color: var(--text-soft);
}
.history {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.history h3 {
  margin: 0 0 12px;
  font-size: 15px;
  color: var(--text);
  display: flex;
  align-items: center;
  gap: 8px;
}
.filter-tag {
  font-size: 11px;
  font-weight: 650;
  color: var(--accent-strong);
  background: var(--accent-soft);
  padding: 2px 8px;
  border-radius: var(--radius-pill);
}
.hist-list {
  overflow: auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.hist-item {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 2px 8px;
  text-align: left;
  color: var(--text);
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  box-shadow: none;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.hist-item:hover {
  border-color: var(--accent);
  background: var(--surface);
}
.hist-item.active {
  border-color: var(--accent);
  background: var(--accent-soft);
}
.hist-title {
  font-weight: 600;
  color: var(--text);
}
.hist-meta {
  grid-column: 1;
  font-size: 12px;
  color: var(--text-soft);
}
.hist-del {
  grid-column: 2;
  grid-row: 1 / span 2;
  align-self: center;
  display: inline-flex;
  padding: 4px;
  border-radius: var(--radius-xs);
  cursor: pointer;
  transition: background 0.15s ease;
}
.hist-del:hover {
  background: color-mix(in srgb, var(--danger) 10%, transparent);
}
.hist-del:hover :deep(.art-icon) {
  --icon-color: var(--danger);
}
@media (max-width: 900px) {
  .body {
    grid-template-columns: 1fr;
  }
}
</style>
