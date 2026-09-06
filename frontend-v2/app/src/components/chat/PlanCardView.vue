<script setup lang="ts">
/**
 * 计划卡：plan_card 事件渲染。批准走
 * POST /ai/conversations/{cid}/plans/{plan_id}/approve（响应即新 run 的 SSE 流），
 * 拒绝走同路径 /reject（普通 REST）。
 */
import { computed } from 'vue'
import type { PlanCardItem } from '../../stores/run'
import { useRunStore } from '../../stores/run'
import AppIcon from '../AppIcon.vue'

const props = defineProps<{ plan: PlanCardItem }>()
const run = useRunStore()

interface StepRow {
  action: string
  tool: string
  reason: string
}

const steps = computed<StepRow[]>(() =>
  props.plan.steps.map((s) => ({
    action: typeof s.action === 'string' ? s.action : JSON.stringify(s),
    tool: typeof s.tool === 'string' ? s.tool : '',
    reason: typeof s.reason === 'string' ? s.reason : '',
  })),
)
</script>

<template>
  <div class="plan">
    <div class="phead">
      <AppIcon name="list" class="i" :size="15" />
      <span class="t">执行计划</span>
      <span class="pid">#{{ plan.planId }}</span>
      <span class="title">{{ plan.title }}</span>
    </div>
    <ol class="steps">
      <li v-for="(s, i) in steps" :key="i">
        <span class="no">{{ i + 1 }}</span>
        <span class="action">{{ s.action }}</span>
        <span v-if="s.tool" class="mtool">{{ s.tool }}</span>
      </li>
    </ol>
    <div class="btns">
      <button class="btn-ok" :disabled="run.hasLiveStream()" @click="run.approvePlan()">批准计划</button>
      <button class="btn-no" :disabled="run.hasLiveStream()" @click="run.rejectPlan()">拒绝</button>
    </div>
  </div>
</template>

<style scoped>
.plan {
  border: 1px solid var(--amber-border-mid);
  border-radius: var(--radius-l);
  background: var(--bg-raise);
  padding: 13px 16px 13px;
  display: flex;
  flex-direction: column;
  gap: 9px;
  flex: none;
}
.phead {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.i {
  color: var(--amber-soft);
  flex: none;
}
.t {
  font-size: 14px;
  font-weight: 600;
  color: var(--amber-soft);
  flex: none;
}
.pid {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ink-3);
  flex: none;
}
.title {
  font-size: 13px;
  color: var(--ink-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.steps {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 220px;
  overflow: auto;
}
.steps li {
  display: flex;
  align-items: baseline;
  gap: 9px;
  font-size: 13.5px;
  line-height: 1.55;
}
.no {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--amber-dim);
  flex: none;
  min-width: 16px;
  text-align: right;
}
.action {
  color: var(--ink);
}
.mtool {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ink-3);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-pill);
  padding: 0 8px;
  flex: none;
}
.btns {
  display: flex;
  gap: 9px;
  margin-top: 2px;
}
.btn-ok {
  height: 32px;
  padding: 0 20px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 700;
  color: var(--btn-ok-text);
  background: var(--btn-ok-bg);
  letter-spacing: 0.04em;
}
.btn-ok:hover {
  filter: brightness(1.05);
}
.btn-no {
  height: 32px;
  padding: 0 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--btn-no-text);
  border: 1px solid var(--line-2);
}
.btn-no:hover {
  border-color: var(--line-hover);
}
</style>
