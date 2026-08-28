<script setup>
// 阶段 C1：Plan Mode 计划卡片。
// 渲染 agent 提交的结构化计划（标题 + 步骤清单 + 影响日期），
// 支持：勾选去掉某步、点编辑改文字、批准执行 / 拒绝。
// 批准时把（可能编辑过的）steps 通过 approve 事件回传父组件，由父组件调 /ai/plan/{id}/approve。
import { computed, ref, watch } from 'vue'
import ArtIcon from '../../components/ArtIcon.vue'

const props = defineProps({
  planCard: { type: Object, required: true },
  messageId: { type: [Number, String], default: null },
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['approve', 'reject'])

// 本地可编辑副本：steps 支持勾选去掉 / 编辑文本
const editableSteps = ref([])
const removed = ref(new Set())

watch(
  () => props.planCard,
  (pc) => {
    if (!pc) return
    editableSteps.value = (pc.steps || []).map((s, i) => ({
      action: s.action || '',
      tool: s.tool || '',
      args_preview: s.args_preview || '',
      rationale: s.rationale || '',
      _idx: i,
    }))
    removed.value = new Set()
  },
  { immediate: true, deep: false },
)

const status = computed(() => props.planCard?.status || 'pending')
const statusLabel = computed(() => {
  const map = { pending: '待审阅', approved: '已批准', rejected: '已拒绝' }
  return map[status.value] || status.value
})
const activeSteps = computed(() => editableSteps.value.filter((_, i) => !removed.value.has(i)))

function toggleStep(idx) {
  if (removed.value.has(idx)) removed.value.delete(idx)
  else removed.value.add(idx)
  // 触发响应式更新
  removed.value = new Set(removed.value)
}

function approve() {
  emit('approve', {
    messageId: props.messageId,
    steps: activeSteps.value.map((s) => ({
      action: s.action,
      tool: s.tool,
      args_preview: s.args_preview,
      rationale: s.rationale,
    })),
  })
}

function reject() {
  emit('reject', { messageId: props.messageId, reason: '' })
}
</script>

<template>
  <section class="plan-card" :data-status="status">
    <header class="plan-head">
      <ArtIcon name="flag" tone="aqua" :size="20" />
      <div class="plan-title">
        <strong>{{ planCard.title || '计划' }}</strong>
        <small v-if="planCard.affected_days?.length">影响 {{ planCard.affected_days.length }} 天</small>
      </div>
      <span class="plan-status" :data-status="status">{{ statusLabel }}</span>
    </header>

    <ol class="plan-steps">
      <li
        v-for="(step, idx) in editableSteps"
        :key="step._idx"
        class="plan-step"
        :class="{ removed: removed.has(idx) }"
      >
        <label class="step-check" :title="removed.has(idx) ? '恢复这一步' : '去掉这一步'">
          <input type="checkbox" :checked="!removed.has(idx)" @change="toggleStep(idx)" />
        </label>
        <div class="step-body">
          <input
            v-model="step.action"
            class="step-input step-action"
            :disabled="status !== 'pending' || busy"
            placeholder="动作描述"
          />
          <div class="step-meta">
            <span class="step-tool">{{ step.tool }}</span>
            <input
              v-if="step.args_preview"
              v-model="step.args_preview"
              class="step-input step-args"
              :disabled="status !== 'pending' || busy"
            />
          </div>
          <p v-if="step.rationale" class="step-rationale">{{ step.rationale }}</p>
        </div>
      </li>
    </ol>

    <footer v-if="status === 'pending'" class="plan-actions">
      <button type="button" class="primary" :disabled="busy || !activeSteps.length" @click="approve">
        <ArtIcon name="check" tone="on-accent" :size="16" />
        <span>批准执行（{{ activeSteps.length }} 步）</span>
      </button>
      <button type="button" class="ghost" :disabled="busy" @click="reject">
        <ArtIcon name="close" tone="pearl" :size="16" />
        <span>拒绝</span>
      </button>
    </footer>
    <p v-else-if="status === 'approved'" class="plan-outcome approved">✓ 计划已批准并执行</p>
    <p v-else-if="status === 'rejected'" class="plan-outcome rejected">✗ 计划已拒绝</p>
  </section>
</template>

<style scoped>
.plan-card {
  margin: 10px 0;
  padding: 14px;
  border: 1px solid color-mix(in srgb, var(--accent) 35%, var(--border));
  border-radius: var(--radius);
  background: color-mix(in srgb, var(--accent) 6%, var(--surface-2));
}

.plan-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.plan-title {
  flex: 1;
  min-width: 0;
}

.plan-title strong {
  display: block;
  font-size: 14px;
  color: var(--text);
}

.plan-title small {
  color: var(--text-soft);
  font-size: 11px;
}

.plan-status {
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  font-size: 11px;
  font-weight: 700;
  background: color-mix(in srgb, var(--accent) 20%, transparent);
  color: var(--accent-strong);
}

.plan-status[data-status='approved'] {
  background: color-mix(in srgb, var(--success) 20%, transparent);
  color: var(--success);
}

.plan-status[data-status='rejected'] {
  background: color-mix(in srgb, var(--danger) 20%, transparent);
  color: var(--danger);
}

.plan-steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 8px;
}

.plan-step {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 8px;
  padding: 8px;
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--surface-solid) 70%, transparent);
}

.plan-step.removed {
  opacity: 0.4;
}

.step-check input {
  margin-top: 3px;
  cursor: pointer;
}

.step-body {
  min-width: 0;
}

.step-action {
  width: 100%;
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
}

.step-meta {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-top: 4px;
  flex-wrap: wrap;
}

.step-tool {
  padding: 1px 6px;
  border-radius: var(--radius-xs);
  background: color-mix(in srgb, var(--accent) 15%, transparent);
  color: var(--accent-strong);
  font-size: 10px;
  font-weight: 800;
  font-family: var(--font-mono, monospace);
}

.step-input {
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-soft);
  font-size: 11px;
  padding: 1px 4px;
  border-radius: var(--radius-xs);
}

.step-input:focus:not(:disabled) {
  border-color: var(--accent);
  background: var(--surface);
}

.step-args {
  flex: 1;
  min-width: 80px;
}

.step-rationale {
  margin: 4px 0 0;
  color: var(--text-muted);
  font-size: 11px;
}

.plan-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.plan-outcome {
  margin: 10px 0 0;
  font-size: 12px;
  font-weight: 700;
}

.plan-outcome.approved {
  color: var(--success);
}

.plan-outcome.rejected {
  color: var(--danger);
}
</style>
