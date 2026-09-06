<script setup lang="ts">
/**
 * AI 对话列（常驻主角，570px ≈ 40%，替代 M0 的 ChatPanelPlaceholder）：
 * 会话头（标题/运行状态/会话列表）→ 消息流 → 活性状态条 → 输入区。
 * ≥1000px 常驻；<1000px 由 App.vue 下发抽屉态 class（chat-as-drawer / chat-drawer-hidden）
 * 变为 fixed 浮层，本组件不感知视口、只认 class。
 */
import { computed, nextTick, ref, watch, onMounted, onUnmounted } from 'vue'
import { useConversationStore } from '../../stores/conversation'
import { useRunStore } from '../../stores/run'
import AppIcon from '../AppIcon.vue'
import ChatInput from './ChatInput.vue'
import ChatThread from './ChatThread.vue'
import ConversationList from './ConversationList.vue'
import RunStatusBar from './RunStatusBar.vue'

const run = useRunStore()
const conv = useConversationStore()

const ownsRun = computed(() => run.conversationId === conv.activeId)
let syncTimer: ReturnType<typeof setInterval> | undefined
const synchronize = () => { if (document.visibilityState !== 'hidden') { void conv.syncState(); if (conv.workspaceDirty) void conv.flushWorkspace() } }
onMounted(() => {
  void conv.initialize()
  syncTimer = setInterval(synchronize, 2500)
  window.addEventListener('focus', synchronize)
})
onUnmounted(() => { clearInterval(syncTimer); window.removeEventListener('focus', synchronize) })

const listOpen = ref(false)
const scroller = ref<HTMLElement | null>(null)

/** 新内容到达时贴底（用户手动上滚超过一屏时则不打扰）。 */
watch(
  () => [
    conv.messages.length,
    run.segments.map((s) => s.content.length).join(','),
    run.toolCalls.length,
    run.sentMessage,
    run.approvalLedger.length, // 审批卡列表化（M3.5）：卡数与落章都要贴底
    run.approvalLedger.map((x) => x.outcome ?? '').join(','),
    run.planCard?.planId,
  ],
  () => {
    void nextTick(() => {
      const el = scroller.value
      if (!el) return
      const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 240
      if (nearBottom) el.scrollTop = el.scrollHeight
    })
  },
)

const headStatus = computed<'' | 'running' | 'approval'>(() =>
  !ownsRun.value ? '' : run.phase === 'streaming' ? 'running' : run.phase === 'awaiting_approval' ? 'approval' : '',
)

// run 收敛后刷新会话列表：新会话的标题在首条消息落库后才存在
watch(
  () => run.phase,
  (p, prev) => {
    if (prev && (p === 'completed' || p === 'error' || p === 'cancelled')) void conv.refresh()
  },
)
</script>

<template>
  <aside class="chat">
    <header class="chat-head">
      <div class="head-text">
        <div class="t">{{ conv.activeTitle }}</div>
        <div class="sub">你的私人秘书</div>
      </div>
      <div class="right">
        <span v-if="headStatus" class="chip-ghost">
          <span class="dot" />{{ headStatus === 'running' ? '运行中' : '等待审批' }}
        </span>
        <button class="ibtn" title="会话列表" @click="listOpen = !listOpen">
          <AppIcon name="list" :size="16" />
        </button>
        <button class="ibtn" title="新建会话" :disabled="run.hasLiveStream() || conv.sending || conv.initializing" @click="conv.startNew()">
          <AppIcon name="plus" :size="16" />
        </button>
      </div>
    </header>

    <details v-if="conv.sessionState" class="context-state">
      <summary>会话记录 · {{ conv.sessionState.message_count }} 条消息<span v-if="conv.sessionState.archive_count"> · 已压缩 {{ conv.sessionState.archive_count }} 次</span></summary>
      <p>当前工作上下文 {{ conv.sessionState.working_rounds }} 轮；压缩前记录保留在本机。</p>
      <p v-if="conv.sessionState.model">当前模型：{{ conv.sessionState.model }}<span v-if="conv.sessionState.context_window"> · 容量 {{ conv.sessionState.context_window.toLocaleString() }} token</span></p>
      <pre v-if="conv.sessionState.summary">{{ conv.sessionState.summary }}</pre>
      <p v-else>尚未生成会话摘要。</p>
    </details>
    <p v-if="conv.loading || conv.initializing" class="context-state">正在加载会话…</p>
    <div class="thread" ref="scroller">
      <ChatThread />
    </div>

    <RunStatusBar v-if="ownsRun" />
    <ChatInput />

    <ConversationList v-if="listOpen" @close="listOpen = false" />
  </aside>
