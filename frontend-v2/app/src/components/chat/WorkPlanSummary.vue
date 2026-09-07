<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ steps: Array<Record<string, unknown>> }>()
const completed = computed(() => props.steps.filter(step => step.status === '已完成').length)
</script>

<template>
  <details v-if="steps.length" class="work-plan">
    <summary>执行计划 <span>{{ completed }} / {{ steps.length }}</span></summary>
    <ol>
      <li v-for="(step, index) in steps" :key="index">
        <span class="step-title">{{ step.title }}</span>
        <span class="step-status">{{ step.status || '待办' }}</span>
        <small v-if="step.status === '已完成'" :data-backed="step.verification === 'tool_receipt'">
          {{ step.verification === 'tool_receipt' ? '有执行记录' : 'AI 汇报' }}
        </small>
      </li>
    </ol>
    <p>展开对话中的工具记录，可查看执行结果。</p>
  </details>
</template>

<style scoped>
.work-plan { margin: 12px 18px; border: 1px solid var(--line); border-radius: 10px; color: var(--ink-2); font-size: 12px; }
summary { padding: 10px 12px; cursor: pointer; font-weight: 600; }
summary span { float: right; font-family: var(--mono); color: var(--ink-3); }
ol { margin: 0; padding: 0 12px 0 30px; max-height: 180px; overflow: auto; }
li { padding: 6px 0; overflow-wrap: anywhere; }
.step-title { margin-right: 8px; }
.step-status { color: var(--ink-3); white-space: nowrap; }
small { display: inline-block; margin-left: 6px; color: var(--ink-3); }
small[data-backed="true"] { color: var(--ink-2); }
p { margin: 0; padding: 8px 12px 12px; color: var(--ink-3); font-size: 11px; line-height: 1.5; }
</style>
