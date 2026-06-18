<script setup>
import { ref, watch } from 'vue'
import draggable from 'vuedraggable'
import TaskCard from '../components/TaskCard.vue'

const props = defineProps({
  tasks: { type: Array, required: true },
})
const emit = defineEmits(['open', 'update-status', 'create'])

const COLUMNS = ['待办', '进行中', '完成']
const lists = ref({ 待办: [], 进行中: [], 完成: [] })

function rebuild() {
  lists.value = {
    待办: props.tasks.filter((t) => t.status === '待办'),
    进行中: props.tasks.filter((t) => t.status === '进行中'),
    完成: props.tasks.filter((t) => t.status === '完成'),
  }
}
watch(() => props.tasks, rebuild, { immediate: true })

function onEnd(evt, targetStatus) {
  const item = lists.value[targetStatus]?.[evt.newIndex]
  if (item && item.status !== targetStatus) {
    emit('update-status', item, targetStatus)
  }
}

const columnMeta = {
  待办: {
    icon: '🐚',
    hint: '把任务轻轻放进海里',
    bg: 'linear-gradient(180deg, rgba(165, 223, 247, 0.18) 0%, rgba(165, 223, 247, 0.06) 100%)',
    accent: 'var(--sea-300)',
    shadow: 'rgba(165, 223, 247, 0.35)',
  },
  进行中: {
    icon: '🌊',
    hint: '像海浪一样慢慢推进',
    bg: 'linear-gradient(180deg, rgba(116, 204, 242, 0.16) 0%, rgba(116, 204, 242, 0.04) 100%)',
    accent: 'var(--accent)',
    shadow: 'rgba(116, 204, 242, 0.35)',
  },
  完成: {
    icon: '✨',
    hint: '贝壳已经拾上岸啦',
    bg: 'linear-gradient(180deg, rgba(165, 242, 193, 0.16) 0%, rgba(165, 242, 193, 0.04) 100%)',
    accent: 'var(--foam-400)',
    shadow: 'rgba(165, 242, 193, 0.35)',
  },
}
</script>

<template>
  <div class="board">
    <div class="board-head">
      <div class="board-title">
        <h2 class="gradient-text">任务看板</h2>
        <p class="muted">拖动卡片在列间移动，感受任务随海浪流转。</p>
      </div>
      <button class="create-btn" @click="emit('create')">
        <span class="btn-icon">＋</span>
        <span>新建任务</span>
      </button>
    </div>

    <div class="columns">
      <div
        class="column"
        v-for="(col, index) in COLUMNS"
        :key="col"
        :style="{
          background: columnMeta[col].bg,
          boxShadow: `0 8px 32px ${columnMeta[col].shadow}, var(--shadow-inset)`,
          animationDelay: `${index * 0.08}s`,
        }"
        :class="['animate-in']"
      >
        <div class="col-head">
          <div class="col-title">
            <span class="col-icon-wrap" :style="{ background: `${columnMeta[col].accent}20`, color: columnMeta[col].accent }">
              <span class="col-icon">{{ columnMeta[col].icon }}</span>
            </span>
            <span class="col-name">{{ col }}</span>
          </div>
          <span class="count">{{ lists[col].length }}</span>
        </div>

        <draggable
          :list="lists[col]"
          group="tasks"
          item-key="id"
          :animation="220"
          ghost-class="ghost"
          chosen-class="chosen"
          drag-class="dragging"
          class="col-body"
          :class="{ empty: !lists[col].length }"
          @end="(e) => onEnd(e, col)"
        >
          <template #item="{ element }">
            <TaskCard :task="element" @click="emit('open', element)" />
          </template>
          <template #footer>
            <div v-if="!lists[col].length" class="empty-hint muted">
              <span class="hint-icon float">{{ columnMeta[col].icon }}</span>
              <span>{{ columnMeta[col].hint }}</span>
            </div>
          </template>
        </draggable>

        <div class="col-foot" :style="{ background: columnMeta[col].accent }"></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.board {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 22px;
  max-width: 1440px;
  margin: 0 auto;
}

.board-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-shrink: 0;
}

.board-title h2 {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: 0.5px;
}

.board-title p {
  margin: 6px 0 0;
  font-size: 14px;
}

.create-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 11px 22px;
  border-radius: var(--radius-pill);
  font-size: 14px;
  font-weight: 600;
}

.btn-icon {
  display: inline-block;
  font-size: 16px;
  transition: transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.create-btn:hover .btn-icon {
  transform: rotate(90deg) scale(1.1);
}

.columns {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 20px;
  flex: 1;
  min-height: 0;
}

.column {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 16px;
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  transition: transform 0.3s ease, box-shadow 0.3s ease;
  position: relative;
  overflow: hidden;
}

.column:hover {
  transform: translateY(-3px);
}

.col-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  padding: 0 4px;
}

.col-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.col-icon-wrap {
  width: 36px;
  height: 36px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-inset);
}

.col-icon {
  font-size: 19px;
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.08));
}

.col-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
}

.count {
  background: var(--surface);
  color: var(--text-soft);
  border-radius: var(--radius-pill);
  padding: 3px 11px;
  font-size: 12px;
  font-weight: 700;
  border: 1px solid var(--border);
  box-shadow: var(--shadow-inset);
  min-width: 28px;
  text-align: center;
}

.col-body {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 80px;
  padding: 4px;
  border-radius: var(--radius-sm);
}

.col-body.empty {
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.col-body:deep(.sortable-ghost) {
  opacity: 0.35;
  background: var(--accent-soft);
  border: 2px dashed var(--accent);
  border-radius: var(--radius-sm);
  transform: scale(0.96);
}

.col-body:deep(.sortable-drag) {
  opacity: 0.96;
  transform: rotate(1.5deg) scale(1.03);
  box-shadow: var(--shadow-xl);
}

.empty-hint {
  text-align: center;
  padding: 36px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  opacity: 0.75;
}

.hint-icon {
  font-size: 36px;
  opacity: 0.85;
}

.col-foot {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 4px;
  opacity: 0.6;
  border-radius: 0 0 var(--radius-lg) var(--radius-lg);
}

@media (max-width: 960px) {
  .columns {
    grid-template-columns: 1fr;
    grid-auto-rows: minmax(200px, 1fr);
  }
}

@media (max-width: 640px) {
  .board-head {
    align-items: center;
  }
  .board-title p {
    display: none;
  }
}
</style>
