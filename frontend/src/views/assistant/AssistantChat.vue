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
  // 当前 run 的实时状态文案（如"正在思考…"）与已用秒数；仅 busy 时有意义
  runStatus: { type: String, default: '' },
  runElapsed: { type: Number, default: 0 },
  // 当前 run 的累计 token 用量：{prompt_tokens, completion_tokens, total_tokens} 或 null
  runUsage: { type: Object, default: null },
  // 阶段 C1：会话模式 chat=正常对话；plan=计划模式
  chatMode: { type: String, default: 'chat' },
  // AI 配置可用性（是否有 enabled 的模型配置）：空对话且未配置时显示配置引导卡。
  // 由 AssistantView 传入响应式的 hasEnabledConfig，保证启用/保存配置后实时刷新。
  aiAvailable: { type: Boolean, default: undefined },
})
defineEmits([
  'send',
  'retry',
  'dismiss-failed',
  'stop',
  'first-confirm',
  'second-confirm',
  'reject',
  'remove-attachment',
  'pick-chat-files',
  'pick-ai-attachments',
  'open-settings',
  'set-mode',
  'approve-plan',
  'reject-plan',
  'grant-action',
])

const input = defineModel({ type: String, default: '' })

// AI 配置可用性：优先用父组件传入的响应式 prop（AssistantView 的 hasEnabledConfig），
// 该值在保存/启用配置后会随 load() 重算实时刷新。未传时降级到 App.vue 注入的
// ai-available（仅 onMounted 读一次，悬浮窗等非主窗口路径可能未初始化），
// 再降级默认 true，防止组件树外使用时误显示配置引导卡。
const injectedAiAvailable = inject('ai-available', ref(true))
const aiAvailable = computed(() =>
  props.aiAvailable !== undefined ? props.aiAvailable : injectedAiAvailable.value,
)

const messagesRef = ref(null)
const composerInput = ref(null)

// token 千位缩写：999 / 1.2k / 34.5k；provider 不回 usage（null）时不显示
function formatTokens(n) {
  const num = Number(n) || 0
  if (num < 1000) return String(num)
  if (num < 10000) return `${(num / 1000).toFixed(1)}k`
  return `${Math.round(num / 1000)}k`
}

const visibleMessages = computed(() =>
  props.messages.filter((message) => {
    // 流式占位消息（assistant 发送后尚未产出任何增量）也放行：让"正在思考…"指示器可见，
    // 否则从发送到首个 text_delta/tool_call_start 之间用户看不到任何反馈。
    if (message.streaming === true) return true
    const hasText = Boolean(message.content?.trim())
    const hasTools = Boolean(message.tool_results?.length)
    const hasActions = Boolean(message.pending_actions?.length)
    // 阶段 C1/C2：含计划卡片或工作清单的消息也可见
    const hasPlan = Boolean(message.plan_card)
    const hasWorkPlan = Boolean(message.work_plan?.length)
    return hasText || hasTools || hasActions || hasPlan || hasWorkPlan
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
      <template v-if="busy || uploadingFiles || attachingFiles">
        <span v-if="uploadingFiles" class="tag">入库中</span>
        <span v-else-if="attachingFiles" class="tag">添加中</span>
        <template v-else>
          <span v-if="runStatus" class="run-status">
            <span class="run-dot" aria-hidden="true"></span>
            {{ runStatus }}<span v-if="runElapsed > 0" class="run-elapsed">{{ runElapsed }}s</span>
          </span>
          <span v-if="runUsage" class="run-tokens" :title="`输入 ${formatTokens(runUsage.prompt_tokens)} · 输出 ${formatTokens(runUsage.completion_tokens)} tokens`">
            <span class="tok-up">↑{{ formatTokens(runUsage.prompt_tokens) }}</span>
            <span class="tok-down">↓{{ formatTokens(runUsage.completion_tokens) }}</span>
          </span>
          <button type="button" class="stop-btn" @click="$emit('stop')" title="中断当前处理">
            <ArtIcon name="close" tone="on-accent" :size="14" />
            <span>停止</span>
          </button>
        </template>
      </template>
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
        :run-status="runStatus"
        @first-confirm="$emit('first-confirm', $event)"
        @second-confirm="$emit('second-confirm', $event)"
        @reject="$emit('reject', $event)"
        @approve-plan="$emit('approve-plan', $event)"
        @reject-plan="$emit('reject-plan', $event)"
        @grant-action="$emit('grant-action', $event)"
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
          :placeholder="chatMode === 'plan' ? '让我先调研并给你一份计划…（计划模式下只读调研，不改数据）' : '例如：帮我把本周论文阅读拆成三天计划，并给明晚加一个提醒...'"
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
          <!-- 阶段 C1：模式切换 chat/plan -->
          <div class="mode-switch" role="group" aria-label="对话模式">
            <button
              type="button"
              class="mode-btn"
              :class="{ active: chatMode === 'chat' }"
              :disabled="busy"
              :title="chatMode === 'chat' ? '当前为对话模式：直接执行操作' : '切换到对话模式'"
              @click="$emit('set-mode', 'chat')"
            >对话</button>
            <button
              type="button"
              class="mode-btn"
              :class="{ active: chatMode === 'plan' }"
              :disabled="busy"
              :title="chatMode === 'plan' ? '当前为计划模式：先调研后给计划，不直接改数据' : '切换到计划模式：先想后干'"
              @click="$emit('set-mode', 'plan')"
            >计划</button>
          </div>
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
/* 阶段 C1：对话/计划 模式切换 */
.mode-switch {
  display: inline-flex;
  gap: 0;
  padding: 2px;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--surface-2) 80%, transparent);
  border: 1px solid var(--border);
}

.mode-btn {
  padding: 4px 12px;
  border: none;
  border-radius: var(--radius-pill);
  background: transparent;
  color: var(--text-soft);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.mode-btn:hover:not(:disabled) {
  color: var(--text);
}

.mode-btn.active {
  background: var(--accent);
  color: var(--on-accent);
}

.mode-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

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

/* 停止按钮：流式处理中可见，点击中断当前 agent run */
.stop-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 700;
  border: 1px solid color-mix(in srgb, var(--danger) 45%, transparent);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--danger) 14%, transparent);
  color: var(--pri-high);
  cursor: pointer;
  transition: background 0.15s;
  flex-shrink: 0;
}

.stop-btn:hover {
  background: color-mix(in srgb, var(--danger) 24%, transparent);
}

/* 运行状态行：文案 + 跳动小圆点 + 已用秒数（对齐 Claude Code 状态栏体感） */
.run-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-soft);
  flex-shrink: 0;
}
.run-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--accent);
  animation: run-pulse 1s ease-in-out infinite;
}
@keyframes run-pulse {
  0%, 100% { opacity: 0.35; transform: scale(0.85); }
  50% { opacity: 1; transform: scale(1); }
}
@media (prefers-reduced-motion: reduce) {
  .run-dot { animation: none; }
}
.run-elapsed {
  color: var(--text-faint, var(--text-soft));
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

/* token 实时占用：↑输入 ↓输出，对照 Claude Code 状态栏 */
.run-tokens {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--text-soft);
  flex-shrink: 0;
}
.tok-up { color: var(--text-soft); }
.tok-down { color: var(--accent-hover); }
</style>
