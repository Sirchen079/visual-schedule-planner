<script setup lang="ts">
/**
 * 「黑板」面板：AI 用 show_blackboard 工具推送的自包含 HTML 示意页。
 * 内容在 sandbox iframe 里渲染（仅 allow-scripts、无同源）——页面内脚本拿不到
 * 应用会话、接口与存储，也与新窗口/表单/顶层导航隔离。消息流 v-html 通道禁
 * iframe，黑板是独立的展示通道，互不影响。
 *
 * 持久沙箱文档 + postMessage 协议（机制借鉴 WorkBuddy）：
 * - 流式预览：show_blackboard 参数还在生成时就边流边渲染——从 argsPreview 里做
 *   部分 JSON 提取，节流推送 blackboard:update（脚本不执行）；工具落定后用
 *   blackboard_updated 事件的整页发 blackboard:finalize（脚本执行）。
 * - 握手排队：iframe ready 之前宿主消息先排队；引导脚本回报页内报错与内容高度，
 *   报错提供「让 AI 修复」（流式期间的报错来自半成品页面，忽略），高度做微小
 *   增长防抖后驱动 iframe 自适应。
 * - 主题同步：应用深浅色切换（documentElement 的 data-theme）即时推送进沙箱文档。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useConversationStore } from '../../stores/conversation'
import { useRunStore } from '../../stores/run'
import {
  BOARD_FALLBACK_HEIGHT, SANDBOX_DOC, createHeightGuard, extractPartialBoard,
  parseBoardMessage, trimUnclosedScript, type BoardGuestMessage,
} from '../../utils/blackboard'
import { currentTheme } from '../../utils/theme'

const STREAM_INTERVAL_MS = 500

const run = useRunStore()
const conv = useConversationStore()
const collapsed = ref(false)
/** 手动收起后，同一页内容不再自动弹开；新一轮绘制（内容变化）才重新展开 */
const dismissedFor = ref('')
/** 当前页的渲染错误（最新一条）与高度 */
const lastError = ref<{ kind: 'script' | 'promise'; message: string; detail: string } | null>(null)
const heightPx = ref(0)
const ready = ref(false)
const frame = ref<HTMLIFrameElement | null>(null)

let pending: BoardGuestMessage[] = []
let guard = createHeightGuard()
let lastSentAt = 0
let lastStreamed = ''
let lastFinalized = ''
let trailingTimer: ReturnType<typeof setTimeout> | null = null
let trailingHtml: string | null = null
let themeObserver: MutationObserver | null = null

/** 正在生成中的 show_blackboard 调用（从流式参数里抠出半成品页面） */
const streamingCall = computed(() => {
  const calls = run.toolCalls
  for (let i = calls.length - 1; i >= 0; i--) {
    if (calls[i].tool === 'show_blackboard' && calls[i].status === 'running') return calls[i]
  }
  return null
})
const streamingBoard = computed(() => {
  const call = streamingCall.value
  if (!call) return null
  const partial = extractPartialBoard(call.argsPreview)
  return partial && partial.html.trim() ? partial : null
})
const boardTitle = computed(() => streamingBoard.value?.title || run.blackboard?.title || '黑板')
const show = computed(() => !!run.blackboard || !!streamingCall.value)

function post(msg: BoardGuestMessage) {
  if (!ready.value) { pending.push(msg); return }
  frame.value?.contentWindow?.postMessage(msg, '*')
}
function flushPending() {
  if (!ready.value) return
  const queue = pending
  pending = []
  for (const msg of queue) frame.value?.contentWindow?.postMessage(msg, '*')
}
function postTheme() {
  post({ type: 'blackboard:theme', theme: currentTheme() })
}
function resetMeasurements() {
  heightPx.value = 0
  guard = createHeightGuard()
}
function sendStream(html: string) {
  lastSentAt = Date.now()
  lastStreamed = html
  post({ type: 'blackboard:update', html: trimUnclosedScript(html) })
}
function finalizeStored() {
  const page = run.blackboard
  if (!page || page.html === lastFinalized) return
  lastFinalized = page.html
  resetMeasurements()
  post({ type: 'blackboard:finalize', html: page.html })
}

watch(streamingBoard, (board, prev) => {
  if (!board) {
    if (trailingTimer !== null) { clearTimeout(trailingTimer); trailingTimer = null }
    trailingHtml = null
    if (prev) {
      // 流式落定：blackboard_updated 已到店存，用整页做最终挂载（脚本执行）
      lastStreamed = ''
      finalizeStored()
    }
    return
  }
  if (!prev) {
    // 新一轮绘制开始：旧页报错与测量作废，若非刚收起的同一页则自动展开
    lastError.value = null
    lastFinalized = ''
    resetMeasurements()
    if (dismissedFor.value !== board.html) collapsed.value = false
  }
  if (board.html === lastStreamed) return
  if (trailingTimer !== null) { trailingHtml = board.html; return }
  const now = Date.now()
  if (now - lastSentAt >= STREAM_INTERVAL_MS) {
    sendStream(board.html)
  } else {
    trailingHtml = board.html
    trailingTimer = setTimeout(() => {
      trailingTimer = null
      const html = trailingHtml
      trailingHtml = null
      if (html) sendStream(html)
    }, STREAM_INTERVAL_MS - (now - lastSentAt))
  }
})

watch(() => run.blackboard?.html, () => {
  lastError.value = null
  if (!streamingBoard.value) finalizeStored()
  if (run.blackboard && dismissedFor.value !== run.blackboard.html) collapsed.value = false
})

