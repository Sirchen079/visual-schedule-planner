<script setup>
import { onBeforeUnmount, onMounted } from 'vue'
import ArtIcon from './ArtIcon.vue'

defineProps({
  upcoming: { type: Array, required: true },
  overdue: { type: Array, required: true },
})
const emit = defineEmits(['open', 'close'])

function onKeydown(event) {
  if (event.key === 'Escape') emit('close')
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

function fmt(d) {
  if (!d) return ''
  return new Date(d).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <div class="panel">
      <div class="head">
        <div class="head-title">
          <ArtIcon name="bell" tone="aqua" :size="28" tile label="提醒" />
          <span>提醒</span>
        </div>
        <button class="ghost close-btn" @click="emit('close')">
          <ArtIcon name="close" tone="pearl" :size="18" />
          <span>关闭</span>
        </button>
      </div>

      <section v-if="overdue.length" class="section">
        <h3 class="section-title overdue-title">
          <ArtIcon name="priority" tone="coral" :size="18" />
          已逾期（{{ overdue.length }}）
        </h3>
        <div class="item overdue" v-for="t in overdue" :key="t.id" @click="emit('open', t)">
          <div class="item-main">
            <span class="title">{{ t.title }}</span>
            <span class="muted">{{ fmt(t.due_date) }}</span>
          </div>
          <span class="tag urgent">
            <ArtIcon name="priority" tone="coral" :size="15" />
            <span>逾期</span>
          </span>
        </div>
      </section>

      <section v-if="upcoming.length" class="section">
        <h3 class="section-title">
          <ArtIcon name="calendar" tone="aqua" :size="18" />
          即将到期（24 小时内，{{ upcoming.length }}）
        </h3>
        <div class="item" v-for="t in upcoming" :key="t.id" @click="emit('open', t)">
          <div class="item-main">
            <span class="title">{{ t.title }}</span>
            <span class="muted">{{ fmt(t.due_date) }}</span>
          </div>
          <span class="tag soon">
            <ArtIcon name="bell" tone="aqua" :size="15" />
            <span>快到期</span>
          </span>
        </div>
      </section>

      <div v-if="!overdue.length && !upcoming.length" class="empty">
        <div class="empty-title">节奏平稳</div>
        <div class="muted">暂无到期或逾期任务。</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  z-index: 120;
  background: rgba(23, 74, 102, 0.28);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  padding: 82px 24px 24px;
  animation: overlay-in 0.25s ease;
}

@keyframes overlay-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

.panel {
  width: 400px;
  max-width: 92vw;
  max-height: calc(100vh - 110px);
  overflow: auto;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl), var(--shadow-inset);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  padding: 22px;
  animation: panel-in 0.22s ease-out;
  position: relative;
}

@keyframes panel-in {
  from {
    opacity: 0;
    transform: translateX(30px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.head-title {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  font-size: 18px;
  font-weight: 800;
  color: var(--text);
}

.close-btn {
  min-height: 34px;
  padding: 7px 12px;
  display: flex;
  align-items: center;
  gap: 5px;
  justify-content: center;
  border-radius: var(--radius-sm);
}

.section {
  margin-bottom: 18px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-soft);
}

.overdue-title {
  color: var(--pri-high);
}

.item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 11px 13px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  margin-bottom: 7px;
  background: var(--surface-2);
  border: 1px solid transparent;
  transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease, background 0.15s ease;
}

.item:hover {
  transform: translateX(2px);
  box-shadow: var(--shadow-sm);
  border-color: var(--border);
  background: var(--surface);
}

.item-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
  font-size: 14px;
}

.tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 700;
  padding: 3px 9px;
  border-radius: var(--radius-pill);
  flex-shrink: 0;
}

.tag.urgent {
  background: rgba(242, 107, 122, 0.12);
  color: var(--pri-high);
}

.tag.soon {
  background: rgba(69, 184, 235, 0.1);
  color: var(--accent-hover);
}

.empty {
  text-align: center;
  padding: 40px 10px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.empty-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

@media (max-width: 480px) {
  .overlay {
    padding: 76px 12px 12px;
  }
  .panel {
    width: 100%;
    max-height: calc(100vh - 95px);
    padding: 18px;
  }
}
</style>
