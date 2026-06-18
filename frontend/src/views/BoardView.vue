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

// 拖动结束：若卡片被移到新列，通知父组件更新 status
function onEnd(evt, targetStatus) {
  const item = lists.value[targetStatus]?.[evt.newIndex]
  if (item && item.status !== targetStatus) {
    emit('update-status', item, targetStatus)
  }
}
</script>

<template>
  <div class="board">
    <div class="board-head">
      <span class="muted">拖动卡片在列间移动即可更改状态</span>
      <button @click="emit('create')">+ 新建任务</button>
    </div>
    <div class="columns">
      <div class="column" v-for="col in COLUMNS" :key="col">
        <div class="col-head">
          <span>{{ col }}</span>
          <span class="count">{{ lists[col].length }}</span>
        </div>
        <draggable
          :list="lists[col]"
          group="tasks"
          item-key="id"
          :animation="160"
          ghost-class="ghost"
          class="col-body"
          @end="(e) => onEnd(e, col)"
        >
          <template #item="{ element }">
            <TaskCard :task="element" @click="emit('open', element)" />
          </template>
        </draggable>
      </div>
    </div>
  </div>
</template>

<style scoped>
.board {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 14px;
}
.board-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.columns {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  flex: 1;
  min-height: 0;
}
.column {
  display: flex;
  flex-direction: column;
  background: var(--surface-2);
  border-radius: var(--radius);
  padding: 12px;
}
.col-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  margin-bottom: 12px;
  padding: 0 4px;
}
.count {
  background: var(--surface);
  color: var(--text-soft);
  border-radius: 999px;
  padding: 1px 9px;
  font-size: 12px;
}
.col-body {
  flex: 1;
  overflow-y: auto;
  min-height: 60px;
}
.ghost {
  opacity: 0.4;
}
</style>
