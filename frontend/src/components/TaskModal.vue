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
    <div class="modal card">
      <div class="modal-head">
        <span>{{ task ? '编辑任务' : '新建任务' }}</span>
        <button class="ghost" @click="emit('close')">✕</button>
      </div>
      <TaskForm :model-value="task" @save="(p) => emit('save', p)" @cancel="emit('close')" />

      <section v-if="task" class="files-section">
        <h3>关联资料</h3>
        <p v-if="fileError" class="muted">⚠️ {{ fileError }}</p>
        <div v-if="!task.files?.length" class="muted">还没有关联资料。</div>
        <div class="file-row" v-for="file in task.files" :key="file.id">
          <a :href="getContentUrl(file.id)" target="_blank" :title="file.original_name">📎 {{ file.original_name }}</a>
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
        <div v-else class="muted">资料库暂无可添加文件。</div>
      </section>

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
  width: 560px;
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
.files-section {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}
.files-section h3 {
  margin: 0 0 10px;
  font-size: 15px;
}
.file-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 6px 0;
}
.file-row a {
  color: var(--text);
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.attach-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  margin-top: 10px;
}
.danger {
  margin-top: 12px;
}
</style>
