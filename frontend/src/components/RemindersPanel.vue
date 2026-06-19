<script setup>
defineProps({
  upcoming: { type: Array, required: true },
  overdue: { type: Array, required: true },
})
const emit = defineEmits(['open', 'close'])

function fmt(d) {
  if (!d) return ''
  return new Date(d).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <div class="panel">
      <div class="panel-wave"></div>
      <div class="head">
        <div class="head-title">
          <span class="bell-icon">🔔</span>
          <span>提醒</span>
        </div>
        <button class="ghost close-btn" @click="emit('close')">✕</button>
      </div>

      <section v-if="overdue.length" class="section">
        <h3 class="section-title overdue-title">
          <span class="title-dot" style="background: var(--pri-high)"></span>
          已逾期（{{ overdue.length }}）
        </h3>
        <div class="item overdue" v-for="t in overdue" :key="t.id" @click="emit('open', t)">
          <div class="item-main">
            <span class="title">{{ t.title }}</span>
            <span class="muted">{{ fmt(t.due_date) }}</span>
          </div>
          <span class="tag urgent">逾期</span>
        </div>
      </section>

      <section v-if="upcoming.length" class="section">
        <h3 class="section-title">
          <span class="title-dot" style="background: var(--accent)"></span>
          即将到期（24 小时内，{{ upcoming.length }}）
        </h3>
        <div class="item" v-for="t in upcoming" :key="t.id" @click="emit('open', t)">
          <div class="item-main">
            <span class="title">{{ t.title }}</span>
            <span class="muted">{{ fmt(t.due_date) }}</span>
          </div>
          <span class="tag soon">快到期</span>
        </div>
      </section>

      <div v-if="!overdue.length && !upcoming.length" class="empty">
        <div class="empty-icon float-slow">🌊</div>
        <div class="empty-title">海面平静</div>
        <div class="muted">暂无到期或逾期任务</div>
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
  animation: panel-in 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
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

.panel-wave {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 5px;
  background: linear-gradient(90deg, var(--sea-300), var(--accent), var(--sea-300));
  opacity: 0.75;
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.head-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 18px;
  font-weight: 800;
  background: linear-gradient(135deg, var(--accent), var(--sea-700));
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

[data-theme="dark"] .head-title {
  background: linear-gradient(135deg, var(--accent), var(--sea-300));
  -webkit-background-clip: text;
  background-clip: text;
}

.bell-icon {
  font-size: 20px;
  -webkit-text-fill-color: initial;
}

.close-btn {
  width: 34px;
  height: 34px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
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

.title-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
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
  transform: translateX(4px);
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

.empty-icon {
  font-size: 40px;
  opacity: 0.7;
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
