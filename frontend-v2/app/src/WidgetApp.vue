<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ChatPanel from './components/chat/ChatPanel.vue'
import AppIcon from './components/AppIcon.vue'
import { useConversationStore } from './stores/conversation'
import { useRunStore } from './stores/run'
import { useSettingsStore } from './stores/settings'

const native = window.zhishiWidget
const conv = useConversationStore(), run = useRunStore(), settings = useSettingsStore()
const router = useRouter(), route = useRoute()
const collapsed = ref(false), pinned = ref(true), error = ref('')
let unsubscribeState: (() => void) | undefined
const status = computed(() => run.phase === 'awaiting_approval' ? '有一项操作等你确认' : run.isActive ? '正在为你处理…' : '随时说说你想做什么')
function applyState(s: { collapsed: boolean; pinned: boolean }) { collapsed.value = s.collapsed; pinned.value = s.pinned }
async function control(action: 'pin' | 'collapse' | 'hide' | 'main') {
  try { if (native) applyState(await native.control(action)); error.value = '' }
  catch (e) { error.value = e instanceof Error ? e.message : String(e) }
}
async function sync() {
  try { if (native) applyState(await native.state()) }
  catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  void conv.refresh()
  void settings.reconcileTheme()
}
function keydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && !e.isComposing && !(e.target instanceof HTMLTextAreaElement)) void control('hide')
}
watch(() => route.fullPath, async path => {
  if (path === '/' || !native) return
  try { await native.openMain(path); await router.replace('/') }
  catch (e) { error.value = e instanceof Error ? e.message : String(e) }
})
onMounted(() => { void sync(); unsubscribeState = native?.onStateChanged?.(applyState); window.addEventListener('focus', sync); window.addEventListener('keydown', keydown) })
onUnmounted(() => { unsubscribeState?.(); window.removeEventListener('focus', sync); window.removeEventListener('keydown', keydown) })
</script>

<template>
  <div class="widget-shell" :class="{ collapsed }">
    <section class="widget-panel" aria-label="知时随身助手">
      <header class="widget-head">
        <img src="/favicon.svg" width="34" height="34" alt="">
        <div class="brand"><strong>知时</strong><span>{{ status }}</span></div>
        <button id="widget-settings" title="悬浮窗设置" aria-label="悬浮窗设置" @click="router.push('/settings?section=desktop')"><AppIcon name="settings" :size="14" /></button>
        <button id="widget-pin" :title="pinned ? '取消置顶' : '置顶'" :aria-label="pinned ? '取消置顶' : '置顶'" :aria-pressed="pinned" @click="control('pin')">钉</button>
        <button id="widget-collapse" :title="collapsed ? '展开对话' : '收起'" :aria-label="collapsed ? '展开对话' : '收起'" :aria-expanded="!collapsed" @click="control('collapse')">{{ collapsed ? '+' : '−' }}</button>
        <button id="widget-hide" title="隐藏 · Ctrl+Alt+Z 唤回" aria-label="隐藏悬浮窗" @click="control('hide')">×</button>
      </header>
      <div v-show="!collapsed" class="widget-body">
        <ChatPanel class="widget-chat" />
        <p v-if="error" class="widget-error" role="alert">{{ error }}</p>
        <footer><span>拖动顶部移动</span><button id="widget-main" @click="control('main')">打开完整知时 ↗</button></footer>
      </div>
    </section>
  </div>
</template>

<style scoped>
.widget-shell { height:100vh; padding:7px; color:var(--ink); background:transparent; }
.widget-panel { display:flex; flex-direction:column; height:100%; overflow:hidden; border:1px solid var(--line-hover); border-radius:18px; background:var(--bg-chat); box-shadow:0 2px 6px #0003; }
.widget-head { height:62px; flex:none; display:flex; align-items:center; gap:7px; padding:9px 12px; background:var(--bg-raise); -webkit-app-region:drag; user-select:none; }
.brand { min-width:0; flex:1; display:grid; gap:3px; padding-left:3px; }.brand strong { font-family:var(--serif); font-size:17px; letter-spacing:3px; }.brand span { font-size:11px; color:var(--ink-3); overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }
button { -webkit-app-region:no-drag; border-radius:7px; color:var(--ink-2); font:inherit; }.widget-head button { min-width:27px; min-height:28px; padding:4px; font-size:14px; }button:hover { background:var(--bg-bubble); }button:focus-visible { outline:2px solid var(--amber); outline-offset:2px; }#widget-pin[aria-pressed=true] { color:var(--amber); background:var(--bg-bubble); }
.widget-body { display:flex; flex-direction:column; flex:1; min-height:0; overflow:hidden; }
.widget-chat { width:100%; flex:1; min-height:0; height:auto; border:0; }
.widget-chat :deep(.chat-head) { height:48px; padding:0 16px; }.widget-chat :deep(.thread) { padding:18px 16px; }.widget-chat :deep(.inputzone) { padding:10px 14px; }.widget-chat :deep(.empty) { padding:24px 0 16px; }.widget-chat :deep(.empty-line) { line-height:1.8; }
footer { height:30px; flex:none; display:flex; align-items:center; justify-content:space-between; padding:0 14px 7px; font-size:10px; color:var(--ink-3); }footer button { color:var(--amber); font-size:11px; padding:3px; }.widget-error { margin:4px 14px; color:var(--terra); font-size:12px; }
</style>
