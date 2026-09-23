<script setup lang="ts">
/**
 * 待发送队列条：run 进行中入队的消息在输入框上方逐条预览，可单条删除。
 * 队列为空时不渲染；run 正常收敛（非 error/cancelled）后由 conversation store 自动依次发出。
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
  <div v-if="conv.queuedMessages.length" class="queue-bar" role="status" aria-label="待发送队列">
    <div class="queue-title">待发送 · {{ conv.queuedMessages.length }}</div>
    <ul class="queue-list">
      <li v-for="(message, index) in conv.queuedMessages" :key="`${index}-${message}`" class="queue-item">
        <span class="queue-text" :title="message">{{ preview(message) }}</span>
        <button class="queue-x" :title="`移除第 ${index + 1} 条待发消息`" @click="conv.removeQueuedMessage(index)">
          <AppIcon name="x" :size="11" />
        </button>
      </li>
    </ul>
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
.queue-x:hover {
  color: var(--terra-soft);
}
</style>
