<script setup lang="ts">
/**
 * 报表视图（/reports，次导航）：晨报/日报/周报的列表 + 纸面详情。
 * - 数据：GET /ai/reports（列表即全文，选中不二次请求）；生成 POST /ai/reports/{daily|weekly}
 * - 生成依赖启用的 AI 配置与 LLM 额度：失败（400/422）在行内告警中呈现，可重试，不静默
 * - 晨报不可手动生成（后端同日幂等自动产出），故生成入口只有日报/周报
 * - 自动刷新：与壳层同款接线 —— watch run.phase 到 completed/cancelled 即重拉
 */
import { computed, onMounted, ref, watch } from 'vue'
import DomainState from '../components/domain/DomainState.vue'
import { useReportsStore, type ReportFilter } from '../stores/reports'
import { useRunStore } from '../stores/run'
import type { Report } from '../api/reports'
import { renderMarkdown } from '../utils/md'

const store = useReportsStore()
const run = useRunStore()

const TYPE_LABEL: Record<string, string> = { briefing: '晨报', daily: '日报', weekly: '周报' }
const FILTERS: { key: ReportFilter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'briefing', label: '晨报' },
  { key: 'daily', label: '日报' },
  { key: 'weekly', label: '周报' },
]

function typeLabel(t: string): string {
  return TYPE_LABEL[t] ?? t
}
function periodLabel(r: Report): string {
  return r.period_start === r.period_end ? r.period_start : `${r.period_start} ~ ${r.period_end}`
}
function createdLabel(r: Report): string {
  return r.created_at.slice(0, 16).replace('T', ' ')
}
function modelLabel(r: Report): string {
  return r.model_name === 'rule' ? '规则生成' : r.model_name
}

const renderedContent = computed(() => (store.selected ? renderMarkdown(store.selected.content) : ''))

/* 删除两段确认（与设置页永久授权同款） */
const confirmingDelete = ref<number | null>(null)
function requestDelete(id: number): void {
  if (confirmingDelete.value === id) {
    confirmingDelete.value = null
    void store.remove(id)
  } else {
    confirmingDelete.value = id
  }
}
watch(
  () => store.selectedId,
  () => (confirmingDelete.value = null),
)

onMounted(() => {
  if (store.reports === null) void store.load()
})

watch(
  () => run.phase,
  (p, prev) => {
    if (prev && (p === 'completed' || p === 'cancelled')) void store.load()
  },
)
</script>

<template>
  <section class="reports-view">
    <Teleport defer to="#head-actions">
      <button
        class="gen"
        :disabled="store.generating.includes('daily')"
        @click="store.generate('daily')"
      >
        {{ store.generating.includes('daily') ? '生成中…' : '生成日报' }}
      </button>
      <button
        class="gen"
        :disabled="store.generating.includes('weekly')"
        @click="store.generate('weekly')"
      >
        {{ store.generating.includes('weekly') ? '生成中…' : '生成周报' }}
      </button>
      <button class="gen ghost" @click="store.load()">刷新</button>
    </Teleport>

    <header class="rv-head">
      <span class="rv-caption">日报周报</span>
      <span class="rv-note">晨报由知时每日自动备好；日报/周报由 AI 汇总生成，也可手动补一份。</span>
    </header>

    <nav class="rv-filters" aria-label="报表类型筛选">
      <button
        v-for="f in FILTERS"
        :key="f.key"
        class="flt"
        :class="{ on: store.filter === f.key }"
        @click="store.setFilter(f.key)"
      >
        {{ f.label }}
      </button>
    </nav>

    <p v-if="store.actionError" class="rv-error" role="alert">{{ store.actionError }}</p>

    <div class="rv-body">
      <!-- 列表 -->
      <section class="rv-list">
        <DomainState
          :loading="store.loading"
          loading-text="正在拉取报表…"
          :error="store.error"
          :empty="!store.loading && store.reports !== null && store.reports.length === 0"
          empty-title="还没有报表"
          @retry="store.load()"
        >
          晨报会在每天自动出现；点右上「生成日报 / 生成周报」让 AI 汇总一段时期。
        </DomainState>
        <ul v-if="store.reports && store.reports.length > 0" class="items">
          <li v-for="r in store.reports" :key="r.id">
            <button
              class="row"
              :class="{ on: store.selectedId === r.id }"
              @click="store.select(r.id)"
            >
              <span class="row-top">
                <span class="badge" :data-type="r.report_type">{{ typeLabel(r.report_type) }}</span>
                <span class="row-title">{{ r.title }}</span>
              </span>
              <span class="row-meta">{{ periodLabel(r) }} · {{ modelLabel(r) }}</span>
            </button>
          </li>
        </ul>
      </section>

      <!-- 纸面详情 -->
      <section class="rv-paper-wrap">
        <div v-if="store.selected" class="paper">
          <header class="paper-head">
            <h2 class="paper-title">{{ store.selected.title }}</h2>
            <p class="paper-meta">
              {{ typeLabel(store.selected.report_type) }} · {{ periodLabel(store.selected) }} ·
              {{ modelLabel(store.selected) }} · 记于 {{ createdLabel(store.selected) }}
            </p>
          </header>
          <!-- eslint-disable-next-line vue/no-v-html -- renderMarkdown 已做整体 HTML 转义 -->
          <article class="paper-body" v-html="renderedContent" />
          <footer class="paper-foot">
            <button
              class="del"
              :class="{ sure: confirmingDelete === store.selected.id }"
              :disabled="store.deleting.includes(store.selected.id)"
              @click="requestDelete(store.selected.id)"
            >
              {{ confirmingDelete === store.selected.id ? '确认删除（不可恢复）' : '删除这份报表' }}
            </button>
          </footer>
        </div>
        <div v-else-if="!store.loading && store.reports && store.reports.length > 0" class="paper-hint">
          从左边挑一份报表看看。
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.reports-view {
  flex: 1;
  min-height: 0;
  padding: 18px 22px 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: auto;
}

