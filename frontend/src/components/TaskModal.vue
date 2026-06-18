<script setup>
import TaskForm from './TaskForm.vue'

defineProps({
  task: { type: Object, default: null },
})
const emit = defineEmits(['save', 'delete', 'close'])
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <div class="modal card">
      <div class="modal-head">
        <span>{{ task ? '编辑任务' : '新建任务' }}</span>
        <button class="ghost" @click="emit('close')">✕</button>
      </div>
      <TaskForm :model-value="task" @save="(p) => emit('save', p)" @cancel="emit('close')" />
      <button v-if="task" class="danger" @click="emit('delete', task)">删除任务</button>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(60, 55, 50, 0.35);
  backdrop-filter: blur(2px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.modal {
  width: 480px;
  max-width: 92vw;
  max-height: 88vh;
  overflow: auto;
}
.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 17px;
  font-weight: 600;
  margin-bottom: 14px;
}
.danger {
  margin-top: 12px;
}
</style>
