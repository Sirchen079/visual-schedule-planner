<script setup lang="ts">
/**
 * 「黑板」面板：AI 用 show_blackboard 工具推送的自包含 HTML 示意页。
 * 内容在 sandbox iframe 里渲染（仅 allow-scripts、无同源）——页面内脚本拿不到
 * 应用会话、接口与存储，也与新窗口/表单/顶层导航隔离。消息流 v-html 通道禁
 * iframe，黑板是独立的展示通道，互不影响。
 *
 * 运行时闭环（机制借鉴 WorkBuddy）：注入引导脚本捕获页内 JS 报错与内容高度，
 * postMessage 回宿主——报错显示错误占位并提供「让 AI 修复」（把错误发回会话，
 * 模型修正后重新推送）；高度回报驱动 iframe 自适应（钳制上下限，未回报保持兜底）。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useConversationStore } from '../../stores/conversation'
import { useRunStore } from '../../stores/run'
import { BOARD_FALLBACK_HEIGHT, buildBoardDoc, clampBoardHeight, parseBoardMessage } from '../../utils/blackboard'

const run = useRunStore()
const conv = useConversationStore()
const collapsed = ref(false)
/** 手动收起后，同一页内容微调不再自动弹开；换新页（内容变化）才重新展开 */
const dismissedFor = ref('')
/** 当前页的渲染错误（最新一条）与高度 */
const lastError = ref<{ kind: 'script' | 'promise'; message: string; detail: string } | null>(null)
const heightPx = ref(0)
const frame = ref<HTMLIFrameElement | null>(null)

const doc = computed(() => run.blackboard ? buildBoardDoc(run.blackboard.html) : '')

watch(() => run.blackboard?.html, () => {
  // 整页替换：上一页的错误与高度作废；新页自动展开（除非用户刚收起的就是这一页）
  lastError.value = null
  heightPx.value = 0
  if (run.blackboard && dismissedFor.value !== run.blackboard.html) collapsed.value = false
})

function onMessage(e: MessageEvent) {
  if (e.source !== frame.value?.contentWindow) return
  const msg = parseBoardMessage(e.data)
  if (!msg) return
  if (msg.type === 'blackboard:error') lastError.value = msg
  else heightPx.value = clampBoardHeight(msg.height)
}
onMounted(() => window.addEventListener('message', onMessage))
onUnmounted(() => window.removeEventListener('message', onMessage))

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
  <section v-if="run.blackboard" class="blackboard" :data-collapsed="collapsed ? '' : null">
    <header class="bb-head">
      <span class="bb-tag">黑板</span>
      <span class="bb-title">{{ run.blackboard.title }}</span>
      <span v-if="lastError" class="bb-err-chip" title="页面脚本报错，见下方详情">报错</span>
      <button class="bb-btn" type="button" @click="collapsed ? (collapsed = false) : collapse()">
        {{ collapsed ? '展开' : '收起' }}
      </button>
    </header>
    <div v-if="!collapsed" class="bb-body">
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
        :srcdoc="doc"
        :style="{ height: heightPx ? `${heightPx}px` : `min(46vh, ${BOARD_FALLBACK_HEIGHT}px)` }"
        :title="`AI 黑板 · ${run.blackboard.title}`"
      />
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
  background: #fff;
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
