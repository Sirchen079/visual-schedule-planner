<script setup>
// 历史会话区：加载态 / 空态 / 会话条目列表。打开会话与新聊天由 AssistantView 处理。
// 后端目前不提供删除会话接口（api/ai.js 无 DELETE /conversations），故条目无删除按钮。
import ArtIcon from '../../components/ArtIcon.vue'
import AppSpinner from '../../components/ui/AppSpinner.vue'
import EmptyState from '../../components/ui/EmptyState.vue'

defineProps({
  conversations: { type: Array, default: () => [] },
  historyLoading: { type: Boolean, default: false },
  activeId: { type: [Number, String], default: null },
  interactionBusy: { type: Boolean, default: false },
})
defineEmits(['open', 'new-chat'])

function formatHistoryTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<template>
  <section class="card history-panel">
    <div class="history-head">
      <div>
        <h3>历史会话</h3>
        <p class="muted">保留最近 50 次会话，点击可回溯上下文。</p>
      </div>
      <button class="ghost compact" :disabled="interactionBusy" @click="$emit('new-chat')">
        <ArtIcon name="plus" tone="aqua" :size="16" />
        <span>新聊天</span>
      </button>
    </div>

    <div v-if="historyLoading" class="history-empty">
      <AppSpinner size="md" label="正在加载历史..." />
    </div>
    <EmptyState
      v-else-if="!conversations.length"
      class="history-grow"
      icon="assistant"
      title="暂无历史会话"
      hint="新的对话会自动保存在这里，点击条目可回溯上下文。"
    />
    <div v-else class="history-list" role="list">
      <button
        v-for="row in conversations"
        :key="row.id"
        class="history-row"
        :class="{ active: row.id === activeId }"
        type="button"
        @click="$emit('open', row)"
      >
        <span class="history-title">{{ row.title || '新的会话' }}</span>
        <span class="history-snippet">{{ row.last_message || '暂无消息' }}</span>
        <span class="history-meta">
          {{ formatHistoryTime(row.updated_at) }} · {{ row.message_count }} 条
        </span>
      </button>
    </div>
  </section>
</template>

<style scoped>
.history-grow {
  flex: 1;
}
</style>
