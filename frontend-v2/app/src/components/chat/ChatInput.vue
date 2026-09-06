<script setup lang="ts">
/**
 * 输入区：附件（POST /ai/attachments multipart → attachment_ids 随消息）+ 发送/停止。
 * 审批 pending 或 run 进行中时发送禁用；409 冲突给友好提示（可关闭）。
 */
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import { useConversationStore } from '../../stores/conversation'
import { useRunStore } from '../../stores/run'
import { CHAT_FOCUS_KEY } from '../../composables/hotkeyPorts'
import AppIcon from '../AppIcon.vue'
import { http } from '../../api/http'
import { useResearchContext } from '../../stores/researchContext'

const run = useRunStore()
const conv = useConversationStore()
const research = useResearchContext()
const useProject = ref(true)
watch(() => research.project?.id, () => { useProject.value = true })

const text = computed({ get: () => conv.draftText, set: value => { conv.draftText = value; conv.saveDraft() } })
const ownsRun = computed(() => run.conversationId === conv.activeId)
const fileInput = ref<HTMLInputElement | null>(null)
const ta = ref<HTMLTextAreaElement | null>(null)
/** 计划模式：AI 先给 plan_card，批准后才执行（POST /ai/chat/stream body.plan_mode） */
const planMode = ref(false)
watch(() => conv.viewVersion, () => {
  planMode.value = false
  if (ta.value) ta.value.style.height = 'auto'
})

/* c 键全局聚焦入口（M4e）：App 级 provide 注册表（CHAT_FOCUS_KEY），本组件挂载时登记
 * textarea 聚焦函数、卸载时注销。不用组件间直接 import / window 事件——注册表由壳层持有，
 * 方向单一且可在单测中直调。 */
const chatFocusRegistry = inject(CHAT_FOCUS_KEY, null)
let deregisterChatFocus: (() => void) | null = null
onMounted(() => {
  deregisterChatFocus = chatFocusRegistry?.register(focusTa) ?? null
})
onUnmounted(() => {
  deregisterChatFocus?.()
  deregisterChatFocus = null
})

/** 聚焦并把光标落到文本末尾（按 c 即续写，不打断已有草稿）。 */
function focusTa(): void {
  const el = ta.value
  if (!el) return
  el.focus()
  const end = el.value.length
  el.setSelectionRange(end, end)
}

const canSend = computed(
  () => text.value.trim().length > 0 && !run.isActive && !conv.sending && !conv.loading && !run.conflict && !conv.uploading && !conv.remoteRunId && !conv.initializing,
)

const microtext = computed<string | null>(() => {
  if (conv.error) return conv.error
  if (conv.persistenceError) return conv.persistenceError
  if (conv.remoteRunId && !run.hasLiveStream()) return '此会话正在另一个窗口执行，已保存的进度会自动同步。'
  if (!ownsRun.value) return run.isActive ? '另一个会话正在执行，可返回该会话查看或停止。' : null
  if (run.conflict) return run.conflictMessage
  // 审批待决期出现的错误（如 resume 被拒 ResumeBlockedOut）优先于常规等待提示展示
  if (run.phase === 'awaiting_approval' && run.error) return run.error.message
  // 信息级微文本（非错误）：ready_to_resume=false 的「同批还有 N 项待决」优先于常规等待文案
  if (run.phase === 'awaiting_approval' && run.notice) return run.notice
  if (run.phase === 'awaiting_approval')
    return '审批待决 — 发送已暂停，批准或拒绝后知时将继续执行'
  if (run.phase === 'streaming') return '知时正在执行这段任务…可随时停止'
  if (run.phase === 'error' && run.error) return run.error.message
  // consumed 幂等等信息级提示在 done 后依然可见（低优先级，不遮错误）
  if (run.notice) return run.notice
  if (conv.error) return conv.error
  return null
})

const microTone = computed(() =>
  run.conflict || run.phase === 'error' || (run.phase === 'awaiting_approval' && !!run.error) ? 'warn' : 'info',
)

