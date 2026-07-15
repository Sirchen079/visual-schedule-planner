<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { deleteReport, generateReport, getReport, listReports } from '../api/ai'
import { getSettings } from '../api/settings'

const emit = defineEmits(['changed'])

const reportType = ref('daily') // daily / weekly
const targetDate = ref(todayStr())
const reports = ref([])
const current = ref(null)
const busy = ref(false)
const error = ref('')
const copied = ref(false)
// 报告个性化设置（来自应用设置，带默认值兜底）
const settings = ref({ taskLimit: 50, timeout: 180, historyFilter: true })
let copiedTimer = null

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
  } catch (e) {
    error.value = e.message
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
  try {
    await deleteReport(id)
    if (current.value?.id === id) current.value = null
    await loadReports()
  } catch (e) {
    error.value = e.message
  }
}

function copyContent() {
  if (!current.value?.content) return
  navigator.clipboard
    ?.writeText(current.value.content)
    .then(() => {
      copied.value = true
      clearTimeout(copiedTimer)
      copiedTimer = setTimeout(() => (copied.value = false), 1500)
    })
    .catch(() => {})
}

// 轻量 markdown 渲染（先 escape 再处理标题/粗体/列表/段落），避免引入额外依赖
function renderMarkdown(md) {
  if (!md) return ''
  const esc = (s) =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  const out = []
  let inList = false
  const closeList = () => {
    if (inList) {
      out.push('</ul>')
      inList = false
    }
  }
  for (const raw of md.split(/\r?\n/)) {
    const line = raw.trim()
    if (!line) {
      closeList()
      continue
    }
    if (/^### /.test(line)) {
      closeList()
      out.push(`<h3>${inline(line.slice(4))}</h3>`)
    } else if (/^## /.test(line)) {
      closeList()
      out.push(`<h2>${inline(line.slice(3))}</h2>`)
    } else if (/^# /.test(line)) {
      closeList()
      out.push(`<h2>${inline(line.slice(2))}</h2>`)
    } else if (/^[-*] /.test(line)) {
      if (!inList) {
        out.push('<ul>')
        inList = true
      }
      out.push(`<li>${inline(line.slice(2))}</li>`)
    } else {
      closeList()
      out.push(`<p>${inline(line)}</p>`)
    }
  }
  closeList()
  return out.join('')
}
</script>

<template>
  <div class="report-view">
    <section class="toolbar panel">
      <div class="seg">
        <button :class="{ active: reportType === 'daily' }" @click="reportType = 'daily'">日报</button>
        <button :class="{ active: reportType === 'weekly' }" @click="reportType = 'weekly'">周报</button>
      </div>
      <input v-model="targetDate" type="date" />
      <button class="primary" :disabled="busy" @click="generate">
        {{ busy ? '生成中…' : `生成${typeLabel}` }}
      </button>
      <button v-if="current" class="copy-btn" :class="{ done: copied }" @click="copyContent">
        {{ copied ? '已复制 ✓' : '复制全文' }}
      </button>
    </section>

    <p v-if="error" class="error">{{ error }}</p>

    <div class="body">
      <section class="content panel">
        <div v-if="busy" class="loading-overlay">
          <span class="spinner"></span>
          <p>正在生成{{ typeLabel }}…</p>
        </div>
        <article v-if="current" class="report-article" :class="{ dimmed: busy }">
          <header>
            <h2>{{ current.title }}</h2>
            <span class="meta">{{ current.period_start }} ~ {{ current.period_end }} · {{ current.model_name }}</span>
          </header>
          <div class="markdown" v-html="renderMarkdown(current.content)"></div>
        </article>
        <div v-else-if="!busy" class="placeholder">
          <p>选择类型与日期，点「生成{{ typeLabel }}」由 AI 汇总你的任务；或从右侧查看历史报告。</p>
        </div>
      </section>

      <aside class="history panel">
        <h3>
          历史报告
          <span v-if="settings.historyFilter" class="filter-tag">仅{{ typeLabel }}</span>
        </h3>
        <div class="hist-list">
          <button
            v-for="r in reports"
            :key="r.id"
            class="hist-item"
            :class="{ active: current?.id === r.id }"
            @click="viewReport(r.id)"
          >
            <span class="hist-title">{{ r.title }}</span>
            <span class="hist-meta">{{ typeLabelOf(r) }} · {{ formatDate(r.created_at) }}</span>
            <span class="hist-del" title="删除" @click.stop="removeReport(r.id)">×</span>
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
  gap: 14px;
  height: 100%;
}
.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 16px;
  box-shadow: var(--shadow-md), var(--shadow-inset);
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.seg {
  display: inline-flex;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 3px;
}
.seg button {
  background: transparent;
  padding: 6px 16px;
  border-radius: var(--radius-sm);
  font-weight: 600;
  color: var(--text-soft);
}
.seg button.active {
  background: var(--accent-soft);
  color: var(--accent-strong);
}
input[type='date'] {
  padding: 7px 10px;
  border-radius: var(--radius-sm);
}
.primary {
  background: var(--accent);
  color: #fff;
  font-weight: 650;
  padding: 8px 18px;
  border-radius: var(--radius-sm);
}
.copy-btn {
  padding: 8px 14px;
  border-radius: var(--radius-sm);
  color: var(--text-soft);
}
.copy-btn.done {
  color: var(--success);
  font-weight: 650;
}
.error {
  color: var(--pri-high);
  margin: 0;
}
.body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 14px;
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
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--text-soft);
  background: color-mix(in srgb, var(--surface) 72%, transparent);
  border-radius: var(--radius-md);
}
.placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--text-soft);
  min-height: 240px;
}
.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--surface-2);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
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
.markdown :deep(h2) {
  font-size: 16px;
  margin: 18px 0 8px;
  color: var(--accent-strong);
}
.markdown :deep(h3) {
  font-size: 14px;
  margin: 14px 0 6px;
  color: var(--text);
}
.markdown :deep(p) {
  margin: 6px 0;
  line-height: 1.7;
  color: var(--text);
}
.markdown :deep(ul) {
  margin: 6px 0;
  padding-left: 22px;
}
.markdown :deep(li) {
  margin: 3px 0;
  line-height: 1.7;
  color: var(--text);
}
.markdown :deep(strong) {
  color: var(--text);
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
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.hist-item:hover {
  border-color: var(--accent);
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
  color: var(--text-soft);
  font-size: 16px;
  padding: 2px 6px;
  border-radius: var(--radius-sm);
}
.hist-del:hover {
  color: var(--pri-high);
  background: rgba(242, 107, 122, 0.1);
}
.muted {
  color: var(--text-soft);
  font-size: 13px;
}
@media (max-width: 900px) {
  .body {
    grid-template-columns: 1fr;
  }
}
</style>
