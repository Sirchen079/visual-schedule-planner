<script setup lang="ts">
/**
 * 工具卡片：tool_call_started → args_delta 流式填参 → tool_call_result 落定。
 * 可展开（默认展开参数，约束 2：工具调用必须可见）；MCP 工具名按 __ 切分显示来源徽标。
 */
import { computed } from 'vue'
import type { ToolCallItem } from '../../stores/run'
import AppIcon from '../AppIcon.vue'

const props = defineProps<{ call: ToolCallItem }>()

/** mcp__{server}__{tool} → 来源徽标 + 短名；普通工具原样显示。 */
function splitToolName(name: string): { server: string | null; short: string } {
  if (name.startsWith('mcp__')) {
    const parts = name.split('__')
    if (parts.length >= 3) return { server: parts[1], short: parts.slice(2).join('__') }
  }
  return { server: null, short: name }
}

const parsedName = computed(() => splitToolName(props.call.tool))

const durationText = computed(() => {
  const ms = props.call.durationMs
  if (ms === null) return ''
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
})

const stateText = computed(() => {
  switch (props.call.status) {
    case 'pending': return '等待审批'
    case 'interrupted': return '已中断 · 结果未确认'
    case 'running':
      return '执行中'
    case 'ok':
      return `已完成 · ${durationText.value}`
    case 'error':
      return `失败 · ${durationText.value}`
  }
})
</script>

<template>
  <!-- 原生 open 属性：默认展开（约束 2），用户可手动折叠 -->
  <details class="tool" open>
    <summary>
      <AppIcon name="chevron-down" class="tw" :size="13" />
      <AppIcon v-if="call.status === 'ok'" name="check" class="i-ok" :size="15" />
      <AppIcon v-else-if="call.status === 'error'" name="alert" class="i-err" :size="15" />
      <span v-else-if="call.status === 'running'" class="i-run" /><AppIcon v-else name="shield" :size="15" />
      <span v-if="parsedName.server" class="badge">{{ parsedName.server }}</span>
      <span class="tname">{{ parsedName.short }}</span>
      <span class="tstate" :data-running="call.status === 'running'">{{ stateText }}</span>
    </summary>
    <div class="tinner">
      <div class="code args">{{ call.argsPreview || '（参数待流式填入）' }}</div>
      <div v-if="call.status !== 'running' && call.resultPreview" class="result">
        <span class="rdot" :data-error="call.status === 'error'" />
        <span class="rtext">{{ call.resultPreview }}</span>
      </div>
    </div>
  </details>
</template>

<style scoped>
.tool {
  border: 1px solid var(--line-2);
  border-radius: var(--radius-m);
  background: var(--bg-raise);
  overflow: hidden;
  flex: none;
}
summary {
  list-style: none;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 9px 12px;
  cursor: pointer;
  user-select: none;
}
summary::-webkit-details-marker {
  display: none;
}
.tw {
  color: var(--ink-3);
  flex: none;
  transition: transform 0.15s;
}
.tool[open] .tw {
  transform: rotate(180deg);
}
.i-ok {
  color: var(--ok);
  flex: none;
}
.i-err {
  color: var(--terra-soft);
  flex: none;
}
.i-run {
  width: 13px;
  height: 13px;
  border-radius: 50%;
  border: 2px solid var(--amber);
  border-top-color: transparent;
  animation: spin 0.9s linear infinite;
  flex: none;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.badge {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--amber-soft);
  border: 1px solid var(--amber-border-dim);
  background: var(--amber-wash);
  border-radius: var(--radius-pill);
  padding: 0 8px;
  line-height: 18px;
  flex: none;
}
.tname {
  font-family: var(--mono);
  font-size: 12.5px;
  color: var(--tool-name);
  word-break: break-all;
}
.tstate {
  margin-left: auto;
  font-size: 12px;
  color: var(--ink-3);
  display: flex;
  align-items: center;
  gap: 5px;
  flex: none;
  font-variant-numeric: tabular-nums;
}
.tstate[data-running='true'] {
  color: var(--amber-soft);
}
.tinner {
  padding: 1px 12px 10px;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.code {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--tool-code);
  background: var(--bg-sink);
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  padding: 7px 11px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 180px;
  overflow: auto;
}
.result {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
  color: var(--ink-2);
}
.rdot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ok);
  flex: none;
  margin-top: 7px;
}
.rdot[data-error='true'] {
  background: var(--terra);
}
.rtext {
  font-family: var(--mono);
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 132px;
  overflow: auto;
}
</style>
