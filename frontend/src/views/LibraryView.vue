<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import { deleteFile, getContentUrl, listFiles, uploadFile } from '../api/files'
import ArtIcon from '../components/ArtIcon.vue'
import AppSpinner from '../components/ui/AppSpinner.vue'
import BaseModal from '../components/ui/BaseModal.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import PageHeader from '../components/ui/PageHeader.vue'

// 应用内确认对话框（App.vue provide）；提供降级以防组件树外调用
const confirmDialog = inject('confirm-dialog', (o) => Promise.resolve(window.confirm(o.message || '')))
// 全局操作反馈 toast（App.vue provide）
const toast = inject('toast', { success: () => {}, error: () => {}, info: () => {}, undo: () => {} })

const files = ref([])
const q = ref('')
const loading = ref(false)
const error = ref(null)
const preview = ref(null)
const input = ref(null)
const dragActive = ref(false)
const uploadProgress = ref(null) // { done, total }
const previewFailures = ref(new Set())

const isLink = (file) => Boolean(file.source_url)
const isImage = (file) => file.mime_type?.startsWith('image/')
const isPdf = (file) => file.mime_type === 'application/pdf'
const iconFor = (file) => {
  if (file.resource_type === 'video') return { name: 'file', labelText: 'VID', tone: 'sand' }
  if (isLink(file)) return { name: 'link', labelText: 'LINK', tone: 'aqua' }
  if (isImage(file)) return { name: 'image', labelText: 'IMG', tone: 'mint' }
  if (isPdf(file)) return { name: 'file', labelText: 'PDF', tone: 'coral' }
  if (file.mime_type?.includes('zip') || file.original_name.endsWith('.zip')) {
    return { name: 'archive', labelText: 'ZIP', tone: 'sand' }
  }
  return { name: 'file', labelText: 'FILE', tone: 'pearl' }
}
const resourceTypeText = (file) => {
  const map = {
    file: '文件',
    link: '链接',
    video: '视频',
    webpage: '网页',
    article: '文章',
    paper: '论文',
    course: '课程',
    pdf: 'PDF',
  }
  return map[file.resource_type] || file.resource_type || '资料'
}
const hostText = (url) => {
  try {
    return new URL(url).hostname
  } catch {
    return url
  }
}
const sizeText = (size) => {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

async function load() {
  loading.value = true
  error.value = null
  try {
    files.value = await listFiles(q.value)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// 多文件并行上传：实时进度 + 逐个汇报结果
async function uploadMany(fileList) {
  const list = Array.from(fileList || [])
  if (!list.length) return
  uploadProgress.value = { done: 0, total: list.length }
  const results = await Promise.allSettled(
    list.map((file) =>
      uploadFile(file).finally(() => {
        uploadProgress.value.done += 1
      })
    )
  )
  uploadProgress.value = null
  const succeeded = results.filter((r) => r.status === 'fulfilled').length
  if (succeeded) {
    toast.success(`已上传 ${succeeded} 个文件`)
    await load()
  }
  results.forEach((r, i) => {
    if (r.status === 'rejected') toast.error(`「${list[i].name}」上传失败`)
  })
}

async function remove(file) {
  const ok = await confirmDialog({
    title: '移入回收站',
    message: `「${file.original_name}」将移入回收站，可在回收站恢复。`,
    confirmText: '移入回收站',
  })
  if (!ok) return
  try {
    await deleteFile(file.id)
    toast.success('已移入回收站')
    await load()
  } catch {
    toast.error(`「${file.original_name}」删除失败`)
  }
}

function open(file) {
  if (isLink(file)) {
    window.open(file.source_url, '_blank', 'noopener,noreferrer')
    return
  }
  if (isImage(file) || isPdf(file)) preview.value = file
  else window.open(getContentUrl(file.id), '_blank')
}

function previewFailed(file) {
  return previewFailures.value.has(file.id)
}

function markPreviewFailed(file) {
  previewFailures.value = new Set([...previewFailures.value, file.id])
}

// 整页拖放：dragenter/dragleave 计数器，避免在子元素间移动时高亮闪烁
let dragDepth = 0
const hasFiles = (e) => Array.from(e.dataTransfer?.types || []).includes('Files')
function onDragEnter(e) {
  if (!hasFiles(e)) return
  dragDepth += 1
  dragActive.value = true
}
function onDragOver(e) {
  if (hasFiles(e)) e.preventDefault()
}
function onDragLeave(e) {
  if (!hasFiles(e)) return
  dragDepth = Math.max(dragDepth - 1, 0)
  if (!dragDepth) dragActive.value = false
}
function onDrop(e) {
  if (!hasFiles(e)) return
  e.preventDefault()
  dragDepth = 0
  dragActive.value = false
  uploadMany(e.dataTransfer.files)
}

const typeStats = computed(() => {
  const stats = [
    { key: 'pdf', label: 'PDF', icon: 'file', tone: 'coral', count: files.value.filter(isPdf).length },
    { key: 'image', label: '图片', icon: 'image', tone: 'mint', count: files.value.filter(isImage).length },
    { key: 'link', label: '链接', icon: 'link', tone: 'aqua', count: files.value.filter(isLink).length },
    { key: 'file', label: '其他', icon: 'archive', tone: 'sand', count: 0 },
  ]
  stats[3].count = Math.max(files.value.length - stats[0].count - stats[1].count - stats[2].count, 0)
  return stats
})

onMounted(load)
</script>

<template>
  <div
    class="library workspace-page"
    @dragenter="onDragEnter"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <PageHeader
      icon="library"
      title="资料库"
      subtitle="集中管理论文、课件、截图、链接和任务资料。"
    >
      <template #actions>
        <button class="upload-btn" @click="input?.click()">
          <ArtIcon name="upload" tone="on-accent" :size="20" />
          <span>上传资料</span>
        </button>
        <input ref="input" type="file" multiple hidden @change="uploadMany($event.target.files)" />
      </template>
    </PageHeader>

    <div class="drop card" :class="{ active: dragActive }" @click="input?.click()">
      <div class="drop-title">{{ dragActive ? '松开以上传文件' : '拖拽文件到这里，或点击选择' }}</div>
      <div class="muted">文件将保存到本机资料库，便于后续关联任务。</div>
    </div>

    <div class="library-metrics">
      <article v-for="item in typeStats" :key="item.key" class="metric-tile">
        <ArtIcon :name="item.icon" :tone="item.tone" :size="34" tile :label="item.label" />
        <div>
          <strong>{{ item.count }}</strong>
          <span>{{ item.label }}</span>
        </div>
      </article>
    </div>

    <div class="toolbar">
      <input v-model="q" placeholder="搜索文件名或备注…" @keyup.enter="load" />
      <button class="ghost search-btn" @click="load">
        <ArtIcon name="search" tone="aqua" :size="18" />
        <span>搜索</span>
      </button>
    </div>

    <div v-if="error" class="card error">{{ error }}</div>

    <div v-if="uploadProgress" class="status-line">
      <AppSpinner size="sm" :label="`正在上传 ${uploadProgress.done}/${uploadProgress.total}`" />
    </div>
    <div v-else-if="loading" class="status-line">
      <AppSpinner size="sm" label="加载中…" />
    </div>

    <EmptyState
      v-if="!loading && !files.length"
      icon="library"
      :title="q ? '没有匹配的资料' : '还没有资料'"
      :hint="q ? '换个关键词试试。' : '把文件拖进页面，或点击右上角上传按钮。'"
    />

    <div class="grid" v-else>
      <div class="file-card card" v-for="file in files" :key="file.id">
        <div class="preview" @click="open(file)">
          <img
            v-if="!isLink(file) && isImage(file) && !previewFailed(file)"
            :src="getContentUrl(file.id)"
            alt=""
            @error="markPreviewFailed(file)"
          />
          <ArtIcon
            v-else
            class="file-art"
            :name="iconFor(file).name"
            :tone="iconFor(file).tone"
            :label-text="iconFor(file).labelText"
            :label="iconFor(file).labelText + ' 文件'"
            :size="84"
            tile
          />
        </div>
        <div class="file-info">
          <div class="name" :title="file.original_name">{{ file.original_name }}</div>
          <div class="meta muted">
            <template v-if="isLink(file)">
              {{ resourceTypeText(file) }} · {{ hostText(file.source_url) }}
            </template>
            <template v-else>
              {{ sizeText(file.size) }} · {{ file.mime_type }}
            </template>
          </div>
        </div>
        <div class="actions">
          <button class="ghost" @click="open(file)">打开</button>
          <button class="ghost" @click="remove(file)">删除</button>
        </div>
      </div>
    </div>

    <BaseModal
      :open="!!preview"
      size="lg"
      :label="preview?.original_name || '预览'"
      @close="preview = null"
    >
      <div v-if="preview" class="preview-body">
        <div class="preview-name" :title="preview.original_name">{{ preview.original_name }}</div>
        <img v-if="isImage(preview)" :src="getContentUrl(preview.id)" :alt="preview.original_name" />
        <iframe v-else :src="getContentUrl(preview.id)" :title="preview.original_name"></iframe>
      </div>
    </BaseModal>

    <div v-if="dragActive" class="drag-mask">
      <ArtIcon name="upload" tone="aqua" :size="56" tile />
      <span class="drag-mask-text">松开以上传文件</span>
    </div>
  </div>
</template>

<style scoped>
.library {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: none;
  margin: 0 auto;
}

/* PageHeader 自带 margin-bottom，与页面 flex 间距叠加拿掉 */
.library :deep(.page-header) {
  margin-bottom: 0;
}

.upload-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 24px;
  border-radius: var(--radius-pill);
  font-size: 14px;
  font-weight: 600;
}

.upload-btn :deep(.art-icon) {
  transition: transform 0.2s ease;
}

.upload-btn:hover :deep(.art-icon) {
  transform: translateY(-2px);
}

.drop {
  text-align: center;
  border: 2px dashed var(--border);
  cursor: pointer;
  padding: 24px 28px;
  transition: transform 0.25s ease, border-color 0.25s ease, background 0.25s ease;
}

.library-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.drop:hover,
.drop.active {
  border-color: var(--accent);
  background: var(--accent-soft);
  transform: translateY(-3px);
}

.drop-title {
  font-weight: 600;
  font-size: 15px;
  margin-bottom: 4px;
}

.toolbar {
  display: flex;
  gap: 12px;
}

.search-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.toolbar input {
  max-width: 340px;
}

.status-line {
  display: flex;
  align-items: center;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
  gap: 16px;
}

.file-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  transition: transform 0.25s ease, box-shadow 0.25s ease;
}

.file-card:hover {
  transform: translateY(-5px);
  box-shadow: var(--shadow-md), var(--shadow-inset);
}

.preview {
  height: 144px;
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border: 1px solid var(--border);
  transition: transform 0.2s ease;
}

.file-card:hover .preview {
  transform: scale(1.02);
}

.preview img,
.preview iframe {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border: none;
}

.file-art {
  flex-shrink: 0;
}

.file-info {
  min-width: 0;
}

.name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
}

.meta {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: auto;
}

.actions button {
  padding: 4px 12px;
  font-size: 13px;
}

.error {
  text-align: center;
  padding: 16px 20px;
  color: var(--danger);
  background: color-mix(in srgb, var(--danger) 8%, transparent);
}

/* 预览弹层内容（外壳由 BaseModal 提供） */
.preview-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: min(76vh, 720px);
  padding: 20px;
}

.preview-name {
  font-weight: 700;
  padding-right: 44px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  flex-shrink: 0;
}

.preview-body img,
.preview-body iframe {
  flex: 1;
  width: 100%;
  min-height: 0;
  object-fit: contain;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--surface-2);
}

/* 整页拖放高亮遮罩（pointer-events 关闭，不拦截落下的文件） */
.drag-mask {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  border-radius: var(--radius-lg);
  border: 2px dashed var(--accent);
  background: color-mix(in srgb, var(--accent-soft) 82%, transparent);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  pointer-events: none;
}

.drag-mask-text {
  font-size: 15px;
  font-weight: 700;
  color: var(--accent-hover);
}

@media (max-width: 640px) {
  .toolbar input {
    max-width: none;
  }
  .library-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
