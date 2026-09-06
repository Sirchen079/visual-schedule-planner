<script setup lang="ts">
/**
 * 域视图通用状态块（加载与错误状态）：
 * - loading：行内进行时文案（不转圈遮屏）
 * - error：赤陶虚线警告 + 重试按钮
 * - empty：衬线留白文案（真实无数据时的引导，可带插槽正文）
 * 视图按 v-if 组合使用，保证任何时刻至少一种状态在屏。
 */
defineProps<{
  loading?: boolean
  loadingText?: string
  error?: string | null
  empty?: boolean
  emptyTitle?: string
}>()

const emit = defineEmits<{ retry: [] }>()
</script>

<template>
  <div v-if="loading" class="ds-loading">{{ loadingText ?? '正在拉取数据…' }}</div>
  <div v-else-if="error" class="ds-error">
    <span>{{ error }}</span>
    <button class="ds-retry" @click="emit('retry')">重试</button>
  </div>
  <div v-else-if="empty" class="ds-empty">
    <div class="ds-mark">{{ emptyTitle ?? '暂无内容' }}</div>
    <p class="ds-line"><slot /></p>
  </div>
</template>

<style scoped>
.ds-loading {
  padding: 14px 2px;
  font-size: 12.5px;
  color: var(--ink-3);
  letter-spacing: 0.02em;
}
.ds-error {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-start;
  font-size: 12.5px;
  color: var(--terra-soft);
  border: 1px dashed var(--terra-dashed);
  border-radius: var(--radius-s);
  padding: 10px 12px;
  margin: 10px 0;
}
.ds-retry {
  font-size: 12px;
  color: var(--amber-soft);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-s);
  padding: 3px 10px;
}
.ds-retry:hover {
  border-color: var(--line-hover);
}
.ds-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  text-align: center;
  padding: 56px 32px;
}
.ds-mark {
  font-family: var(--serif);
  font-size: 22px;
  font-weight: 600;
  letter-spacing: 0.14em;
  color: var(--ink-2);
  margin-bottom: 6px;
}
.ds-line {
  font-size: 13px;
  color: var(--ink-3);
  line-height: 1.8;
  max-width: 420px;
}
</style>
