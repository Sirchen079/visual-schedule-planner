<script setup>
// 应用内确认对话框：替代原生 confirm()，复用全局视觉系统与 BaseModal 基座
// (Esc / 点遮罩 = 取消,Enter = 确认,焦点陷阱与 z-index 由 BaseModal 统一处理)。
import ArtIcon from './ArtIcon.vue'
import BaseModal from './ui/BaseModal.vue'

const props = defineProps({
  open: Boolean,
  title: { type: String, default: '请确认' },
  message: { type: String, default: '' },
  confirmText: { type: String, default: '确定' },
  cancelText: { type: String, default: '取消' },
  danger: { type: Boolean, default: false },
})
const emit = defineEmits(['confirm', 'cancel'])

// 焦点在按钮上时让按钮自身的 click 生效,避免取消按钮上按 Enter 误触发确认
function onEnter(e) {
  if (e.target.closest('button')) return
  emit('confirm')
}
</script>

<template>
  <BaseModal
    :open="open"
    size="sm"
    :closable="false"
    :label="title"
    @close="emit('cancel')"
  >
    <div class="confirm-body" @keydown.enter.prevent="onEnter">
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
        <button class="ghost cancel-btn" type="button" @click="emit('cancel')">
          {{ cancelText }}
        </button>
        <button class="confirm-btn" type="button" :class="{ danger }" @click="emit('confirm')">
          {{ confirmText }}
        </button>
      </div>
    </div>
  </BaseModal>
</template>

<style scoped>
.confirm-body {
  padding: 28px 22px 22px;
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
  background: color-mix(in srgb, var(--danger) 12%, transparent);
  border-color: color-mix(in srgb, var(--danger) 28%, transparent);
}

.title {
  font-size: 17px;
  font-weight: 800;
  color: var(--text);
}

.message {
  margin: 8px auto 0;
  font-size: 13px;
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
}

.confirm-btn {
  padding: 9px 18px;
  font-weight: 700;
  background: var(--btn-gradient);
  box-shadow: 0 4px 12px var(--accent-glow-strong);
}

.confirm-btn:hover {
  background: var(--btn-gradient-hover);
}

.confirm-btn.danger {
  background: linear-gradient(135deg, var(--danger), var(--danger-strong));
  border-color: color-mix(in srgb, var(--danger) 40%, var(--border));
  box-shadow: 0 4px 12px color-mix(in srgb, var(--danger) 30%, transparent);
}

.confirm-btn.danger:hover {
  background: var(--danger);
}
</style>
