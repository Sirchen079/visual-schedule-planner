<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import { deleteFile, getContentUrl, listFiles, uploadFile } from '../api/files'
import ArtIcon from '../components/ArtIcon.vue'

// 应用内确认对话框（App.vue provide）；提供降级以防组件树外调用
const confirmDialog = inject('confirm-dialog', (o) => Promise.resolve(window.confirm(o.message || '')))

const files = ref([])
const q = ref('')
const loading = ref(false)
const error = ref(null)
const preview = ref(null)
const input = ref(null)
const dragOver = ref(false)
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

async function uploadMany(fileList) {
  const list = Array.from(fileList || [])
  if (!list.length) return
  loading.value = true
  try {
    for (const file of list) await uploadFile(file)
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
    dragOver.value = false
  }
}

async function remove(file) {
  const ok = await confirmDialog({
    title: '移入回收站',
    message: `「${file.original_name}」将移入回收站，可在回收站恢复。`,
    confirmText: '移入回收站',
  })
  if (!ok) return
  await deleteFile(file.id)
  await load()
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

const emptyText = computed(() => (q.value ? '没有匹配的资料' : '还没有资料，拖文件进来试试'))
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
  <div class="library workspace-page">
    <div class="library-head">
      <div>
        <h2 class="page-title">
        <ArtIcon name="library" tone="aqua" :size="44" tile label="资料库" />
        <span>资料库</span>
      </h2>
        <p class="muted">集中管理论文、课件、截图、链接和任务资料。</p>
      </div>
      <button class="upload-btn" @click="input?.click()">
        <ArtIcon name="upload" tone="on-accent" :size="20" />
        <span>上传资料</span>
      </button>
      <input ref="input" type="file" multiple hidden @change="uploadMany($event.target.files)" />
    </div>

    <div
      class="drop card"
      :class="{ active: dragOver }"
      @dragover.prevent="dragOver = true"
      @dragleave.prevent="dragOver = false"
      @drop.prevent="uploadMany($event.dataTransfer.files)"
      @click="input?.click()"
    >
      <div class="drop-title">{{ dragOver ? '松开以上传文件' : '拖拽文件到这里，或点击选择' }}</div>
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
    <div v-if="loading" class="loading-line muted">
      <span class="spinner"></span>
      <span>处理中…</span>
    </div>

    <div v-if="!loading && !files.length" class="card empty">
      <div>{{ emptyText }}</div>
    </div>

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

    <Transition name="pop">
      <div v-if="preview" class="overlay" @click.self="preview = null">
        <div class="preview-modal card">
          <div class="modal-head">
            <span class="preview-name" :title="preview.original_name">{{ preview.original_name }}</span>
            <button class="ghost" @click="preview = null">关闭</button>
          </div>
          <img v-if="isImage(preview)" :src="getContentUrl(preview.id)" />
          <iframe v-else :src="getContentUrl(preview.id)"></iframe>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.library {
  display: flex;
  flex-direction: column;
  gap: 18px;
  max-width: none;
  margin: 0 auto;
}

.library-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

h2 {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: 0.5px;
  white-space: nowrap;
}

p {
  margin: 6px 0 0;
  font-size: 14px;
}

.upload-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 11px 22px;
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
  padding: 22px 28px;
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
  margin-bottom: 5px;
}

.toolbar {
  display: flex;
  gap: 10px;
}

.search-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.toolbar input {
  max-width: 340px;
}

.loading-line {
  display: flex;
  align-items: center;
  gap: 10px;
}

.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid var(--surface-2);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
  gap: 18px;
}

.file-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 13px;
  transition: transform 0.25s ease, box-shadow 0.25s ease;
}

.file-card:hover {
  transform: translateY(-5px);
  box-shadow: var(--shadow-md), var(--shadow-inset);
}

.preview {
  height: 145px;
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
  gap: 6px;
  margin-top: auto;
}

.actions button {
  padding: 6px 12px;
  font-size: 13px;
}

.empty,
.error {
  text-align: center;
  padding: 40px;
}

.error {
  color: var(--pri-high);
  background: rgba(242, 107, 122, 0.08);
}

.overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: rgba(8, 47, 73, 0.32);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.preview-modal {
  width: min(900px, 92vw);
  height: min(720px, 88vh);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-weight: 700;
  flex-shrink: 0;
  gap: 12px;
}

.preview-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.preview-modal img,
.preview-modal iframe {
  flex: 1;
  width: 100%;
  min-height: 0;
  object-fit: contain;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--surface-2);
}

@media (max-width: 640px) {
  .library-head {
    align-items: center;
  }
  .library-head p {
    display: none;
  }
  .toolbar input {
    max-width: none;
  }
  .library-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
