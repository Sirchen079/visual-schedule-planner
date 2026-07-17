<script setup>
// 统一弹层基座:overlay、Esc 关闭、焦点陷阱、z-index 层级、开合动画。
// 用法:<BaseModal :open="bool" @close="..."> —— 组件常驻挂载,由 open 控制显隐,
// 动画在组件内部完成(Transition 作用于真实 overlay 元素,Teleport 只负责位移)。
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import ArtIcon from '../ArtIcon.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  size: { type: String, default: 'md' }, // sm | md | lg
  closable: { type: Boolean, default: true },
  closeOnOverlay: { type: Boolean, default: true },
  closeOnEsc: { type: Boolean, default: true },
  label: { type: String, default: '对话框' },
})
const emit = defineEmits(['close'])

// 嵌套弹层(如确认框叠在编辑弹窗上)按打开顺序抬升 z-index;
// 全局打开栈保证 Esc / Tab 只作用于最上层弹层
const zIndex = ref(200)
const modalStack = (globalThis.__zhishiModalStack ||= [])
const stackToken = {}
function bumpZ() {
  const seed = (globalThis.__zhishiModalSeed || 200) + 10
  globalThis.__zhishiModalSeed = seed
  zIndex.value = seed
}

const panel = ref(null)
let previousFocus = null

// closable=false 只隐藏右上角 X 钮;Esc / 遮罩点击是否生效由 closeOnEsc / closeOnOverlay 控制
function close() {
  emit('close')
}
function onOverlayDown(e) {
  if (props.closeOnOverlay && e.target === e.currentTarget) close()
}
function onKeydown(e) {
  // 只响应最上层弹层,避免嵌套场景下 Esc 一次关掉多层
  if (modalStack[modalStack.length - 1] !== stackToken) return
  if (e.key === 'Escape' && props.closeOnEsc) {
    e.stopImmediatePropagation()
    e.preventDefault()
    close()
    return
  }
  if (e.key !== 'Tab' || !panel.value) return
  // 焦点陷阱:Tab 在面板内循环
  const focusables = panel.value.querySelectorAll(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  )
  const list = Array.from(focusables).filter((el) => !el.disabled && el.offsetParent !== null)
  if (!list.length) return
  const first = list[0]
  const last = list[list.length - 1]
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault()
    last.focus()
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault()
    first.focus()
  }
}

async function activate() {
  bumpZ()
  modalStack.push(stackToken)
  previousFocus = document.activeElement
  document.addEventListener('keydown', onKeydown, true)
  await nextTick()
  const target =
    panel.value?.querySelector('[data-autofocus]') ||
    panel.value?.querySelector('input, textarea, select, button:not(.modal-close)') ||
    panel.value
  target?.focus?.()
}
function deactivate() {
  const i = modalStack.indexOf(stackToken)
  if (i !== -1) modalStack.splice(i, 1)
  document.removeEventListener('keydown', onKeydown, true)
  if (previousFocus?.isConnected) previousFocus.focus()
  previousFocus = null
}

watch(
  () => props.open,
  (v) => (v ? activate() : deactivate())
)
onBeforeUnmount(deactivate)
</script>

<template>
  <Teleport to="body">
    <Transition name="pop">
      <div v-if="open" class="modal-overlay" :style="{ zIndex }" @mousedown="onOverlayDown">
        <div
          ref="panel"
          :class="['modal-panel', `size-${size}`]"
          role="dialog"
          aria-modal="true"
          :aria-label="label"
          tabindex="-1"
        >
          <button
            v-if="closable"
            class="ghost modal-close"
            type="button"
            :aria-label="`关闭${label}`"
            @click="close"
          >
            <ArtIcon name="close" tone="pearl" :size="16" />
          </button>
          <slot />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: var(--overlay-bg);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

.modal-panel {
  position: relative;
  width: 100%;
  max-height: calc(100vh - 48px);
  overflow: auto;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl), var(--shadow-inset);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  outline: none;
}

.modal-panel.size-sm {
  max-width: 420px;
}
.modal-panel.size-md {
  max-width: 640px;
}
.modal-panel.size-lg {
  max-width: 860px;
}

.modal-close {
  position: absolute;
  top: 14px;
  right: 14px;
  z-index: 2;
  width: 34px;
  height: 34px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-xs);
}

@media (max-width: 640px) {
  .modal-overlay {
    padding: 12px;
    align-items: flex-end;
  }
  .modal-panel {
    max-height: calc(100vh - 24px);
    border-radius: var(--radius-lg) var(--radius-lg) 0 0;
  }
}
</style>
