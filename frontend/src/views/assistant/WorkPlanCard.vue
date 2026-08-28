<script setup>
// 阶段 C2：工作清单卡片（agent TodoList 实时可视化）。
// 渲染 agent 调用 update_work_plan 产出的步骤清单：pending / in_progress / done 三态，
// in_progress 项高亮脉冲动画，run 结束后折叠为「已完成 N 项」摘要。
import { computed, ref, watch } from 'vue'
import ArtIcon from '../../components/ArtIcon.vue'

const props = defineProps({
  items: { type: Array, default: () => [] },
  collapsed: { type: Boolean, default: false },
})
const emit = defineEmits(['toggle-collapse'])

const counts = computed(() => {
  const total = props.items.length
  const done = props.items.filter((i) => i.status === 'done').length
  const inProgress = props.items.filter((i) => i.status === 'in_progress').length
  return { total, done, inProgress }
})

const allDone = computed(() => counts.value.total > 0 && counts.value.done === counts.value.total)

const localCollapsed = ref(props.collapsed)
watch(allDone, (done) => {
  // 全部完成时自动折叠为摘要
  if (done) localCollapsed.value = true
})
</script>

<template>
  <section v-if="items.length" class="work-plan-card" :class="{ done: allDone }">
    <header class="wp-head" @click="localCollapsed = !localCollapsed">
      <ArtIcon name="check" :tone="allDone ? 'mint' : 'aqua'" :size="18" />
      <strong>工作清单</strong>
      <span class="wp-progress">{{ counts.done }}/{{ counts.total }}</span>
      <span v-if="allDone" class="wp-done-tag">已全部完成</span>
      <span v-else-if="counts.inProgress" class="wp-progress-bar">
        <span class="wp-progress-fill" :style="{ width: `${(counts.done / counts.total) * 100}%` }" />
      </span>
      <button type="button" class="wp-toggle" :aria-label="localCollapsed ? '展开' : '折叠'">
        {{ localCollapsed ? '▸' : '▾' }}
      </button>
    </header>
    <ol v-show="!localCollapsed" class="wp-items">
      <li
        v-for="item in items"
        :key="item.id"
        class="wp-item"
        :data-status="item.status"
      >
        <span class="wp-bullet" aria-hidden="true">
          {{ item.status === 'done' ? '✓' : item.status === 'in_progress' ? '◌' : '○' }}
        </span>
        <span class="wp-title">{{ item.title }}</span>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.work-plan-card {
  margin: 8px 0;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--surface-2) 70%, transparent);
}

.work-plan-card.done {
  border-color: color-mix(in srgb, var(--success) 40%, var(--border));
  background: color-mix(in srgb, var(--success) 6%, transparent);
}

.wp-head {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
}

.wp-head strong {
  font-size: 12px;
  color: var(--text);
}

.wp-progress {
  margin-left: auto;
  font-size: 11px;
  font-weight: 800;
  color: var(--text-soft);
}

.wp-done-tag {
  font-size: 11px;
  font-weight: 700;
  color: var(--success);
}

.wp-progress-bar {
  flex: 1;
  max-width: 120px;
  height: 4px;
  border-radius: var(--radius-pill);
  background: var(--surface-3);
  overflow: hidden;
}

.wp-progress-fill {
  display: block;
  height: 100%;
  background: var(--accent);
  transition: width 0.3s;
}

.wp-toggle {
  border: none;
  background: none;
  color: var(--text-soft);
  font-size: 12px;
  cursor: pointer;
}

.wp-items {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  display: grid;
  gap: 4px;
}

.wp-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px;
  border-radius: var(--radius-xs);
  font-size: 12px;
}

.wp-item[data-status='done'] {
  color: var(--text-muted);
}

.wp-item[data-status='done'] .wp-title {
  text-decoration: line-through;
}

.wp-item[data-status='in_progress'] {
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  color: var(--accent-strong);
  font-weight: 700;
}

.wp-item[data-status='in_progress'] .wp-bullet {
  animation: wp-pulse 1.2s ease-in-out infinite;
}

.wp-bullet {
  display: inline-flex;
  width: 16px;
  justify-content: center;
  font-size: 13px;
  font-weight: 800;
}

.wp-item[data-status='done'] .wp-bullet {
  color: var(--success);
}

.wp-item[data-status='pending'] .wp-bullet {
  color: var(--text-muted);
}

@keyframes wp-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
