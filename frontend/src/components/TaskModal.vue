<script setup>
import { computed, onMounted, ref } from 'vue'
import TaskForm from './TaskForm.vue'
import { attachFile, detachFile, getContentUrl, listFiles } from '../api/files'

const props = defineProps({
  task: { type: Object, default: null },
})
const emit = defineEmits(['save', 'delete', 'close', 'changed'])

const allFiles = ref([])
const selectedFileId = ref('')
const fileError = ref(null)

const attachedIds = computed(() => new Set((props.task?.files || []).map((f) => f.id)))
const attachableFiles = computed(() => allFiles.value.filter((f) => !attachedIds.value.has(f.id)))

onMounted(async () => {
  if (!props.task) return
  try {
    allFiles.value = await listFiles()
  } catch (e) {
    fileError.value = e.message
  }
})

async function doAttach() {
  if (!props.task || !selectedFileId.value) return
  await attachFile(props.task.id, selectedFileId.value)
  selectedFileId.value = ''
  emit('changed')
}

async function doDetach(file) {
  if (!props.task) return
  await detachFile(props.task.id, file.id)
  emit('changed')
}
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <div class="modal">
      <div class="modal-wave"></div>
      <div class="modal-head">
        <div class="modal-title">
          <span class="title-icon">{{ task ? '🐚' : '🌊' }}</span>
          <span>{{ task ? '编辑任务' : '新建任务' }}</span>
        </div>
        <button class="ghost close-btn" @click="emit('close')">✕</button>
      </div>

      <TaskForm :model-value="task" @save="(p) => emit('save', p)" @cancel="emit('close')" />

      <section v-if="task" class="files-section">
        <h3><span class="section-icon">📎</span>关联资料</h3>
        <p v-if="fileError" class="muted error-text">⚠️ {{ fileError }}</p>
        <div v-if="!task.files?.length" class="muted empty-text">还没有关联资料。</div>
        <div class="file-row" v-for="file in task.files" :key="file.id">
          <a :href="getContentUrl(file.id)" target="_blank" :title="file.original_name">
            <span class="file-icon">📎</span>
            <span class="file-name">{{ file.original_name }}</span>
          </a>
          <button class="ghost" @click="doDetach(file)">移除</button>
        </div>
        <div class="attach-row" v-if="attachableFiles.length">
          <select v-model="selectedFileId">
            <option value="">选择资料库文件…</option>
            <option v-for="file in attachableFiles" :key="file.id" :value="file.id">
              {{ file.original_name }}
            </option>
          </select>
          <button type="button" @click="doAttach">添加</button>
        </div>
        <div v-else class="muted empty-text">资料库暂无可添加文件。</div>
      </section>

      <button v-if="task" class="danger" @click="emit('delete', task)">删除任务</button>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(8, 47, 73, 0.3);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 20px;
}

.modal {
  width: 560px;
  max-width: 92vw;
  max-height: 88vh;
  overflow: auto;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl), var(--shadow-inset);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  display: flex;
  flex-direction: column;
  gap: 18px;
  animation: modal-in 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
  position: relative;
  padding: 22px;
}

@keyframes modal-in {
  from {
    opacity: 0;
    transform: translateY(24px) scale(0.96);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.modal-wave {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 5px;
  background: linear-gradient(90deg, var(--sea-300), var(--accent), var(--sea-300));
  opacity: 0.75;
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
}

.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 18px;
  font-weight: 800;
  flex-shrink: 0;
  gap: 12px;
}

.modal-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.modal-title span:last-child {
  background: linear-gradient(135deg, var(--accent), var(--sea-700));
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

[data-theme="dark"] .modal-title span:last-child {
  background: linear-gradient(135deg, var(--accent), var(--sea-300));
  -webkit-background-clip: text;
  background-clip: text;
}

.title-icon {
  font-size: 22px;
}

.close-btn {
  width: 36px;
  height: 36px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  flex-shrink: 0;
}

.files-section {
  margin-top: 2px;
  padding-top: 18px;
  border-top: 1px solid var(--border);
}

.files-section h3 {
  margin: 0 0 12px;
  font-size: 15px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-icon {
  font-size: 16px;
}

.error-text {
  color: var(--pri-high);
}

.empty-text {
  padding: 8px 0;
}

.file-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 9px 12px;
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  margin-bottom: 7px;
  border: 1px solid transparent;
  transition: border-color 0.2s ease;
}

.file-row:hover {
  border-color: var(--border);
}

.file-row a {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--text);
  text-decoration: none;
  overflow: hidden;
  min-width: 0;
}

.file-icon {
  flex-shrink: 0;
}

.file-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-row button {
  padding: 5px 12px;
  font-size: 13px;
  flex-shrink: 0;
}

.attach-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  margin-top: 12px;
}

.danger {
  margin-top: 2px;
}

@media (max-width: 520px) {
  .attach-row {
    grid-template-columns: 1fr;
  }
}
</style>
