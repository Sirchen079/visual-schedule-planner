<script setup>
// Token 用量面板：按日堆叠柱状图 + 模型汇总表。
// 成本为按配置价目的估算值，estimated_cost 为 null 时显示「—」。
import { computed, onMounted, ref, watch } from 'vue'
import { getTokenUsage } from '../../api/stats'
import BaseChart, { cssVar } from '../../components/charts/BaseChart.vue'
import EmptyState from '../../components/ui/EmptyState.vue'
import SegmentedControl from '../../components/ui/SegmentedControl.vue'
import { useThemeTick } from '../../composables/useThemeTick'

const days = ref(30)
const rangeOptions = [
  { value: 7, label: '7 天' },
  { value: 30, label: '30 天' },
  { value: 90, label: '90 天' },
]

const usage = ref(null)
const loading = ref(false)
const failed = ref(false)
const themeTick = useThemeTick()

async function load() {
  loading.value = true
  failed.value = false
  try {
    usage.value = await getTokenUsage(days.value)
  } catch {
    usage.value = null
    failed.value = true
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(days, load)

const hasData = computed(() => {
  const u = usage.value
  if (!u) return false
  return (u.days || []).some((d) => d.total_tokens > 0) || (u.models || []).length > 0
})

const chartOption = computed(() => {
  themeTick.value
  const rows = usage.value?.days || []
  if (!rows.length || !hasData.value) return null
  const text = cssVar('--text-soft', '#476a7d')
  const line = cssVar('--border', 'rgba(130, 185, 208, 0.55)')
  const split = cssVar('--surface-3', 'rgba(214, 236, 245, 0.82)')
  const accent = cssVar('--accent', '#3b98c6')
  const success = cssVar('--success', '#4aaf7c')
  return {
    grid: { left: 56, right: 16, top: 32, bottom: 28 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['输入 tokens', '输出 tokens'], textStyle: { color: text }, top: 0 },
    xAxis: {
      type: 'category',
      data: rows.map((d) => d.date.slice(5)),
      axisLabel: { color: text },
      axisLine: { lineStyle: { color: line } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: text },
      splitLine: { lineStyle: { color: split } },
    },
    series: [
      {
        name: '输入 tokens',
        type: 'bar',
        stack: 'tokens',
        barMaxWidth: 22,
        itemStyle: { color: accent },
        data: rows.map((d) => d.prompt_tokens),
      },
      {
        name: '输出 tokens',
        type: 'bar',
        stack: 'tokens',
        barMaxWidth: 22,
        itemStyle: { color: success, borderRadius: [3, 3, 0, 0] },
        data: rows.map((d) => d.completion_tokens),
      },
    ],
  }
})

function formatTokens(value) {
  return Number(value || 0).toLocaleString()
}

function formatCost(value) {
  return value == null ? '—' : Number(value).toFixed(4)
}
</script>

<template>
  <div class="token-usage">
    <div class="usage-toolbar">
      <SegmentedControl v-model="days" :options="rangeOptions" size="sm" />
      <span v-if="loading" class="muted usage-loading">加载中…</span>
    </div>

    <p v-if="failed" class="muted usage-failed">用量数据加载失败，请稍后重试。</p>

    <EmptyState
      v-else-if="!loading && usage && !hasData"
      compact
      icon="assistant"
      title="暂无用量记录"
      hint="与助手对话后，这里会统计每日 tokens 与各模型调用情况。"
    />

    <template v-else-if="usage && hasData">
      <BaseChart v-if="chartOption" :option="chartOption" height="220px" />

      <div v-if="usage.models?.length" class="usage-table-wrap">
        <table class="usage-table">
          <thead>
            <tr>
              <th>模型</th>
              <th>调用次数</th>
              <th>输入 tokens</th>
              <th>输出 tokens</th>
              <th>合计</th>
              <th>估算成本</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in usage.models" :key="`${m.provider}/${m.model}`">
              <td class="model-cell">
                <span class="model-name">{{ m.model }}</span>
                <span class="muted model-provider">{{ m.provider }}</span>
              </td>
              <td>{{ formatTokens(m.call_count) }}</td>
              <td>{{ formatTokens(m.prompt_tokens) }}</td>
              <td>{{ formatTokens(m.completion_tokens) }}</td>
              <td>{{ formatTokens(m.total_tokens) }}</td>
              <td>{{ formatCost(m.estimated_cost) }}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td>合计</td>
              <td>{{ formatTokens(usage.models.reduce((s, m) => s + (m.call_count || 0), 0)) }}</td>
              <td>{{ formatTokens(usage.total_prompt_tokens) }}</td>
              <td>{{ formatTokens(usage.total_completion_tokens) }}</td>
              <td>{{ formatTokens(usage.total_tokens) }}</td>
              <td>{{ formatCost(usage.total_estimated_cost) }}</td>
            </tr>
          </tfoot>
        </table>
      </div>

      <p v-if="usage.untracked_calls > 0" class="usage-note muted">
        {{ usage.untracked_calls }} 次调用未返回用量，未计入统计
      </p>
      <p class="usage-note muted cost-note">成本按配置价目估算，以服务商账单为准</p>
    </template>
  </div>
</template>

<style scoped>
.token-usage {
  display: grid;
  gap: 12px;
}

.usage-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
}

.usage-loading,
.usage-failed {
  font-size: 12px;
}

.usage-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
}

.usage-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  white-space: nowrap;
}

.usage-table th,
.usage-table td {
  padding: 8px 10px;
  text-align: right;
  border-bottom: 1px solid var(--border);
  color: var(--text);
}

.usage-table th:first-child,
.usage-table td:first-child {
  text-align: left;
}

.usage-table th {
  color: var(--text-soft);
  font-weight: 700;
}

.usage-table tbody tr:last-child td {
  border-bottom: none;
}

.usage-table tfoot td {
  border-top: 1px solid var(--border-strong);
  border-bottom: none;
  font-weight: 800;
}

.model-cell {
  display: grid;
  gap: 2px;
}

.model-name {
  font-weight: 650;
}

.model-provider {
  font-size: 11px;
}

.usage-note {
  margin: 0;
  font-size: 12px;
}

.cost-note {
  text-align: right;
}
</style>
