<script setup>
// 单条消息气泡：结构化渲染文本块（不用 v-html）、工具结果 details、危险操作确认卡，
// assistant 消息 hover 显示「复制」。视觉样式集中在 AssistantView.vue 的样式块维护。
import { inject } from 'vue'

const props = defineProps({
  message: { type: Object, required: true },
  assistantName: { type: String, default: '知时助手' },
  pendingTokens: { type: Object, default: () => ({}) },
  busy: { type: Boolean, default: false },
})
defineEmits(['first-confirm', 'second-confirm'])

// 悬浮窗宿主没有 toast provider，调用前必须判空
const toast = inject('toast', null)

function pendingStatusText(action) {
  if (action.status === 'pending') return '等待确认'
  if (action.status === 'confirmed') return '已一次确认'
  if (action.status === 'executed') return '已执行'
  if (action.status === 'expired') return '已过期'
  return action.status || '待处理'
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }
  // 非安全上下文（如 file:// 悬浮窗）降级：隐藏 textarea + execCommand
  const el = document.createElement('textarea')
  el.value = text
  el.style.position = 'fixed'
  el.style.opacity = '0'
  document.body.appendChild(el)
  el.select()
  document.execCommand('copy')
  el.remove()
}

async function copyMessage() {
  try {
    await copyText(props.message.content || '')
    toast?.success('已复制')
  } catch {
    toast?.error('复制失败')
  }
}
</script>

<template>
  <article :class="['message', message.role]">
    <div class="message-role">
      {{ message.role === 'user' ? '你' : message.role === 'assistant' ? assistantName : '系统' }}
    </div>
    <div
      v-if="message.content?.trim()"
      class="message-content"
    >
      <template v-for="(block, blockIndex) in message.blocks" :key="blockIndex">
        <ul v-if="block.type === 'list'" class="message-list">
          <li v-for="(item, itemIndex) in block.items" :key="itemIndex">{{ item }}</li>
        </ul>
        <p v-else-if="block.type === 'paragraph'" class="message-paragraph">
          <template v-for="(line, lineIndex) in block.lines" :key="lineIndex">
            <span>{{ line }}</span>
            <br v-if="lineIndex < block.lines.length - 1" />
          </template>
        </p>
      </template>
    </div>

    <div v-if="message.tool_results?.length" class="tool-results">
      <span class="tag">已执行 {{ message.tool_results.length }} 个工具</span>
      <details>
        <summary>查看结果</summary>
        <pre>{{ JSON.stringify(message.tool_results, null, 2) }}</pre>
      </details>
    </div>

    <div v-for="action in message.pending_actions || []" :key="action.id" class="pending-card">
      <div class="pending-head">
        <div>
          <strong>危险操作待确认</strong>
          <p>{{ pendingStatusText(action) }}</p>
        </div>
        <span class="danger-dot"></span>
      </div>
      <p class="pending-summary">{{ action.summary }}</p>
      <ul v-if="action.preview?.length" class="pending-preview">
        <li v-for="(line, previewIndex) in action.preview" :key="previewIndex">{{ line }}</li>
      </ul>
      <div class="pending-actions">
        <button v-if="!pendingTokens[action.id]" class="ghost" :disabled="busy" @click="$emit('first-confirm', action)">
          第一次确认
        </button>
        <button v-else class="danger" :disabled="busy" @click="$emit('second-confirm', action)">
          我已理解影响，执行
        </button>
      </div>
    </div>

    <div v-if="message.role === 'assistant' && message.content?.trim()" class="message-actions">
      <button type="button" class="ghost compact copy-action" aria-label="复制这条回复" @click="copyMessage">
        复制
      </button>
    </div>
  </article>
</template>

<style scoped>
.message-actions {
  position: absolute;
  top: 6px;
  right: 8px;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s ease;
}

.message:hover .message-actions,
.message:focus-within .message-actions {
  opacity: 1;
  pointer-events: auto;
}

.copy-action {
  background: var(--surface-solid);
  box-shadow: var(--shadow-sm);
}
</style>
