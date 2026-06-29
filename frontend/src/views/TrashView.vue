<script setup>
import { computed, onMounted, ref } from 'vue'
import { listTrash, purgeTask, restoreTask } from '../api/tasks'
import { listTrashFiles, purgeFile, restoreFile } from '../api/files'
import ArtIcon from '../components/ArtIcon.vue'

const emit = defineEmits(['changed'])

const tasks = ref([])
const files = ref([])
const loading = ref(false)
const error = ref(null)
const deletedTotal = computed(() => tasks.value.length + files.value.length)

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
  <div class="trash workspace-page">
    <div class="trash-head animate-in">
      <h2 class="page-title">
        <ArtIcon name="trash" tone="coral" :size="44" tile label="回收站" />
        <span>回收站</span>
      </h2>
      <p class="muted">误删的东西在这里暂存 30 天，可随时恢复或彻底清除。</p>
    </div>

    <div v-if="error" class="card error animate-in">{{ error }}</div>
    <div v-if="loading" class="center muted">
      <span class="spinner"></span>
      <p>加载中…</p>
    </div>

    <div v-if="!loading" class="trash-metrics">
      <article class="metric-tile">
        <ArtIcon name="trash" tone="coral" :size="34" tile label="删除项" />
        <div>
          <strong>{{ deletedTotal }}</strong>
          <span>删除项</span>
        </div>
      </article>
      <article class="metric-tile">
        <ArtIcon name="task" tone="aqua" :size="34" tile label="任务" />
        <div>
          <strong>{{ tasks.length }}</strong>
          <span>任务</span>
        </div>
      </article>
      <article class="metric-tile">
        <ArtIcon name="file" tone="sand" :size="34" tile label="文件" />
        <div>
          <strong>{{ files.length }}</strong>
          <span>文件</span>
        </div>
      </article>
    </div>

    <section
      v-if="!loading && tasks.length"
      class="card group animate-in"
      style="animation-delay: 0.05s"
    >
      <h3>
        <ArtIcon name="task" tone="aqua" :size="24" tile label="任务" />
        <span>任务</span>
        <span class="count-pill">{{ tasks.length }}</span>
      </h3>
      <div class="row" v-for="t in tasks" :key="t.id">
        <ArtIcon class="row-art" name="task" tone="aqua" :size="42" tile label="任务" />
        <div class="row-main">
          <span class="row-title">{{ t.title }}</span>
          <span class="row-time">删除于 {{ timeText(t.deleted_at) }}</span>
        </div>
        <div class="row-actions">
          <button class="restore-btn" @click="restoreTaskItem(t)">
            <ArtIcon name="restore" tone="mint" :size="18" />
            <span>恢复</span>
          </button>
          <button class="ghost purge-btn" @click="purgeTaskItem(t)">
            <ArtIcon name="trash" tone="coral" :size="18" />
            <span>彻底删除</span>
          </button>
        </div>
      </div>
    </section>

    <section
      v-if="!loading && files.length"
      class="card group animate-in"
      style="animation-delay: 0.1s"
    >
      <h3>
        <ArtIcon name="file" tone="sand" :size="24" tile label="文件" />
        <span>文件</span>
        <span class="count-pill">{{ files.length }}</span>
      </h3>
      <div class="row" v-for="f in files" :key="f.id">
        <ArtIcon class="row-art" name="file" tone="sand" :size="42" tile label="文件" />
        <div class="row-main">
          <span class="row-title">{{ f.original_name }}</span>
          <span class="row-time">删除于 {{ timeText(f.deleted_at) }}</span>
        </div>
        <div class="row-actions">
          <button class="restore-btn" @click="restoreFileItem(f)">
            <ArtIcon name="restore" tone="mint" :size="18" />
            <span>恢复</span>
          </button>
          <button class="ghost purge-btn" @click="purgeFileItem(f)">
            <ArtIcon name="trash" tone="coral" :size="18" />
            <span>彻底删除</span>
          </button>
        </div>
      </div>
    </section>

    <div v-if="!loading && !tasks.length && !files.length" class="card empty animate-in">
      <div class="empty-title">回收站为空</div>
      <div class="muted">删除的任务和文件会显示在这里。</div>
    </div>
  </div>
</template>

<style scoped>
.trash {
  display: flex;
  flex-direction: column;
  gap: 18px;
  max-width: none;
  margin: 0 auto;
}

.trash-head {
  position: relative;
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

.trash-head p {
  margin: 6px 0 0;
  font-size: 14px;
}

.trash-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
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

.row-art {
  flex-shrink: 0;
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

.row-actions button {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.restore-btn {
  padding: 7px 15px;
  font-size: 13px;
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
  .trash-metrics {
    grid-template-columns: 1fr;
  }
  .row {
    flex-wrap: wrap;
  }
  .row-actions {
    width: 100%;
    margin-left: 51px;
  }
}
</style>