</template>

<style scoped>
.context-state { flex:none; font-size:12px; color:var(--ink-3); padding:8px 22px; border-bottom:1px solid var(--line); max-height:180px; overflow:auto; }
.context-state summary { cursor:pointer; }
.context-state p { margin:6px 0; }
.context-state pre { white-space:pre-wrap; overflow-wrap:anywhere; font-family:var(--sans); color:var(--ink-2); }
.chat {
  width: var(--chat-w);
  height: 100%;
  flex: none;
  background: var(--bg-chat);
  border-right: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  position: relative;
  min-width: 0;
}
/* ---- 窄屏（<1000px）抽屉态：class 由 App.vue 依 matchMedia + 开关状态 fallthrough 下发 ----
 * chat-drawer-hidden：抽屉关，不占 flex 位，内容区占满导航轨以外全部宽度；
 * chat-as-drawer：抽屉开，fixed 浮层（层谱：背衬 35 之上、通知面板 40 之下）。
 * ≥1000px 两个 class 永不出现，常驻布局像素级不变。 */
.chat.chat-drawer-hidden {
  display: none;
}
.chat.chat-as-drawer {
  position: fixed;
  left: var(--rail-w);
  top: 0;
  bottom: 0;
  width: min(var(--chat-w), calc(100vw - var(--rail-w) - 24px));
  z-index: 36;
  box-shadow: var(--shadow-panel);
  animation: chat-drawer-in 0.18s ease-out; /* prefers-reduced-motion 下被全局规则禁用 */
}
@keyframes chat-drawer-in {
  from {
    opacity: 0;
    transform: translateX(-14px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
.chat-head {
  height: 56px;
  flex: none;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 22px;
  border-bottom: 1px solid var(--line);
}
.head-text {
  min-width: 0;
}
.chat-head .t {
  font-family: var(--serif);
  font-size: 16.5px;
  font-weight: 600;
  letter-spacing: 0.02em;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chat-head .sub {
  font-size: 12px;
  color: var(--ink-3);
  margin-top: 2px;
}
.right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}
.chip-ghost {
  font-size: 12px;
  color: var(--ink-2);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-pill);
  padding: 4px 11px;
  display: flex;
  align-items: center;
  gap: 7px;
  background: var(--bg-raise);
  white-space: nowrap;
}
.chip-ghost .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--amber);
  animation: pulse 2s infinite;
}
.ibtn {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ink-3);
}
.ibtn:hover:not(:disabled) {
  background: var(--ink-wash);
  color: var(--ink-2);
}
.ibtn:disabled {
  /* 浅色 --ctl-disabled-opacity=0.75（图标须 ≥3:1）；暗色 fallback 0.4 不变 */
  opacity: var(--ctl-disabled-opacity, 0.4);
  cursor: not-allowed;
}
.thread {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 18px 24px 8px;
}
@keyframes pulse {
  0% {
    box-shadow: 0 0 0 0 var(--amber-pulse);
  }
  70% {
    box-shadow: 0 0 0 7px var(--amber-pulse-end);
  }
  100% {
    box-shadow: 0 0 0 0 var(--amber-pulse-end);
  }
}
</style>