function onMessage(e: MessageEvent) {
  if (e.source !== frame.value?.contentWindow) return
  const msg = parseBoardMessage(e.data)
  if (!msg) return
  if (msg.type === 'blackboard:ready') {
    ready.value = true
    postTheme()
    if (streamingBoard.value) sendStream(streamingBoard.value.html)
    else finalizeStored()
    flushPending()
  } else if (msg.type === 'blackboard:error') {
    if (!streamingBoard.value) lastError.value = msg
  } else {
    heightPx.value = guard.push(msg.height)
  }
}
onMounted(() => {
  window.addEventListener('message', onMessage)
  themeObserver = new MutationObserver(postTheme)
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
})
onUnmounted(() => {
  window.removeEventListener('message', onMessage)
  themeObserver?.disconnect()
  if (trailingTimer !== null) clearTimeout(trailingTimer)
})

function collapse() {
  collapsed.value = true
  if (run.blackboard) dismissedFor.value = run.blackboard.html
}

const canAskFix = computed(() => !run.isActive && !conv.sending && !!lastError.value)
function askFix() {
  if (!lastError.value) return
  const { kind, message, detail } = lastError.value
  const where = kind === 'promise' ? '（未处理的 Promise 异常）' : ''
  const tail = detail ? `\n详情：${detail.slice(0, 300)}` : ''
  void conv.sendMessage(`黑板页面渲染出错${where}：${message}${tail}\n请定位问题后用 show_blackboard 重新推送修复后的页面。`)
}
</script>

<template>
  <section v-if="show" class="blackboard" :data-collapsed="collapsed ? '' : null">
    <header class="bb-head">
      <span class="bb-tag">黑板</span>
      <span class="bb-title" :title="boardTitle">{{ boardTitle }}</span>
      <span v-if="streamingCall" class="bb-live"><span class="bb-spin" />AI 正在绘制…</span>
      <span v-else-if="lastError" class="bb-err-chip" title="页面脚本报错，见下方详情">报错</span>
      <button class="bb-btn" type="button" @click="collapsed ? (collapsed = false) : collapse()">
        {{ collapsed ? '展开' : '收起' }}
      </button>
    </header>
    <!-- v-show：收起时保持 iframe 存活，展开即见内容，不用重新引导 -->
    <div v-show="!collapsed" class="bb-body">
      <div v-if="lastError" class="bb-error">
        <p class="bb-error-msg">渲染出错：{{ lastError.message }}</p>
        <p v-if="lastError.detail" class="bb-error-detail">{{ lastError.detail.slice(0, 240) }}</p>
        <button class="bb-fix" type="button" :disabled="!canAskFix"
          :title="canAskFix ? '把报错发回会话，让 AI 修复后重新推送' : '等当前回答结束后再发送'"
          @click="askFix">
          让 AI 修复
        </button>
      </div>
      <iframe
        ref="frame"
        class="bb-frame"
        sandbox="allow-scripts"
        :srcdoc="SANDBOX_DOC"
        :style="{ height: heightPx ? `${heightPx}px` : `min(46vh, ${BOARD_FALLBACK_HEIGHT}px)` }"
        :title="`AI 黑板 · ${boardTitle}`"
      />
      <div v-if="!ready" class="bb-loading">正在渲染…</div>
    </div>
  </section>
</template>

<style scoped>
.blackboard {
  flex: none;
  margin: 10px 18px 0;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--bg-raise);
  overflow: hidden;
}
.bb-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
}
.bb-tag {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--ink-3);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-pill);
  padding: 2px 8px;
}
.bb-title {
  min-width: 0;
  font-family: var(--serif);
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bb-live {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--amber-soft);
}
.bb-spin {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 1.5px solid var(--line-2);
  border-top-color: var(--amber);
  animation: bb-spin 0.9s linear infinite;
}
@keyframes bb-spin {
  to { transform: rotate(360deg); }
}
.bb-err-chip {
  flex: none;
  font-size: 11px;
  color: #96422f;
  border: 1px solid rgba(184, 84, 62, 0.45);
  border-radius: var(--radius-pill);
  padding: 1px 7px;
}
.bb-btn {
  margin-left: auto;
  flex: none;
  font-size: 12px;
  color: var(--ink-3);
  border-radius: 6px;
  padding: 3px 9px;
}
.bb-btn:hover { background: var(--ink-wash); color: var(--ink-2); }
.bb-frame {
  display: block;
  width: 100%;
  border: 0;
  border-top: 1px solid var(--line);
  background: var(--bg-raise);
}
.bb-loading {
  padding: 6px 12px;
  font-size: 11.5px;
  color: var(--ink-3);
  border-top: 1px solid var(--line);
}
.bb-error {
  border-top: 1px solid var(--line);
  background: rgba(184, 84, 62, 0.07);
  padding: 8px 12px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
}
.bb-error-msg {
  margin: 0;
  font-size: 12px;
  color: #96422f;
  overflow-wrap: anywhere;
}
.bb-error-detail {
  margin: 0;
  width: 100%;
  font-size: 11px;
  color: var(--ink-3);
  font-family: var(--mono, monospace);
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.bb-fix {
  margin-left: auto;
  flex: none;
  font-size: 12px;
  color: var(--ink-2);
  border: 1px solid var(--line-2);
  border-radius: 6px;
  padding: 3px 10px;
  background: var(--bg-raise);
}
.bb-fix:hover:not(:disabled) { background: var(--ink-wash); }
.bb-fix:disabled { opacity: var(--ctl-disabled-opacity, 0.4); cursor: not-allowed; }
</style>
