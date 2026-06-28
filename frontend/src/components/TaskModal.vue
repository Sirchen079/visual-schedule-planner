<script setup>
import { computed, onMounted, ref } from 'vue'
import TaskForm from './TaskForm.vue'
import ArtIcon from './ArtIcon.vue'
import { attachFile, detachFile, getContentUrl, listFiles } from '../api/files'
import { createSubtask, deleteSubtask, updateSubtask } from '../api/tasks'

const props = defineProps({
  task: { type: Object, default: null },
})
const emit = defineEmits(['save', 'delete', 'close', 'changed'])

const allFiles = ref([])
const selectedFileId = ref('')
const fileError = ref(null)

const attachedIds = computed(() => new Set((props.task?.files || []).map((f) => f.id)))
const attachableFiles = computed(() => allFiles.value.filter((f) => !attachedIds.value.has(f.id)))

function isLink(file) {
  return Boolean(file?.source_url)
}

function fileHref(file) {
  return isLink(file) ? file.source_url : getContentUrl(file.id)
}

function fileIcon(file) {
  if (file?.resource_type === 'video') return { name: 'file', labelText: 'VID', tone: 'sand' }
  if (isLink(file)) return { name: 'link', labelText: 'LINK', tone: 'aqua' }
  return { name: 'file', labelText: 'FILE', tone: 'pearl' }
}

function fileSubtitle(file) {
  if (isLink(file)) {
    try {
      return `${file.resource_type || 'link'} · ${new URL(file.source_url).hostname}`
    } catch {
      return `${file.resource_type || 'link'} · ${file.source_url}`
    }
  }
  return file.mime_type || '文件'
}

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

// 子任务：本地维护列表，增删/勾选后通知父组件刷新（进度由后端按完成率联动）
const subtasks = ref([...(props.task?.subtasks || [])])
const newSub = ref('')
const subDoneCount = computed(() => subtasks.value.filter((s) => s.done).length)
const subPct = computed(() =>
  subtasks.value.length
    ? Math.round((subDoneCount.value / subtasks.value.length) * 100)
    : 0
)

async function addSub() {
  if (!props.task || !newSub.value.trim()) return
  const s = await createSubtask(props.task.id, newSub.value.trim())
  subtasks.value.push(s)
  newSub.value = ''
  emit('changed')
}
async function toggleSub(s) {
  const updated = await updateSubtask(props.task.id, s.id, { done: !s.done })
  const i = subtasks.value.findIndex((x) => x.id === s.id)
  if (i !== -1) subtasks.value[i] = updated
  emit('changed')
}
async function removeSub(s) {
  await deleteSubtask(props.task.id, s.id)
  subtasks.value = subtasks.value.filter((x) => x.id !== s.id)
  emit('changed')
}
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <div class="modal">
      <div class="modal-head">
        <div class="modal-title">{{ task ? '编辑任务' : '新建任务' }}</div>
        <button class="ghost close-btn" @click="emit('close')">
          <ArtIcon name="close" tone="pearl" :size="18" />
          <span>关闭</span>
        </button>
      </div>

      <TaskForm :model-value="task" @save="(p) => emit('save', p)" @cancel="emit('close')" />

      <section v-if="task" class="files-section">
        <h3>
          <ArtIcon name="library" tone="aqua" :size="24" tile label="关联资料" />
          <span>关联资料</span>
        </h3>
        <p v-if="fileError" class="muted error-text">{{ fileError }}</p>
        <div v-if="!task.files?.length" class="muted empty-text">还没有关联资料。</div>
        <div class="file-row" v-for="file in task.files" :key="file.id">
          <a :href="fileHref(file)" target="_blank" rel="noopener noreferrer" :title="file.original_name">
            <ArtIcon
              class="file-art compact"
              :name="fileIcon(file).name"
              :tone="fileIcon(file).tone"
              :label-text="fileIcon(file).labelText"
              :label="fileIcon(file).labelText + ' 资料'"
              :size="40"
              tile
            />
            <span class="file-copy">
              <span class="file-name">{{ file.original_name }}</span>
              <span class="file-subtitle">{{ fileSubtitle(file) }}</span>
            </span>
          </a>
          <button class="ghost icon-text-btn" @click="doDetach(file)">
            <ArtIcon name="close" tone="pearl" :size="16" />
            <span>移除</span>
          </button>
        </div>
        <div class="attach-row" v-if="attachableFiles.length">
          <select v-model="selectedFileId">
            <option value="">选择资料库文件…</option>
            <option v-for="file in attachableFiles" :key="file.id" :value="file.id">
              {{ file.original_name }}
            </option>
          </select>
          <button type="button" @click="doAttach">
            <ArtIcon name="plus" tone="pearl" :size="18" />
            <span>添加</span>
          </button>
        </div>
        <div v-else class="muted empty-text">资料库暂无可添加文件。</div>
      </section>

      <section v-if="task" class="subtasks-section">
        <h3>
          <ArtIcon name="steps" tone="mint" :size="24" tile label="子任务" />
          <span>子任务</span>
          <span class="muted hint">进度按完成率自动计算</span>
        </h3>
        <div v-if="subtasks.length" class="sub-progress">
          <span class="sub-progress-text">{{ subDoneCount }}/{{ subtasks.length }} 完成 · {{ subPct }}%</span>
          <span class="sub-progress-bar">
            <span class="sub-progress-fill" :style="{ width: subPct + '%' }"></span>
          </span>
        </div>
        <div v-if="!subtasks.length" class="muted empty-text">还没有子任务，拆成小步更容易推进。</div>
        <div class="subtask-row" :class="{ done: s.done }" v-for="s in subtasks" :key="s.id">
          <label class="sub-check">
            <input type="checkbox" :checked="s.done" @change="toggleSub(s)" />
            <span :class="{ done: s.done }">{{ s.title }}</span>
          </label>
          <button class="ghost sub-del" @click="removeSub(s)">
            <ArtIcon name="close" tone="pearl" :size="16" label="删除子任务" />
          </button>
        </div>
        <div class="sub-add">
          <input v-model="newSub" placeholder="添加子任务，回车确认" @keydown.enter.prevent="addSub" />
          <button type="button" @click="addSub">
            <ArtIcon name="plus" tone="pearl" :size="18" />
            <span>添加</span>
          </button>
        </div>
      </section>

      <button v-if="task" class="danger icon-text-btn" @click="emit('delete', task)">
        <ArtIcon name="trash" tone="pearl" :size="18" />
        <span>删除任务</span>
      </button>
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
  color: var(--text);
}