.gen {
  font-size: 12.5px;
  color: var(--amber-soft);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-pill);
  padding: 4px 13px;
}
.gen:hover {
  border-color: var(--line-hover);
}
.gen:disabled {
  /* 浅色 --ctl-disabled-opacity=0.75（禁用文字须 ≥3:1）；暗色 fallback 0.5 不变 */
  opacity: var(--ctl-disabled-opacity, 0.5);
  cursor: default;
}
.gen.ghost {
  color: var(--ink-2);
}

.rv-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.rv-caption {
  font-family: var(--serif);
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--ink-2);
}
.rv-note {
  font-size: 11.5px;
  color: var(--ink-3);
}

.rv-filters {
  display: flex;
  gap: 6px;
}
.flt {
  font-size: 12px;
  color: var(--ink-3);
  border: 1px solid var(--line);
  border-radius: var(--radius-pill);
  padding: 3px 12px;
}
.flt:hover {
  border-color: var(--line-hover);
  color: var(--ink-2);
}
.flt.on {
  color: var(--amber-soft);
  border-color: var(--line-hover);
}

.rv-error {
  font-size: 12.5px;
  color: var(--terra-soft);
  border: 1px dashed var(--terra-dashed);
  border-radius: var(--radius-s);
  padding: 8px 12px;
}

.rv-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(280px, 340px) 1fr;
  gap: 14px;
  align-items: start;
}

.rv-list {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.items {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.row {
  width: 100%;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 3px;
  border: 1px solid var(--line);
  background: var(--bg-raise);
  border-radius: var(--radius-s);
  padding: 9px 12px;
}
.row:hover {
  border-color: var(--line-hover);
}
.row.on {
  border-color: var(--line-hover);
  background: var(--bg-app);
}
.row-top {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}
.badge {
  flex: none;
  font-size: 10.5px;
  letter-spacing: 0.08em;
  color: var(--amber-soft);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-pill);
  padding: 1px 8px;
}
.badge[data-type='briefing'] {
  color: var(--ink-2);
}
.badge[data-type='weekly'] {
  color: var(--terra-soft);
}
.row-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.row-meta {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-3);
}

/* 纸面详情：A 的纸张意象 —— 衬线标题 + 米色纸面 + 细边 */
.rv-paper-wrap {
  min-width: 0;
}
.paper {
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  background: var(--bg-raise);
  padding: 26px 30px 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.paper-head {
  border-bottom: 1px solid var(--line);
  padding-bottom: 12px;
}
.paper-title {
  font-family: var(--serif);
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 0.05em;
  color: var(--ink);
}
.paper-meta {
  margin-top: 6px;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-3);
}
.paper-body {
  font-size: 13.5px;
  line-height: 1.9;
  color: var(--ink-2);
}
.paper-body :deep(p) {
  margin: 0 0 4px;
}
.paper-body :deep(ul),
.paper-body :deep(ol) {
  margin: 4px 0 8px;
  padding-left: 22px;
}
.paper-body :deep(li) {
  margin: 2px 0;
}
.paper-body :deep(strong) {
  color: var(--ink);
}
.paper-body :deep(code) {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--amber-soft);
}
.paper-body :deep(table) {
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 12.5px;
}
.paper-body :deep(th),
.paper-body :deep(td) {
  border: 1px solid var(--line);
  padding: 4px 10px;
}
.paper-body :deep(th) {
  color: var(--ink);
  font-weight: 600;
}
.paper-foot {
  border-top: 1px solid var(--line);
  padding-top: 12px;
  display: flex;
  justify-content: flex-end;
}
.del {
  font-size: 11.5px;
  color: var(--terra-soft);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-s);
  padding: 3px 10px;
}
.del:hover {
  border-color: var(--terra-dashed);
}
.del.sure {
  border-color: var(--terra-dashed);
  background: var(--bg-app);
}
.del:disabled {
  /* 同 gen：浅色 0.75、暗色 fallback 0.5 不变 */
  opacity: var(--ctl-disabled-opacity, 0.5);
  cursor: default;
}
.paper-hint {
  padding: 40px 0;
  text-align: center;
  font-size: 12.5px;
  color: var(--ink-3);
}

@media (max-width: 880px) {
  .rv-body {
    grid-template-columns: 1fr;
  }
  .paper {
    padding: 18px 16px 14px;
  }
  .paper-title {
    font-size: 17px;
  }
}
</style>
