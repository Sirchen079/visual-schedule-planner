<script setup>
import { computed, onMounted, ref } from 'vue'
import { deleteFile, getContentUrl, listFiles, uploadFile } from '../api/files'

const files = ref([])
const q = ref('')
const loading = ref(false)
const error = ref(null)
const preview = ref(null)
const input = ref(null)
const dragOver = ref(false)

const isImage = (file) => file.mime_type?.startsWith('image/')
const isPdf = (file) => file.mime_type === 'application/pdf'
const iconFor = (file) => {
  if (isImage(file)) return '🖼️'
  if (isPdf(file)) return '📄'
  if (file.mime_type?.includes('zip') || file.original_name.endsWith('.zip')) return '🗜️'
  return '📎'
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
  if (!confirm(`将「${file.original_name}」移入回收站？（可在回收站恢复）`)) return
  await deleteFile(file.id)
  await load()
}

function open(file) {
  if (isImage(file) || isPdf(file)) preview.value = file
  else window.open(getContentUrl(file.id), '_blank')
}

const emptyText = computed(() => (q.value ? '没有匹配的资料' : '还没有资料，拖文件进来试试'))

onMounted(load)
</script>

<template>
  <div class="library">
    <div class="library-head">
      <div>
        <h2 class="gradient-text">资料库</h2>
        <p class="muted">论文、课件、截图、数据文件都可以先放进海湾。</p>
      </div>
      <button class="upload-btn" @click="input?.click()">
        <span class="btn-icon">☁️</span>
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
      <div class="drop-icon float">{{ dragOver ? '🌊' : '☁️' }}</div>
      <div class="drop-title">拖拽文件到这里，或点击选择</div>
      <div class="muted">任何类型都可以；文件存到本机 data/files，不进数据库</div>
    </div>

    <div class="toolbar">
      <input v-model="q" placeholder="搜索文件名或备注…" @keyup.enter="load" />
      <button class="ghost" @click="load">搜索</button>
    </div>

    <div v-if="error" class="card error">{{ error }}</div>
    <div v-if="loading" class="loading-line muted">
      <span class="spinner"></span>
      <span>处理中…</span>
    </div>

    <div v-if="!loading && !files.length" class="card empty">
      <div class="empty-icon float-slow">🐚</div>
      <div>{{ emptyText }}</div>
    </div>

    <div class="grid" v-else>
      <div class="file-card card" v-for="file in files" :key="file.id">
        <div class="preview" @click="open(file)">
          <img v-if="isImage(file)" :src="getContentUrl(file.id)" alt="" />
          <iframe v-else-if="isPdf(file)" :src="getContentUrl(file.id)"></iframe>
          <div v-else class="file-icon">{{ iconFor(file) }}</div>
        </div>
        <div class="file-info">
          <div class="name" :title="file.original_name">{{ file.original_name }}</div>
          <div class="meta muted">{{ sizeText(file.size) }} · {{ file.mime_type }}</div>
        </div>
        <div class="actions">
          <button class="ghost" @click="open(file)">打开</button>
          <button class="ghost" @click="remove(file)">删除</button>
        </div>
      </div>
    </div>

    <div v-if="preview" class="overlay" @click.self="preview = null">
      <div class="preview-modal card">
        <div class="modal-head">
          <span class="preview-name" :title="preview.original_name">{{ preview.original_name }}</span>
          <button class="ghost" @click="preview = null">✕</button>
        </div>
        <img v-if="isImage(preview)" :src="getContentUrl(preview.id)" />
        <iframe v-else :src="getContentUrl(preview.id)"></iframe>
      </div>
    </div>
  </div>
</template>

<style scoped>
.library {
  display: flex;
  flex-direction: column;
  gap: 18px;
  max-width: 1200px;
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

.btn-icon {
  font-size: 16px;
  display: inline-block;
  transition: transform 0.4s ease;
}

.upload-btn:hover .btn-icon {
  transform: translateY(-2px);
}

.drop {
  text-align: center;
  border: 2px dashed var(--border);
  cursor: pointer;
  padding: 38px 28px;
  transition: transform 0.25s ease, border-color 0.25s ease, background 0.25s ease;
}

.drop:hover,
.drop.active {
  border-color: var(--accent);
  background: var(--accent-soft);
  transform: translateY(-3px);
}

.drop-icon {
  font-size: 44px;
  margin-bottom: 12px;
  transition: transform 0.3s ease;
}

.drop.active .drop-icon {
  transform: scale(1.2);
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
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
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

.file-icon {
  font-size: 44px;
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

.empty-icon {
  font-size: 42px;
  margin-bottom: 12px;
  opacity: 0.7;
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
}
</style>
