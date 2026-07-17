<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import { listTrash, purgeTask, restoreTask } from '../api/tasks'
import { listTrashFiles, purgeFile, restoreFile } from '../api/files'
import ArtIcon from '../components/ArtIcon.vue'
import AppSpinner from '../components/ui/AppSpinner.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import PageHeader from '../components/ui/PageHeader.vue'

const emit = defineEmits(['changed'])
// 应用内确认对话框（App.vue provide）；提供降级以防组件树外调用
const confirmDialog = inject('confirm-dialog', (o) => Promise.resolve(window.confirm(o.message || '')))
// 全局操作反馈 toast（App.vue provide）
const toast = inject('toast', { success: () => {}, error: () => {}, info: () => {}, undo: () => {} })

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
  try {
    await restoreTask(t.id)
    tasks.value = tasks.value.filter((x) => x.id !== t.id)
    emit('changed')
    toast.success(`已恢复「${t.title}」`)
  } catch {
    toast.error('恢复失败，请重试')
  }
}
async function purgeTaskItem(t) {
  const ok = await confirmDialog({
    title: '彻底删除任务',
    message: `「${t.title}」将被永久删除，此操作不可恢复。`,
    confirmText: '彻底删除',
    danger: true,
  })
  if (!ok) return
  try {
    await purgeTask(t.id)
    tasks.value = tasks.value.filter((x) => x.id !== t.id)
    toast.success('已彻底删除')
  } catch {
    toast.error('删除失败，请重试')
  }
}
async function restoreFileItem(f) {
  try {
    await restoreFile(f.id)
    files.value = files.value.filter((x) => x.id !== f.id)
    emit('changed')
    toast.success(`已恢复「${f.original_name}」`)
  } catch {
    toast.error('恢复失败，请重试')
  }
}
async function purgeFileItem(f) {
  const ok = await confirmDialog({
    title: '彻底删除文件',
    message: `「${f.original_name}」及其磁盘文件将被永久删除，不可恢复。`,
    confirmText: '彻底删除',
    danger: true,
  })
  if (!ok) return
  try {
    await purgeFile(f.id)
    files.value = files.value.filter((x) => x.id !== f.id)
    toast.success('已彻底删除')
  } catch {
    toast.error('删除失败，请重试')
  }
}

onMounted(load)
</script>

<template>
  <div class="trash workspace-page">
    <PageHeader
      class="animate-in"
      icon="trash"
      title="回收站"
      subtitle="误删的东西在这里暂存 30 天，可随时恢复或彻底清除。"
    />

    <div v-if="error" class="card error animate-in">{{ error }}</div>
    <div v-if="loading" class="center">
      <AppSpinner size="lg" label="加载中…" />
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

    <EmptyState
      v-if="!loading && !tasks.length && !files.length"
      class="animate-in"
      icon="trash"
      title="回收站为空"
      hint="删除的任务和文件会显示在这里。"
    />
  </div>
</template>

<style scoped>
.trash {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: none;
  margin: 0 auto;
}

/* PageHeader 自带 margin-bottom，与页面 flex 间距叠加拿掉 */
.trash :deep(.page-header) {
  margin-bottom: 0;
}

.trash-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.group {
  padding: 20px 24px;
}

.group h3 {
  margin: 0 0 16px;
  font-size: 15px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text);
}

.count-pill {
  margin-left: 4px;
  padding: 2px 12px;
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
  gap: 12px;
  padding: 12px 16px;
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
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text);
}

.row-time {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-muted);
  width: fit-content;
  padding: 2px 8px;
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
  gap: 4px;
}

.restore-btn {
  padding: 8px 16px;
  font-size: 13px;
}

.purge-btn {
  padding: 8px 16px;
  font-size: 13px;
  color: var(--pri-high);
}

.purge-btn:hover {
  background: color-mix(in srgb, var(--danger) 12%, transparent);
  color: var(--pri-high);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--danger) 20%, transparent), var(--shadow-inset);
}

.center {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
}

.error {
  color: var(--danger);
  background: color-mix(in srgb, var(--danger) 8%, transparent);
  padding: 12px 16px;
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
    margin-left: 54px;
  }
}
</style>
