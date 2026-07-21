<script setup>
// 对话区：消息列表（AssistantMessage）+ 输入区。消息、附件、发送状态全部由
// AssistantView 持有并通过 props 下发，本组件只负责渲染与转发交互事件。
import { computed, inject, ref } from 'vue'
import ArtIcon from '../../components/ArtIcon.vue'
import AssistantMessage from './AssistantMessage.vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  assistantName: { type: String, default: '知时助手' },
  busy: { type: Boolean, default: false },
  uploadingFiles: { type: Boolean, default: false },
  attachingFiles: { type: Boolean, default: false },
  chatAttachments: { type: Array, default: () => [] },
  pendingTokens: { type: Object, default: () => ({}) },
  failedText: { type: String, default: '' },
})
defineEmits([
  'send',
  'retry',
  'dismiss-failed',
  'first-confirm',
  'second-confirm',
  'remove-attachment',
  'pick-chat-files',
  'pick-ai-attachments',
  'open-settings',
])

const input = defineModel({ type: String, default: '' })

// AI 配置可用性（App.vue provide）：空对话且未配置模型时显示配置引导卡。
// 降级默认 true（不显示引导卡），防止组件树外使用时误导。
const aiAvailable = inject('ai-available', ref(true))

const messagesRef = ref(null)
const composerInput = ref(null)

const visibleMessages = computed(() =>
  props.messages.filter((message) => {
    const hasText = Boolean(message.content?.trim())
    const hasTools = Boolean(message.tool_results?.length)
    const hasActions = Boolean(message.pending_actions?.length)
    return hasText || hasTools || hasActions
  })
)

// 父组件在消息变化 / 打开窗口后调用（父侧先 await nextTick）
function scrollToBottom() {
  const el = messagesRef.value
  if (el) el.scrollTop = el.scrollHeight
}

function focusComposer() {
  composerInput.value?.focus()
}

defineExpose({ scrollToBottom, focusComposer })
</script>

<template>
  <section class="card chat-panel chat-stage">
    <div class="chat-head">
      <div class="chat-copy">
        <h3>{{ assistantName }} 对话</h3>
        <p class="muted">低风险操作会直接执行；危险操作会显示二次确认卡片。</p>
      </div>
      <span v-if="busy || uploadingFiles || attachingFiles" class="tag">
        {{ uploadingFiles ? '入库中' : attachingFiles ? '添加中' : '处理中' }}
      </span>
      <button v-else class="ghost compact" @click="$emit('open-settings')">
        <ArtIcon name="assistant" tone="aqua" :size="16" />
        <span>配置</span>
      </button>
    </div>

    <div ref="messagesRef" class="messages" role="log" aria-live="polite" :aria-busy="busy">
      <div v-if="!messages.length" class="empty-chat">
        <template v-if="!aiAvailable">
          <div class="empty-title">需要先配置模型才能开始对话</div>
          <div>在「配置」里接入一个模型接口后，{{ assistantName }}就能帮你拆任务、排日程了。</div>
          <button type="button" class="config-guide-btn" @click="$emit('open-settings')">
            <ArtIcon name="assistant" tone="on-accent" :size="16" />
            <span>去配置</span>
          </button>
        </template>
        <template v-else>
          <div class="empty-title">从一个想法开始</div>
          <div>告诉{{ assistantName }}你要安排什么，或让它整理刚上传的资料。</div>
        </template>
      </div>

      <AssistantMessage
        v-for="(message, index) in visibleMessages"
        :key="index"
        :message="message"
        :assistant-name="assistantName"
        :pending-tokens="pendingTokens"
        :busy="busy"
        @first-confirm="$emit('first-confirm', $event)"
        @second-confirm="$emit('second-confirm', $event)"
      />
    </div>

    <div v-if="failedText" class="failed-bar" role="status">
      <span class="failed-text" :title="failedText">发送失败：{{ failedText }}</span>
      <button type="button" class="ghost compact" :disabled="busy" @click="$emit('retry')">
        <ArtIcon name="refresh" tone="aqua" :size="14" />
        <span>重试</span>
      </button>
      <button type="button" class="ghost compact failed-dismiss" aria-label="忽略发送失败" @click="$emit('dismiss-failed')">
        <ArtIcon name="close" tone="pearl" :size="14" />
      </button>
    </div>

    <div class="composer">
      <div class="composer-input">
        <textarea
          ref="composerInput"
          v-model="input"
          placeholder="例如：帮我把本周论文阅读拆成三天计划，并给明晚加一个提醒..."
          :disabled="uploadingFiles || attachingFiles"
          @keydown.ctrl.enter.prevent="$emit('send')"
        ></textarea>
        <div v-if="uploadingFiles" class="upload-hint">正在上传资料到资料库...</div>
        <div v-if="attachingFiles" class="upload-hint">正在添加对话附件...</div>
        <div v-if="chatAttachments.length" class="attachment-strip">
          <span v-for="file in chatAttachments" :key="file.id" class="attachment-chip">
            <ArtIcon :name="file.kind === 'image' ? 'image' : 'file'" tone="aqua" :size="15" />
            <span>{{ file.original_name }}</span>
            <button type="button" :aria-label="`移除 ${file.original_name}`" @click="$emit('remove-attachment', file.id)">
              <ArtIcon name="close" tone="pearl" :size="14" />
            </button>
          </span>
        </div>
      </div>
      <div class="composer-toolbar">
        <div class="composer-file-actions">
          <button class="ghost compact" :disabled="busy || uploadingFiles || attachingFiles" @click="$emit('pick-ai-attachments')">
            <ArtIcon name="file" tone="aqua" :size="18" />
            <span>看文件</span>
          </button>
          <button class="ghost compact" :disabled="busy || uploadingFiles || attachingFiles" @click="$emit('pick-chat-files')">
            <ArtIcon name="upload" tone="mint" :size="18" />
            <span>入库</span>
          </button>
        </div>
        <button
          class="send-action"
          :disabled="busy || uploadingFiles || attachingFiles || (!input.trim() && !chatAttachments.length)"
          @click="$emit('send')"
        >
          <ArtIcon name="send" tone="on-accent" :size="20" />
          <span>{{ busy ? '处理中...' : '发送' }}</span>
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* 发送失败重试条：显示上一条失败消息，可一键重发（复用父组件发送逻辑）或忽略 */
.failed-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  padding: 8px 10px;
  border: 1px solid color-mix(in srgb, var(--danger) 38%, transparent);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--danger) 8%, transparent);
  flex-shrink: 0;
}

.failed-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--pri-high);
  font-size: 12px;
  font-weight: 700;
}

.failed-dismiss {
  flex-shrink: 0;
}

/* 空对话且未配置模型时的引导卡按钮 */
.config-guide-btn {
  margin-top: 12px;
  justify-self: center;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 20px;
  font-size: 13px;
  font-weight: 700;
}
</style>
