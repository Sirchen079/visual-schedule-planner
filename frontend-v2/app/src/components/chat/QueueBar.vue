<script setup lang="ts">
/**
 * 插话与待发送条：run 进行中的两类暂存消息在输入框上方逐条预览。
 * - 插话（steerEntries）：已 POST 到活跃 run 的注入队列，「待注入」→ steer_accepted 确认后
 *   变「已注入」；仅 POST 尚未返回的条目可撤回（中断请求并移除），已受理的不可撤回。
 * - 待发队列（queuedMessages）：远端 run / 回退场景的 v1 队列，run 正常收敛后自动依次发出。
 * 两者皆空时不渲染；撤回按钮对已受理条目禁用（AI 一定会看到，撤回会造成 UI 与模型认知不一致）。
 */
import { useConversationStore } from '../../stores/conversation'
import AppIcon from '../AppIcon.vue'

const conv = useConversationStore()

/** 单行预览：换行压成空格，超长截断交给 CSS ellipsis。 */
function preview(text: string): string {
  return text.replace(/\s+/g, ' ')
}
</script>

<template>
  <div v-if="conv.steerEntries.length || conv.queuedMessages.length" class="queue-bar" role="status" aria-label="插话与待发送消息">
    <template v-if="conv.steerEntries.length">
      <div class="queue-title">插话 · {{ conv.steerEntries.length }}</div>
      <ul class="queue-list">
        <li v-for="entry in conv.steerEntries" :key="entry.token" class="queue-item">
          <span class="steer-tag" :data-confirmed="entry.messageId !== null">{{ entry.messageId !== null ? '已注入' : '待注入' }}</span>
          <span class="queue-text" :title="entry.text">{{ preview(entry.text) }}</span>
          <button
            class="queue-x"
            :disabled="entry.runId !== null || entry.messageId !== null"
            :title="entry.runId !== null || entry.messageId !== null ? '已被知时接收，无法撤回' : '撤回这条插话'"
            :aria-label="entry.runId !== null || entry.messageId !== null ? '插话已被接收，无法撤回' : '撤回这条插话'"
            @click="conv.withdrawSteer(entry.token)"
          >
            <AppIcon name="x" :size="11" />
          </button>
        </li>
      </ul>
    </template>
    <template v-if="conv.queuedMessages.length">
      <div class="queue-title">待发送 · {{ conv.queuedMessages.length }}</div>
      <ul class="queue-list">
        <li v-for="(message, index) in conv.queuedMessages" :key="`${index}-${message}`" class="queue-item">
          <span class="queue-text" :title="message">{{ preview(message) }}</span>
          <button class="queue-x" :title="`移除第 ${index + 1} 条待发消息`" @click="conv.removeQueuedMessage(index)">
            <AppIcon name="x" :size="11" />
          </button>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.queue-bar {
  flex: none;
  margin: 0 22px 4px;
  padding: 8px 10px;
  border: 1px dashed var(--line-2);
  border-radius: var(--radius-l);
  background: var(--bg-raise);
  font-size: 12px;
  color: var(--ink-2);
}
.queue-title {
  color: var(--ink-3);
  letter-spacing: 0.02em;
}
.queue-title + .queue-title {
  margin-top: 6px;
}
.queue-list {
  margin: 4px 0 0;
  padding: 0;
  list-style: none;
}
.queue-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 0;
}
.steer-tag {
  flex: none;
  font-size: 11px;
  letter-spacing: 0.02em;
  border: 1px dashed var(--amber-border-dim, var(--line-2));
  border-radius: var(--radius-pill);
  padding: 0 7px;
  color: var(--amber-soft, var(--ink-3));
  line-height: 18px;
  user-select: none;
}
.steer-tag[data-confirmed] {
  border-style: solid;
  border-color: var(--line-2);
  color: var(--ink-3);
}
.queue-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.queue-x {
  display: flex;
  padding: 2px;
  color: var(--ink-3);
  flex: none;
}
.queue-x:hover:not(:disabled) {
  color: var(--terra-soft);
}
.queue-x:disabled {
  opacity: var(--ctl-disabled-opacity, 0.45);
  cursor: not-allowed;
}
</style>
