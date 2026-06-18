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
    <div class="panel card">
      <div class="head">
        <span>🔔 提醒</span>
        <button class="ghost" @click="emit('close')">✕</button>
      </div>

      <section v-if="overdue.length">
        <h3 class="overdue-title">⚠️ 已逾期（{{ overdue.length }}）</h3>
        <div class="item overdue" v-for="t in overdue" :key="t.id" @click="emit('open', t)">
          <span class="title">{{ t.title }}</span>
          <span class="muted">{{ fmt(t.due_date) }}</span>
        </div>
      </section>

      <section v-if="upcoming.length">
        <h3>⏰ 即将到期（24 小时内，{{ upcoming.length }}）</h3>
        <div class="item" v-for="t in upcoming" :key="t.id" @click="emit('open', t)">
          <span class="title">{{ t.title }}</span>
          <span class="muted">{{ fmt(t.due_date) }}</span>
        </div>
      </section>

      <div v-if="!overdue.length && !upcoming.length" class="empty muted">
        🌊 海面平静，暂无到期或逾期任务。
      </div>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  z-index: 120;
  background: rgba(23, 74, 102, 0.35);
  backdrop-filter: blur(2px);
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  padding: 72px 24px;
}
.panel {
  width: 380px;
  max-width: 92vw;
  max-height: 70vh;
  overflow: auto;
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 17px;
  font-weight: 700;
  margin-bottom: 12px;
}
section {
  margin-bottom: 14px;
}
h3 {
  margin: 0 0 8px;
  font-size: 14px;
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
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  margin-bottom: 6px;
  background: var(--surface-2);
}
.item:hover {
  background: var(--surface-3);
}
.item.overdue {
  border-left: 3px solid var(--pri-high);
}
.title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}
.empty {
  text-align: center;
  padding: 30px 10px;
}
</style>