.close-btn {
  padding: 7px 12px;
  display: flex;
  align-items: center;
  gap: 5px;
  justify-content: center;
  border-radius: var(--radius-sm);
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

.file-art {
  flex-shrink: 0;
}

.file-art.compact {
  margin-right: 2px;
}

.icon-text-btn,
.attach-row button,
.sub-add button {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.file-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-copy {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.file-subtitle {
  color: var(--text-soft);
  font-size: 12px;
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

.subtasks-section {
  margin-top: 2px;
  padding-top: 18px;
  border-top: 1px solid var(--border);
}

.subtasks-section h3 {
  margin: 0 0 12px;
  font-size: 15px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
}

.hint {
  font-size: 12px;
  font-weight: 400;
}

.sub-progress {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding: 9px 12px;
  border-radius: var(--radius-xs);
  background: linear-gradient(135deg, var(--accent-soft), var(--surface-2));
  border: 1px solid var(--border);
  box-shadow: var(--shadow-inset);
}

.sub-progress-text {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-soft);
  white-space: nowrap;
}

.sub-progress-bar {
  flex: 1;
  height: 7px;
  border-radius: var(--radius-pill);
  background: var(--surface-3);
  overflow: hidden;
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.06);
}

.sub-progress-fill {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--sea-300));
  border-radius: var(--radius-pill);
  transition: width 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.subtask-row.done {
  background: rgba(116, 230, 156, 0.08);
  border-color: rgba(116, 230, 156, 0.22);
}

.subtask-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  border: 1px solid transparent;
  box-shadow: var(--shadow-inset);
  margin-bottom: 6px;
  transition: border-color 0.2s ease, transform 0.2s ease;
}

.subtask-row:hover {
  border-color: var(--border);
  transform: translateX(4px);
}

.sub-check {
  display: flex;
  align-items: center;
  gap: 9px;
  cursor: pointer;
  font-size: 14px;
  min-width: 0;
}

.sub-check input {
  width: 16px;
  height: 16px;
  accent-color: var(--accent);
  flex-shrink: 0;
}

.sub-check .done {
  text-decoration: line-through;
  color: var(--text-soft);
}

.sub-del {
  padding: 3px 9px;
  font-size: 12px;
  flex-shrink: 0;
}

.sub-add {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  margin-top: 10px;
}

@media (max-width: 520px) {
  .attach-row {
    grid-template-columns: 1fr;
  }
}
</style>
