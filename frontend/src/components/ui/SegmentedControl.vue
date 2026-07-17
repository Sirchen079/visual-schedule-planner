<script setup>
// 统一分段控件
// <SegmentedControl v-model="mode" :options="[{ value: 'day', label: '日' }]" />
import ArtIcon from '../ArtIcon.vue'

defineProps({
  modelValue: { type: [String, Number], required: true },
  options: { type: Array, required: true }, // [{ value, label, icon? }]
  size: { type: String, default: 'md' }, // sm | md
})
const emit = defineEmits(['update:modelValue'])
</script>

<template>
  <div :class="['seg-control', `size-${size}`]" role="tablist">
    <button
      v-for="opt in options"
      :key="opt.value"
      type="button"
      role="tab"
      :aria-selected="modelValue === opt.value"
      :class="['seg-item', modelValue === opt.value && 'active']"
      @click="emit('update:modelValue', opt.value)"
    >
      <ArtIcon v-if="opt.icon" :name="opt.icon" :tone="modelValue === opt.value ? 'aqua' : 'pearl'" :size="16" />
      <span>{{ opt.label }}</span>
    </button>
  </div>
</template>

<style scoped>
.seg-control {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 4px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-inset);
}

.seg-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: transparent;
  color: var(--text-soft);
  border: 1px solid transparent;
  border-radius: var(--radius-xs);
  font-weight: 650;
  white-space: nowrap;
  box-shadow: none;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}

.size-md .seg-item {
  padding: 7px 14px;
  font-size: 13px;
}
.size-sm .seg-item {
  padding: 5px 10px;
  font-size: 12px;
}

.seg-item.active {
  color: var(--accent-strong);
  background: var(--accent-soft);
  border-color: color-mix(in srgb, var(--accent) 22%, var(--border));
}

.seg-item:not(.active):hover {
  color: var(--text);
  background: color-mix(in srgb, var(--surface-solid) 60%, transparent);
}
</style>
