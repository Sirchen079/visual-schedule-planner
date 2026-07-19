<script setup>
// 历史会话区：加载态 / 空态 / 会话条目列表。打开会话与新聊天由 AssistantView 处理。
// 条目支持行内重命名与删除（确认流程在 AssistantView），操作结果经 emit 上抛。
import { nextTick, ref } from 'vue'
import ArtIcon from '../../components/ArtIcon.vue'
import AppSpinner from '../../components/ui/AppSpinner.vue'
import EmptyState from '../../components/ui/EmptyState.vue'

defineProps({
  conversations: { type: Array, default: () => [] },
  historyLoading: { type: Boolean, default: false },
  activeId: { type: [Number, String], default: null },
  interactionBusy: { type: Boolean, default: false },
})
const emit = defineEmits(['open', 'new-chat', 'rename', 'delete'])

// 行内重命名：editingId 非空时该行变为输入框；回车确认、Esc 取消
const editingId = ref(null)
const editingTitle = ref('')
const editInput = ref(null)

function startRename(row) {
  editingId.value = row.id
  editingTitle.value = row.title || ''
  nextTick(() => editInput.value?.[0]?.focus())
}

function confirmRename(row) {
  const next = editingTitle.value.trim()
  editingId.value = null
  if (next && next !== row.title) emit('rename', row, next)
}

function cancelRename() {
  editingId.value = null
}

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
      <div
        v-for="row in conversations"
        :key="row.id"
        class="history-row"
        :class="{ active: row.id === activeId }"
      >
        <div v-if="editingId === row.id" class="history-rename">
          <input
            ref="editInput"
            v-model="editingTitle"
            class="rename-input"
            maxlength="200"
            @keydown.enter.prevent="confirmRename(row)"
            @keydown.esc.prevent="cancelRename"
            @blur="confirmRename(row)"
          />
        </div>
        <button v-else class="history-main" type="button" @click="$emit('open', row)">
          <span class="history-title">{{ row.title || '新的会话' }}</span>
          <span class="history-snippet">{{ row.last_message || '暂无消息' }}</span>
          <span class="history-meta">
            {{ formatHistoryTime(row.updated_at) }} · {{ row.message_count }} 条
          </span>
        </button>
        <div v-if="editingId !== row.id" class="history-actions">
          <button
            class="ghost compact"
            type="button"
            :disabled="interactionBusy"
            @click.stop="startRename(row)"
          >
            重命名
          </button>
          <button
            class="ghost compact danger-text"
            type="button"
            :disabled="interactionBusy"
            @click.stop="$emit('delete', row)"
          >
            删除
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.history-grow {
  flex: 1;
}

.history-row {
  position: relative;
  display: flex;
  align-items: stretch;
}

.history-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  text-align: left;
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  color: inherit;
  font: inherit;
}

.history-actions {
  display: none;
  align-items: flex-start;
  gap: 2px;
  padding-left: 6px;
}

.history-row:hover .history-actions,
.history-row:focus-within .history-actions {
  display: flex;
}

.icon-btn {
  padding: 4px;
  border-radius: var(--radius-sm);
}

.danger-text {
  color: var(--coral, #d95d6a);
}

.history-rename {
  flex: 1;
}

.rename-input {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: inherit;
  font: inherit;
  outline: none;
}
</style>
