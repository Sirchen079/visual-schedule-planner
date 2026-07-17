<script setup>
// 统一加载指示器
defineProps({
  size: { type: String, default: 'md' }, // sm | md | lg
  label: { type: String, default: '' },
})
</script>

<template>
  <span :class="['app-spinner', `size-${size}`]" role="status" :aria-label="label || '加载中'">
    <span class="spinner-ring"></span>
    <span v-if="label" class="spinner-label muted">{{ label }}</span>
  </span>
</template>

<style scoped>
.app-spinner {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.spinner-ring {
  display: inline-block;
  border: 3px solid var(--surface-2);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

.size-sm .spinner-ring {
  width: 16px;
  height: 16px;
  border-width: 2px;
}
.size-md .spinner-ring {
  width: 26px;
  height: 26px;
}
.size-lg .spinner-ring {
  width: 36px;
  height: 36px;
}
</style>
