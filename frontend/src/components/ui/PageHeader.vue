<script setup>
// 统一页面头部:图标 tile + 标题 + 副标题 + 右侧操作区
import ArtIcon from '../ArtIcon.vue'

defineProps({
  icon: { type: String, required: true },
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
})
</script>

<template>
  <header class="page-header">
    <div class="page-title">
      <ArtIcon :name="icon" tone="aqua" :size="44" tile label="" />
      <div class="page-heading">
        <h2>{{ title }}</h2>
        <p v-if="subtitle" class="muted">{{ subtitle }}</p>
      </div>
    </div>
    <div v-if="$slots.actions" class="page-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 18px;
}

.page-title {
  min-width: 0;
}

.page-heading h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 800;
  color: var(--text);
  letter-spacing: 0;
}

.page-heading p {
  margin: 2px 0 0;
}

.page-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

@media (max-width: 640px) {
  .page-heading h2 {
    font-size: 19px;
  }
}
</style>
