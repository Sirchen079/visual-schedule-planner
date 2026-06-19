<script setup>
import { onMounted, ref } from 'vue'
import { listTrash, purgeTask, restoreTask } from '../api/tasks'
import { listTrashFiles, purgeFile, restoreFile } from '../api/files'

const emit = defineEmits(['changed'])

const tasks = ref([])
const files = ref([])
const loading = ref(false)
const error = ref(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    const [t, f] = await Promise.all([listTrash(), listTrashFiles()])
    tasks.value = t
    files.value = f
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function timeText(t) {
  if (!t) return ''
  return new Date(t).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function restoreTaskItem(t) {
  await restoreTask(t.id)
  tasks.value = tasks.value.filter((x) => x.id !== t.id)
  emit('changed')
}
async function purgeTaskItem(t) {
  if (!confirm(`彻底删除「${t.title}」？此操作不可恢复。`)) return
  await purgeTask(t.id)
  tasks.value = tasks.value.filter((x) => x.id !== t.id)
}
async function restoreFileItem(f) {
  await restoreFile(f.id)
  files.value = files.value.filter((x) => x.id !== f.id)
  emit('changed')
}
async function purgeFileItem(f) {
  if (!confirm(`彻底删除「${f.original_name}」？磁盘文件也会被删除，不可恢复。`)) return
  await purgeFile(f.id)
  files.value = files.value.filter((x) => x.id !== f.id)
}

onMounted(load)
</script>

<template>
  <div class="trash">
    <div class="trash-head animate-in">
      <h2 class="gradient-text"><span class="head-icon float">🌊</span>回收站</h2>
      <p class="muted">误删的东西在这里暂存 30 天，可随时恢复或彻底清除。</p>
    </div>

    <div v-if="error" class="card error animate-in">⚠️ {{ error }}</div>
    <div v-if="loading" class="center muted">
      <span class="spinner"></span>
      <p>加载中…</p>
    </div>

    <section
      v-if="!loading && tasks.length"
      class="card group animate-in"
      style="animation-delay: 0.05s"
    >
      <h3><span class="section-icon">🗂️</span>任务（{{ tasks.length }}）</h3>
      <div class="row" v-for="t in tasks" :key="t.id">
        <div class="row-main">
          <span class="row-title">{{ t.title }}</span>
          <span class="muted row-meta">删除于 {{ timeText(t.deleted_at) }}</span>
        </div>
        <div class="row-actions">
          <button class="ghost" @click="restoreTaskItem(t)">恢复</button>
          <button class="ghost danger-text" @click="purgeTaskItem(t)">彻底删除</button>
        </div>
      </div>
    </section>

    <section
      v-if="!loading && files.length"
      class="card group animate-in"
      style="animation-delay: 0.1s"
    >
      <h3><span class="section-icon">📎</span>文件（{{ files.length }}）</h3>
      <div class="row" v-for="f in files" :key="f.id">
        <div class="row-main">
          <span class="row-title">{{ f.original_name }}</span>
          <span class="muted row-meta">删除于 {{ timeText(f.deleted_at) }}</span>
        </div>
        <div class="row-actions">
          <button class="ghost" @click="restoreFileItem(f)">恢复</button>
          <button class="ghost danger-text" @click="purgeFileItem(f)">彻底删除</button>
        </div>
      </div>
    </section>

    <div v-if="!loading && !tasks.length && !files.length" class="card empty animate-in">
      <div class="empty-icon float-slow">🏖️</div>
      <div>回收站是空的，海湾很干净。</div>
    </div>
  </div>
</template>

<style scoped>
.trash {
  display: flex;
  flex-direction: column;
  gap: 18px;
  max-width: 860px;
  margin: 0 auto;
}

.trash-head h2 {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: 0.5px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.head-icon {
  font-size: 24px;
  filter: drop-shadow(0 2px 6px var(--accent-glow));
}

.trash-head p {
  margin: 6px 0 0;
  font-size: 14px;
}

.group {
  padding: 20px 22px;
}

.group h3 {
  margin: 0 0 14px;
  font-size: 15px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-icon {
  font-size: 18px;
}

.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  margin-bottom: 8px;
  border: 1px solid transparent;
  box-shadow: var(--shadow-inset);
  transition: border-color 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;
}

.row:hover {
  border-color: var(--border);
  transform: translateX(6px);
  box-shadow: var(--shadow-sm), var(--shadow-inset);
}

.row-main {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.row-title {
  font-weight: 600;
  font-size: 14.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-meta {
  font-size: 12px;
}

.row-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.row-actions button {
  padding: 6px 14px;
  font-size: 13px;
}

.danger-text {
  color: var(--pri-high);
}

.empty {
  text-align: center;
  padding: 50px 20px;
}

.empty-icon {
  font-size: 42px;
  margin-bottom: 12px;
  opacity: 0.8;
}

.center {
  text-align: center;
  padding: 60px 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}

.spinner {
  width: 30px;
  height: 30px;
  border: 3px solid var(--surface-2);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.error {
  color: var(--pri-high);
  background: rgba(242, 107, 122, 0.08);
  padding: 14px 18px;
}
</style>
