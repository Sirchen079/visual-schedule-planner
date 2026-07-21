<script setup>
// 渐进式一次性提示条：首次进入某视图时给一句温和提示，「知道了」关闭并
// 写入 localStorage（zs-tip-* 键）后不再出现。设置里「重置新手提示」可清除。
import { ref } from 'vue'
import ArtIcon from '../ArtIcon.vue'

const props = defineProps({
  // localStorage 键（沿用 zs-* 惯例，如 zs-tip-calendar）
  tipKey: { type: String, required: true },
  icon: { type: String, default: 'bell' },
  text: { type: String, required: true },
})

const visible = ref(false)
try {
  visible.value = !localStorage.getItem(props.tipKey)
} catch {
  visible.value = false
}

function dismiss() {
  visible.value = false
  try {
    localStorage.setItem(props.tipKey, '1')
  } catch {
    // 隐私模式等写入失败时，本次关闭仍生效
  }
}
</script>

<template>
  <Transition name="tip">
    <div v-if="visible" class="first-run-tip" role="note">
      <ArtIcon :name="icon" tone="aqua" :size="18" label="提示" />
      <span class="tip-text">{{ text }}</span>
      <button class="ghost tip-close" type="button" @click="dismiss">知道了</button>
    </div>
  </Transition>
</template>

<style scoped>
.first-run-tip {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: var(--radius-sm);
  background: var(--accent-soft);
  border: 1px solid color-mix(in srgb, var(--accent) 22%, var(--border));
  box-shadow: var(--shadow-xs);
  flex-shrink: 0;
}

.first-run-tip :deep(.art-icon) {
  flex-shrink: 0;
}

.tip-text {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text);
}

.tip-close {
  flex-shrink: 0;
  padding: 5px 14px;
  font-size: 12px;
  font-weight: 700;
  color: var(--accent-strong);
}

.tip-enter-active,
.tip-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}

.tip-enter-from,
.tip-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
