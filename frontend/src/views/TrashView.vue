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
      <div class="head-wave"></div>
      <h2 class="gradient-text">
        <span class="head-icon float">🌊</span>回收站
      </h2>
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
      <h3><span class="section-icon">🗂️</span>任务<span class="count-pill">{{ tasks.length }}</span></h3>
      <div class="row" v-for="t in tasks" :key="t.id">
        <div class="row-icon" style="--ic: var(--cat-mentor)">🗂️</div>
        <div class="row-main">
          <span class="row-title">{{ t.title }}</span>
          <span class="row-time"><span>🗑️</span>{{ timeText(t.deleted_at) }}</span>
        </div>
        <div class="row-actions">
          <button class="restore-btn" @click="restoreTaskItem(t)"><span>↩</span>恢复</button>
          <button class="ghost purge-btn" @click="purgeTaskItem(t)">彻底删除</button>
        </div>
      </div>
    </section>

    <section
      v-if="!loading && files.length"
      class="card group animate-in"
      style="animation-delay: 0.1s"
    >
      <h3><span class="section-icon">📎</span>文件<span class="count-pill">{{ files.length }}</span></h3>
      <div class="row" v-for="f in files" :key="f.id">
        <div class="row-icon" style="--ic: var(--cat-misc)">📎</div>
        <div class="row-main">
          <span class="row-title">{{ f.original_name }}</span>
          <span class="row-time"><span>🗑️</span>{{ timeText(f.deleted_at) }}</span>
        </div>
        <div class="row-actions">
          <button class="restore-btn" @click="restoreFileItem(f)"><span>↩</span>恢复</button>
          <button class="ghost purge-btn" @click="purgeFileItem(f)">彻底删除</button>
        </div>
      </div>
    </section>

    <div v-if="!loading && !tasks.length && !files.length" class="card empty animate-in">
      <div class="empty-icon float-slow">🏖️</div>
      <div class="empty-title">回收站是空的</div>
      <div class="muted">海湾很干净，没有漂浮的杂物。</div>
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

.trash-head {
  position: relative;
  padding-top: 6px;
}

.head-wave {
  position: absolute;
  top: 0;
  left: 0;
  width: 64px;
  height: 5px;
  border-radius: var(--radius-pill);
  background: linear-gradient(90deg, var(--sea-300), var(--accent), var(--foam-400));
  opacity: 0.8;
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
  color: var(--text);
}

.section-icon {
  font-size: 18px;
}

.count-pill {
  margin-left: 2px;
  padding: 1px 10px;
  border-radius: var(--radius-pill);
  background: var(--accent-soft);
  color: var(--accent-hover);
  font-size: 12px;
  font-weight: 700;
  border: 1px solid var(--border);
  box-shadow: var(--shadow-inset);
}

.row {
  display: flex;
  align-items: center;
  gap: 13px;
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  margin-bottom: 9px;
  border: 1px solid transparent;
  box-shadow: var(--shadow-inset);
  transition: border-color 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;
}

.row:hover {
  border-color: var(--border);
  transform: translateX(6px);
  box-shadow: var(--shadow-sm), var(--shadow-inset);
}

.row-icon {
  width: 38px;
  height: 38px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  font-size: 18px;
  background: color-mix(in srgb, var(--ic, var(--accent)) 16%, transparent);
  border: 1px solid color-mix(in srgb, var(--ic, var(--accent)) 28%, transparent);
  box-shadow: var(--shadow-inset);
}

.row-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1;
}

.row-title {
  font-weight: 600;
  font-size: 14.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text);
}

.row-time {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11.5px;
  color: var(--text-muted);
  width: fit-content;
  padding: 1px 8px;
  border-radius: var(--radius-pill);
  background: var(--surface);
  border: 1px solid var(--border);
}

.row-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.restore-btn {
  padding: 7px 15px;
  font-size: 13px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.restore-btn span {
  font-size: 14px;
}

.purge-btn {
  padding: 7px 14px;
  font-size: 13px;
  color: var(--pri-high);
}

.purge-btn:hover {
  background: rgba(242, 107, 122, 0.12);
  color: var(--pri-high);
  box-shadow: 0 4px 12px rgba(242, 107, 122, 0.2), var(--shadow-inset);
}

.empty {
  text-align: center;
  padding: 56px 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.empty-icon {
  font-size: 46px;
  margin-bottom: 8px;
  opacity: 0.85;
}

.empty-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
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

@media (max-width: 600px) {
  .row {
    flex-wrap: wrap;
  }
  .row-actions {
    width: 100%;
    margin-left: 51px;
  }
}
</style>
