<script setup>
// 悬浮窗前端：按钮态（知时圆形悬浮球）<-> 面板态（展开知时助手）。
// 与主窗口互斥：主窗口打开时主进程发 float:collapse，切回按钮态。
// 按钮态用 JS 区分点击与拖动：按下后位移 < 4px 视为点击展开，否则触发主进程拖动窗口。
import { onMounted, ref } from 'vue'
import AssistantView from './AssistantView.vue'
import ArtIcon from '../components/ArtIcon.vue'

const FLOAT_BUTTON_SIZE = { w: 60, h: 60 }
const FLOAT_PANEL_SIZE = { w: 400, h: 640 }
const DRAG_THRESHOLD = 4

const collapsed = ref(true)
let downAt = null
let dragging = false

function expand() {
  collapsed.value = false
  window.electronAPI?.floatSetSize?.(FLOAT_PANEL_SIZE.w, FLOAT_PANEL_SIZE.h)
}

function collapse() {
  collapsed.value = true
  window.electronAPI?.floatSetSize?.(FLOAT_BUTTON_SIZE.w, FLOAT_BUTTON_SIZE.h)
}

function onPointerDown(e) {
  if (e.button !== 0) return
  downAt = { x: e.clientX, y: e.clientY }
  dragging = false
  e.currentTarget.setPointerCapture?.(e.pointerId)
}

function onPointerMove(e) {
  if (!downAt) return
  const dx = e.clientX - downAt.x
  const dy = e.clientY - downAt.y
  if (!dragging && Math.hypot(dx, dy) > DRAG_THRESHOLD) {
    dragging = true
    window.electronAPI?.floatDragStart?.()
  }
  if (dragging) {
    e.preventDefault()
    window.electronAPI?.floatDragMove?.()
  }
}

function onPointerUp(e) {
  if (!downAt) return
  e.currentTarget?.releasePointerCapture?.(e.pointerId)
  if (!dragging) expand()
  downAt = null
  dragging = false
}

onMounted(() => {
  window.electronAPI?.onFloatCollapse?.(collapse)
})
</script>

<template>
  <button
    v-show="collapsed"
    class="float-button"
    aria-label="知时助手"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerUp"
  >
    <ArtIcon name="assistant" tone="on-accent" :size="32" />
  </button>
  <AssistantView v-show="!collapsed" float-mode @collapse="collapse" />
</template>

<style scoped>
.float-button {
  width: 100vw;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  margin: 0;
  border: none;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--accent), var(--sea-400));
  box-shadow: 0 6px 20px var(--accent-glow), var(--shadow-inset);
  cursor: grab;
  transition: transform 0.15s ease, filter 0.15s ease;
  -webkit-app-region: no-drag;
}
.float-button:hover {
  transform: scale(1.06);
  filter: saturate(1.08);
}
.float-button:active {
  cursor: grabbing;
  transform: scale(0.96);
}
.float-button :deep(.art-icon) {
  color: #fff;
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.25));
}
</style>