function send(): void {
  if (!canSend.value) return
  const message = text.value.trim()
  const attachmentIds = conv.attachmentIds
  conv.stageSentEcho(conv.draftAttachments) // 时间线 sent 回显附件 chip
  // 草稿和附件仅在服务端 run_started 确认接收后清理。
  const planModeOn = planMode.value
  planMode.value = false // 计划模式是一次性意图：随本条消息生效
  void conv.sendMessage(message, { attachmentIds, planMode: planModeOn, researchProjectId: useProject.value ? research.project?.id : undefined })
}

async function stopRemote(): Promise<void> {
  const cid = conv.activeId, rid = conv.remoteRunId
  if (!rid) return
  try { await http.post(`/ai/runs/${rid}/cancel`); if (conv.activeId === cid) await conv.syncState() }
  catch (e) { if (conv.activeId === cid) conv.error = e instanceof Error ? e.message : '停止失败' }
}

function onKeydown(e: KeyboardEvent): void {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    send()
  }
}

function pickFile(): void {
  fileInput.value?.click()
}

async function onFileChange(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (file) await conv.uploadAttachment(file)
}

function autogrow(e: Event): void {
  const el = e.target as HTMLTextAreaElement
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 140)}px`
}
</script>

<template>
  <div class="inputzone">
    <label v-if="research.project" class="project-context"><input v-model="useProject" type="checkbox">结合当前项目：{{ research.project.title }}</label>
    <button v-if="!ownsRun && run.isActive && run.conversationId" class="session-link" @click="conv.select(run.conversationId)">返回正在执行的会话</button>
    <button v-if="conv.remoteRunId && !run.hasLiveStream()" class="session-link" @click="stopRemote">停止此会话的运行</button>
    <button v-if="conv.sessionState?.can_resume && ownsRun && !run.hasLiveStream()" class="session-link" @click="run.openResumeStream()">继续已确认的审批</button>
    <div class="inputbox" :data-disabled="run.isActive">
      <!-- 附件 chips -->
      <div v-if="conv.draftAttachments.length" class="chips">
        <span v-for="a in conv.draftAttachments" :key="a.id" class="chip">
          {{ a.name }}
          <button class="chip-x" :title="'移除附件 ' + a.name" @click="conv.removeAttachment(a.id)">
            <AppIcon name="x" :size="11" />
          </button>
        </span>
        <span v-if="conv.uploading" class="chip uploading">解析中…</span>
      </div>
      <textarea
        ref="ta"
        v-model="text"
        class="ta"
        rows="1"
        :placeholder="run.isActive ? '知时正在执行…' : '告诉知时要做什么…'"
        :disabled="conv.initializing"
        @keydown="onKeydown"
        @input="autogrow"
      />
      <div class="row">
        <button class="ibtn" title="附件" :disabled="run.isActive || conv.uploading" @click="pickFile">
          <AppIcon name="paperclip" :size="16" />
        </button>
        <input ref="fileInput" type="file" class="file-hidden" @change="onFileChange" />
        <button
          class="plan-toggle"
          :data-on="planMode ? '' : null"
          title="计划模式：知时先给出执行计划，你批准后才开始执行"
          @click="planMode = !planMode"
        >
          计划
        </button>
        <span class="model-chip">
          知时 Agent
          <AppIcon name="chevron-down" :size="11" />
        </span>
        <!-- 进行中：停止（POST /ai/runs/{run_id}/cancel，幂等）；空闲：发送 -->
        <button
          v-if="run.isActive && ownsRun"
          class="send stop"
          title="停止当前任务"
          @click="run.cancel()"
        >
          <AppIcon name="stop" :size="16" />
        </button>
        <button v-else class="send" :disabled="!canSend" title="发送（Enter）" @click="send">
          <AppIcon name="send" :size="16" />
        </button>
      </div>
    </div>
    <div v-if="microtext" class="microtext" :data-tone="microTone">
      <span>{{ microtext }}</span>
      <button v-if="run.conflict" class="dismiss" title="知道了" @click="run.dismissConflict()">
        <AppIcon name="x" :size="12" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.session-link { font-size:12px; color:var(--amber); padding:6px 0; display:block; }
.project-context { display:flex; gap:7px; align-items:center; color:var(--amber); font-size:12px; padding:0 0 10px; overflow-wrap:anywhere; }
.project-context input { accent-color:var(--amber); }
.inputzone {
  flex: none;
  padding: 12px 22px 14px;
}
.inputbox {
  border: 1px solid var(--line-2);
  border-radius: var(--radius-l);
  background: var(--bg-raise);
  padding: 11px 12px 9px;
  box-shadow: var(--shadow-input);
}
.inputbox[data-disabled='true'] {
  /* 浅色 --inputbox-disabled-opacity=1（整组 opacity 会把占位文字压到 <4.5:1）；暗色 fallback 0.75 不变 */
  opacity: var(--inputbox-disabled-opacity, 0.75);
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 4px 8px;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--ink-2);
  border: 1px solid var(--line-2);
  background: var(--bg-sink);
  border-radius: var(--radius-pill);
  padding: 3px 10px;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chip.uploading {
  color: var(--amber-soft);
  border-color: var(--amber-border-dim);
}
.chip-x {
  display: flex;
  color: var(--ink-3);
  padding: 1px;
}
.chip-x:hover {
  color: var(--terra-soft);
}
.ta {
  display: block;
  width: 100%;
  border: none;
  outline: none;
  resize: none;
  background: transparent;
  color: var(--ink);
  font: inherit;
  font-size: 14px;
  line-height: 1.6;
  padding: 2px 4px 12px;
  min-height: 28px;
  max-height: 140px;
}
.ta::placeholder {
  color: var(--ink-faint);
}
.ta:disabled {
  color: var(--ink-3);
  cursor: not-allowed;
}
.row {
  display: flex;
  align-items: center;
  gap: 4px;
}
.ibtn {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ink-3);
  flex: none;
}
.ibtn:hover:not(:disabled) {
  background: var(--ink-wash);
  color: var(--ink-2);
}
.ibtn:disabled {
  /* 浅色 --ctl-disabled-opacity=0.75（图标须 ≥3:1）；暗色 fallback 0.45 不变 */
  opacity: var(--ctl-disabled-opacity, 0.45);
  cursor: not-allowed;
}
.file-hidden {
  display: none;
}
.plan-toggle {
  margin-left: 6px;
  font-size: 12px;
  color: var(--ink-3);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-pill);
  padding: 4px 11px;
  user-select: none;
}
.plan-toggle:hover {
  color: var(--ink-2);
  border-color: var(--line-hover);
}
.plan-toggle[data-on] {
  color: var(--amber-soft);
  border-color: var(--amber-border);
  background: var(--amber-wash);
}
.model-chip {
  margin-left: 6px;
  font-size: 12px;
  color: var(--ink-2);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-pill);
  padding: 4px 11px;
  display: flex;
  align-items: center;
  gap: 5px;
  background: var(--bg-sink);
  user-select: none;
}
.send {
  margin-left: auto;
  width: 32px;
  height: 32px;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--btn-ok-bg);
  color: var(--btn-ok-text);
  flex: none;
}
.send:hover {
  filter: brightness(1.05);
}
.send:disabled {
  background: var(--send-idle-bg);
  color: var(--send-idle-text);
  /* 浅色 --ctl-disabled-opacity=0.75（空闲图标须 ≥3:1）；暗色 fallback 0.45 不变 */
  opacity: var(--ctl-disabled-opacity, 0.45);
  cursor: not-allowed;
  filter: none;
}
.send.stop {
  background: var(--send-idle-bg);
  color: var(--terra-soft);
  opacity: 1;
}
.microtext {
  margin-top: 8px;
  font-size: 12px;
  letter-spacing: 0.02em;
  padding-left: 2px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.microtext[data-tone='info'] {
  color: var(--terra-soft);
}
.microtext[data-tone='warn'] {
  color: var(--terra-soft);
  font-weight: 500;
}
.dismiss {
  color: var(--ink-3);
  display: flex;
  padding: 2px;
  flex: none;
}
.dismiss:hover {
  color: var(--ink-2);
}
</style>
