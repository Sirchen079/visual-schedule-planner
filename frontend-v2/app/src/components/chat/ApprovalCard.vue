<script setup lang="ts">
/**
 * 审批卡（安全边界，final-shell 里的「台灯下待签字的单据」）：
 * tool_approval_requested 渲染（M3.5 起以审批账目驱动，同流多卡并存，每张独立批准/拒绝）；
 * 批准前绝不显示为已完成；批准/始终允许/拒绝 → run store 按卡上的 actionId 调对应端点，
 * ready_to_resume=false 时停留等待（显示图章），同批结清后才开 resume 新流续跑。
 * 已批准/已拒绝卡保留图章（与日历幽灵块图章语言一致），直到下一轮新 run 清账。
 */
import { computed, ref } from 'vue'
import type { PendingApproval } from '../../stores/run'
import { useRunStore } from '../../stores/run'
import AppIcon from '../AppIcon.vue'

const props = defineProps<{ approval: PendingApproval }>()

const run = useRunStore()
const busy = ref(false)

const resolved = computed(() => props.approval.outcome)
const resolvedText = computed(() => {
  switch (props.approval.outcome) {
    case 'approved':
      return '已批准'
    case 'denied':
      return '已拒绝'
    case 'expired':
      return '已过期'
    default:
      return ''
  }
})

/** args → 键值表（值统一 JSON 化并截断超长项）。 */
const argRows = computed(() =>
  Object.entries(props.approval.args).map(([k, v]) => ({
    key: k,
    value: typeof v === 'string' ? v : JSON.stringify(v, null, 0) ?? String(v),
  })),
)

/** preview 为空时（后端当前不填 preview），从常见字段给一行可读摘要。 */
const headline = computed(() => {
  if (props.approval.preview) return props.approval.preview
  const a = props.approval.args
  const subject = [a.title, a.name, a.content, a.text].find((v) => typeof v === 'string' && v)
  return subject ? `操作对象：${subject}` : ''
})

async function act(fn: () => Promise<void>): Promise<void> {
  if (busy.value || resolved.value) return
  busy.value = true
  try {
    await fn()
  } finally {
    busy.value = false
  }
}

const approve = () => act(() => run.approve(props.approval.actionId, false))
const approveAlways = () => act(() => run.approve(props.approval.actionId, true))
const reject = () => act(() => run.reject(props.approval.actionId))
</script>

<template>
  <div class="approve" :data-action-id="approval.actionId" :data-resolved="resolved ? resolved : undefined" :data-busy="busy">
    <div class="ahead">
      <AppIcon name="shield" class="i-shield" :size="16" />
      <span class="a1">需要你的批准</span>
      <span v-if="!resolved" class="apend"><span class="pulse" />待处理</span>
      <span v-else class="apend resolved">{{ resolvedText }}</span>
    </div>
    <div class="atool">{{ approval.tool }}</div>
    <div class="preview">
      <div v-if="headline" class="p1">{{ headline }}</div>
      <table class="args">
        <tbody>
          <tr v-for="row in argRows" :key="row.key">
            <th>{{ row.key }}</th>
            <td>{{ row.value }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="!resolved" class="btns">
      <button class="btn-ok" :disabled="busy || run.hasLiveStream()" @click="approve">批准</button>
      <button class="btn-no" :disabled="busy || run.hasLiveStream()" @click="reject">拒绝</button>
      <button v-if="approval.grantAvailable" class="btn-always" :disabled="busy || run.hasLiveStream()" @click="approveAlways">
        始终允许
      </button>
    </div>
  </div>
</template>

<style scoped>
.approve {
  border: 1px solid var(--approve-border);
  border-radius: var(--radius-l);
  padding: 14px 16px 13px;
  display: flex;
  flex-direction: column;
  gap: 9px;
  background: var(--approve-gradient), var(--bg-approve);
  box-shadow:
    0 0 0 1px var(--glow-ring),
    0 6px 30px var(--glow-blur);
  animation: glow-pulse 3.2s ease-in-out infinite;
  flex: none;
}
.approve[data-resolved] {
  animation: none;
  border-color: var(--line-2);
  box-shadow: none;
  background: var(--bg-raise);
}
.approve[data-busy='true'] {
  opacity: 0.75;
  pointer-events: none;
}
@keyframes glow-pulse {
  0%,
  100% {
    box-shadow:
      0 0 0 1px var(--glow-ring),
      0 6px 26px var(--glow-blur);
  }
  50% {
    box-shadow:
      0 0 0 1px var(--glow-ring-strong),
      0 6px 36px var(--glow-blur-strong);
  }
}
.ahead {
  display: flex;
  align-items: center;
  gap: 8px;
}
.i-shield {
  color: var(--approve-icon);
  flex: none;
}
.a1 {
  font-size: 14px;
  font-weight: 600;
  color: var(--approve-title);
}
.apend {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  font-weight: 600;
  color: var(--terra-soft);
}
.apend.resolved {
  color: var(--ink-3);
}
.pulse {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--terra);
  animation: pulse 1.8s infinite;
}
.atool {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--ink-3);
  margin-top: -4px;
}
.preview {
  background: var(--bg-preview);
  border: 1px solid var(--approve-border-soft);
  border-radius: 8px;
  padding: 10px 13px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.p1 {
  font-size: 15px;
  font-weight: 600;
  color: var(--approve-p1);
  line-height: 1.4;
}
.args {
  border-collapse: collapse;
  display: block;
  max-height: 180px;
  overflow: auto;
}
.args th {
  text-align: left;
  font-family: var(--mono);
  font-size: 11.5px;
  font-weight: 500;
  color: var(--amber-dim);
  padding: 2px 12px 2px 0;
  vertical-align: top;
  white-space: nowrap;
}
.args td {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--tool-code);
  line-height: 1.55;
  word-break: break-all;
}
.btns {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-top: 2px;
}
.btn-ok {
  height: 34px;
  padding: 0 24px;
  border-radius: 8px;
  font-size: 13.5px;
  font-weight: 700;
  color: var(--btn-ok-text);
  background: var(--btn-ok-bg);
  letter-spacing: 0.04em;
}
.btn-ok:hover {
  filter: brightness(1.05);
}
.btn-no {
  height: 34px;
  padding: 0 19px;
  border-radius: 8px;
  font-size: 13.5px;
  font-weight: 500;
  color: var(--btn-no-text);
  background: transparent;
  border: 1px solid var(--line-2);
}
.btn-no:hover {
  border-color: var(--line-hover);
}
.btn-always {
  margin-left: auto;
  font-size: 12.5px;
  color: var(--approve-always);
  text-decoration: underline dotted;
  text-underline-offset: 3px;
}
</style>
