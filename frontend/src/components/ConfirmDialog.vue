<script setup>
// 应用内确认对话框：替代原生 confirm()，复用全局视觉系统。
// 支持 danger 样式（彻底删除等不可恢复操作）与键盘操作（Enter 确认 / Esc 取消）。
import { onMounted, onBeforeUnmount } from 'vue'
import ArtIcon from './ArtIcon.vue'

const props = defineProps({
  open: Boolean,
  title: { type: String, default: '请确认' },
  message: { type: String, default: '' },
  confirmText: { type: String, default: '确定' },
  cancelText: { type: String, default: '取消' },
  danger: { type: Boolean, default: false },
})
const emit = defineEmits(['confirm', 'cancel'])

function onKeydown(e) {
  if (!props.open) return
  if (e.key === 'Escape') emit('cancel')
  else if (e.key === 'Enter') emit('confirm')
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Transition name="confirm">
    <div v-if="open" class="overlay" @click.self="emit('cancel')">
      <div class="dialog" role="dialog" aria-modal="true">
        <div class="icon-wrap" :class="{ danger }">
          <ArtIcon
            :name="danger ? 'trash' : 'assistant'"
            :tone="danger ? 'coral' : 'aqua'"
            :size="30"
            tile
            :label="title"
          />
        </div>
        <div class="title">{{ title }}</div>
        <p v-if="message" class="message">{{ message }}</p>
        <div class="actions">
          <button class="ghost cancel-btn" @click="emit('cancel')">{{ cancelText }}</button>
          <button class="confirm-btn" :class="{ danger }" @click="emit('confirm')">
            {{ confirmText }}
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  z-index: 150;
  background: rgba(8, 47, 73, 0.34);
  backdrop-filter: blur(7px);
  -webkit-backdrop-filter: blur(7px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.dialog {
  width: 400px;
  max-width: 92vw;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl), var(--shadow-inset);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  padding: 24px 22px 20px;
  text-align: center;
}
.icon-wrap {
  width: 58px;
  height: 58px;
  margin: 0 auto 13px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-soft);
  border: 1px solid color-mix(in srgb, var(--accent) 22%, var(--border));
}
.icon-wrap.danger {
  background: rgba(242, 107, 122, 0.12);
  border-color: rgba(242, 107, 122, 0.28);
}
.title {
  font-size: 17px;
  font-weight: 800;
  color: var(--text);
}
.message {
  margin: 8px auto 0;
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--text-soft);
  max-width: 34ch;
}
.actions {
  display: flex;
  justify-content: center;
  gap: 10px;
  margin-top: 20px;
}
.cancel-btn {
  padding: 9px 18px;
  border-radius: var(--radius-sm);
  font-size: 13.5px;
}
.confirm-btn {
  padding: 9px 18px;
  border-radius: var(--radius-sm);
  font-size: 13.5px;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, var(--accent), #62b8d2);
  border: 1px solid color-mix(in srgb, var(--accent) 40%, var(--border));
  box-shadow: 0 4px 12px rgba(59, 152, 198, 0.28);
  transition: filter 0.15s ease, transform 0.15s ease;
}
.confirm-btn:hover {
  background: linear-gradient(135deg, var(--accent-hover), var(--accent));
}
.confirm-btn:active {
  transform: scale(0.97);
}
.confirm-btn.danger {
  background: linear-gradient(135deg, var(--pri-high), #e0526b);
  border-color: color-mix(in srgb, var(--pri-high) 40%, var(--border));
  box-shadow: 0 4px 12px rgba(242, 107, 122, 0.3);
}
.confirm-btn.danger:hover {
  filter: brightness(1.05);
}

.confirm-enter-active,
.confirm-leave-active {
  transition: opacity 0.2s ease;
}
.confirm-enter-active .dialog,
.confirm-leave-active .dialog {
  transition: opacity 0.22s ease, transform 0.28s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.confirm-enter-from,
.confirm-leave-to {
  opacity: 0;
}
.confirm-enter-from .dialog,
.confirm-leave-to .dialog {
  opacity: 0;
  transform: translateY(12px) scale(0.95);
}
</style>
