<script setup>
// 统一空状态:图标 + 标题 + 提示 + 可选操作
import ArtIcon from '../ArtIcon.vue'

defineProps({
  icon: { type: String, default: 'task' },
  title: { type: String, default: '暂无内容' },
  hint: { type: String, default: '' },
  compact: { type: Boolean, default: false },
})
</script>

<template>
  <div :class="['empty-state', { compact }]">
    <ArtIcon :name="icon" tone="pearl" :size="compact ? 34 : 44" tile />
    <p class="empty-title">{{ title }}</p>
    <p v-if="hint" class="empty-hint muted">{{ hint }}</p>
    <div v-if="$slots.default" class="empty-actions">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.empty-state {
  display: grid;
  place-items: center;
  justify-items: center;
  gap: 8px;
  min-height: 220px;
  padding: 28px 24px;
  text-align: center;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--surface-2) 80%, transparent);
}

.empty-state.compact {
  min-height: 120px;
  padding: 18px 16px;
}

.empty-title {
  margin: 4px 0 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--text-soft);
}

.empty-hint {
  margin: 0;
  max-width: 420px;
}

.empty-actions {
  margin-top: 8px;
  display: flex;
  gap: 10px;
}
</style>
