<script setup lang="ts">
/**
 * 活性状态条（常驻）：
 * 八阶段中文标签 + 心跳/本地时钟刷新「已进行 Xs」 + usage token 累计。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRunStore } from '../../stores/run'

const run = useRunStore()

/** 活跃期间每秒走一次本地时钟，心跳间隔内「已进行」也能连续走秒。 */
const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | null = null

watch(
  () => run.isActive,
  (active) => {
    if (active && timer === null) timer = setInterval(() => (now.value = Date.now()), 1000)
    if (!active && timer !== null) {
      clearInterval(timer)
      timer = null
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  if (timer !== null) clearInterval(timer)
})

const elapsedText = computed<string | null>(() => {
  if (run.lastHeartbeat) {
    const ms = run.lastHeartbeat.elapsedMs + Math.max(0, now.value - run.lastHeartbeat.at)
    return `${(ms / 1000).toFixed(1)}s`
  }
  if (run.startedAt && run.isActive) return `${((now.value - run.startedAt) / 1000).toFixed(1)}s`
  if (run.runCompleted) return `${(run.runCompleted.elapsedMs / 1000).toFixed(1)}s`
  return null
})

const phaseText = computed(() => {
  switch (run.phase) {
    case 'idle':
      return '待命'
    case 'streaming':
      return run.stageLabel ?? '进行中'
    case 'awaiting_approval':
      return '等待审批'
    case 'completed':
      return '已完成'
    case 'error':
      return '出错了'
    case 'cancelled':
      return '已取消'
  }
})

const usageText = computed(() => {
  const u = run.usage
  if (!u || (u.tokensIn === 0 && u.tokensOut === 0)) return null
  return `↑ ${u.tokensIn.toLocaleString()} in · ↓ ${u.tokensOut.toLocaleString()} out`
})

const dotTone = computed(() => {
  if (run.phase === 'awaiting_approval') return 'terra'
  if (run.phase === 'error') return 'terra'
  if (run.phase === 'streaming') return 'amber'
  if (run.phase === 'completed') return 'ok'
  return 'dim'
})
</script>

<template>
  <div class="runbar" :data-active="run.isActive">
    <span class="rpulse" :data-tone="dotTone" />
    <span class="phase" :data-tone="dotTone">{{ phaseText }}</span>
    <template v-if="elapsedText">
      <span class="sep">·</span>
      <span class="elapsed">已进行 {{ elapsedText }}</span>
    </template>
    <span v-if="usageText" class="tok">{{ usageText }}</span>
  </div>
</template>

<style scoped>
.runbar {
  flex: none;
  height: 34px;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0 24px;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  background: var(--bg-runbar);
  font-size: 12px;
  color: var(--ink-2);
  white-space: nowrap;
  overflow: hidden;
}
.rpulse {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: none;
}
.rpulse[data-tone='amber'] {
  background: var(--amber);
  animation: pulse 2s infinite;
}
.rpulse[data-tone='terra'] {
  background: var(--terra);
  animation: pulse 1.8s infinite;
}
.rpulse[data-tone='ok'] {
  background: var(--ok);
}
.rpulse[data-tone='dim'] {
  background: var(--ink-3);
  opacity: 0.6;
}
.phase {
  font-weight: 600;
  color: var(--amber-soft);
}
.phase[data-tone='terra'] {
  color: var(--terra-soft);
}
.phase[data-tone='dim'] {
  color: var(--ink-3);
}
.sep {
  color: var(--ink-ghost);
}
.elapsed {
  font-variant-numeric: tabular-nums;
}
.tok {
  margin-left: auto;
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ink-3);
  font-variant-numeric: tabular-nums;
}
@keyframes pulse {
  0% {
    box-shadow: 0 0 0 0 var(--amber-pulse);
  }
  70% {
    box-shadow: 0 0 0 7px var(--amber-pulse-end);
  }
  100% {
    box-shadow: 0 0 0 0 var(--amber-pulse-end);
  }
}
</style>
