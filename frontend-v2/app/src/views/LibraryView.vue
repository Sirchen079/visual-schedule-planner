<script setup lang="ts">
/**
 * 资料库视图（/library）：文件列表 + 搜索 + 上传 + 备注编辑 + 软删除，B×C 暗色。
 * - 数据：GET /api/files?q（后端过滤）；上传走 multipart（POST /api/files，notes 为 query 参数）
 * - 行内备注编辑（PATCH）；删除入回收站（乐观移除 + 失败回滚，约束①）；恢复/彻底删除在回收站页
 * - run done 后由壳层自动刷新（App.vue 接线，覆盖 AI bulk_delete_files/import_web_resources）
 */
import { onMounted, ref, watch } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import MaterialReader from '../components/MaterialReader.vue'
import MaterialSearch from '../components/MaterialSearch.vue'
import { materialTarget } from '../api/materials'
import DomainState from '../components/domain/DomainState.vue'
import { humanSize, parseStatusLabel, useLibraryStore } from '../stores/library'

const library = useLibraryStore()
const route = useRoute()
const selectedFile = computed(() => Number(route.query.file) > 0 ? Number(route.query.file) : undefined)
const selectedPart = computed(() => Math.max(1, Number(route.query.part) || 1))
const selectedRevision = computed(() => typeof route.query.revision === 'string' ? route.query.revision : undefined)
const search = ref(library.query)
/** 行内备注编辑态：fileId → 草稿 */
const editingNotes = ref<number | null>(null)
const notesDraft = ref('')

function startEdit(fileId: number, notes: string): void {
  editingNotes.value = fileId
  notesDraft.value = notes
}

async function saveNotes(fileId: number): Promise<void> {
  await library.saveNotes(fileId, notesDraft.value)
  editingNotes.value = null
}

/** 隐藏的文件选择器（样式自绘按钮触发） */
const fileInput = ref<HTMLInputElement | null>(null)
function pick(): void {
  fileInput.value?.click()
}

async function onPicked(ev: Event): Promise<void> {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) await library.upload(file)
  input.value = ''
}

watch(search, (q, prev) => {
  if (q !== prev && q !== library.query) void library.load(q)
})

function uploadedLabel(iso: string): string {
  return iso.slice(0, 10)
}

onMounted(() => {
  if (library.items === null) void library.load()
})
</script>

<template>
  <section class="lib-view">
    <Teleport defer to="#head-actions">
      <div class="search">
        <input
          v-model="search"
          class="search-in"
          placeholder="搜索资料名…"
          aria-label="搜索资料"
        />
      </div>
      <button class="new-btn" :disabled="library.uploading" @click="pick">
        <AppIcon name="plus" :size="14" />
        {{ library.uploading ? '上传中…' : '上传资料' }}
      </button>
      <input ref="fileInput" class="hidden-input" type="file" aria-label="选择要上传的文件" @change="onPicked" />
    </Teleport>

    <header class="lv-head">
      <span class="lv-caption">资料库</span>
      <span v-if="library.items" class="lv-count">{{ library.items.length }} 件<template v-if="library.query">（匹配「{{ library.query }}」）</template></span>
      <span v-if="library.lastRefreshedAt" class="lv-note">AI 写操作后自动刷新</span>
    </header>

    <MaterialSearch v-if="!selectedFile" @indexed="library.load(library.query)" />
    <MaterialReader v-if="selectedFile" :file-id="selectedFile" :part="selectedPart" :revision="selectedRevision" @indexed="library.load(library.query)" />

    <div v-if="library.actionError" class="action-error" role="alert">
      <AppIcon name="alert" :size="14" />
      <span>{{ library.actionError }}</span>
    </div>

    <DomainState
      :loading="library.loading && library.items === null"
      loading-text="正在清点资料…"
      :error="library.error"
      :empty="!library.loading && library.items !== null && library.items.length === 0"
      :empty-title="library.query ? '没有匹配的资料' : '资料库还空着'"
      @retry="library.load('')"
    >
      <template v-if="!library.query">
        对话里发过的附件、上传的文档都会归到这里。点右上「上传资料」，<br />或直接把文件拖进左侧对话，知时会上传并解析入库。
      </template>
      <template v-else>换个关键词试试，或清空搜索看全部。</template>
    </DomainState>

    <ul v-if="library.items && library.items.length > 0" class="rows">
      <li v-for="f in library.items" :key="f.id" class="row" :data-link="f.resource_type === 'link'">
        <div class="badge" :title="f.mime_type">{{ f.resource_type === 'link' ? '链' : '文' }}</div>

        <div class="row-main">
          <div class="row-title-line">
            <span class="row-name">{{ f.original_name }}</span>
            <span class="row-size">{{ f.resource_type === 'link' ? '网页链接' : humanSize(f.size) }}</span>
            <span class="row-parse" :data-s="f.parse_status">{{ parseStatusLabel(f.parse_status) }}</span>
          </div>

          <!-- 备注：点按进入行内编辑 -->
          <template v-if="editingNotes === f.id">
            <div class="notes-edit">
              <input
                v-model="notesDraft"
                class="notes-in"
                placeholder="备注（回车保存，Esc 取消）"
                aria-label="编辑备注"
                @keydown.enter.prevent="saveNotes(f.id)"
                @keydown.esc="editingNotes = null"
              />
              <button class="mini" @click="saveNotes(f.id)">保存</button>
            </div>
          </template>
          <button v-else class="notes" title="点击编辑备注" @click="startEdit(f.id, f.notes)">
            {{ f.notes || '加备注…' }}
          </button>
        </div>

        <RouterLink class="read-material" :to="materialTarget(f.id)">阅读 / 检索</RouterLink>
        <span class="row-date">{{ uploadedLabel(f.uploaded_at) }}</span>
        <button class="del" :aria-label="`删除 ${f.original_name}`" title="删除（入回收站）" @click="library.remove(f.id)">
          <AppIcon name="x" :size="13" />
        </button>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.read-material { color:var(--amber); font-size:12px; white-space:nowrap; }
.lib-view {
  flex: 1;
  min-height: 0;
  padding: 18px 22px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow: auto;
}

.search-in {
  font-family: var(--sans);
  font-size: 12.5px;
  color: var(--ink);
  background: var(--bg-sink);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-pill);
  padding: 5px 13px;
  width: 170px;
  box-shadow: var(--shadow-input);
}
.search-in::placeholder {
  color: var(--ink-faint);
}
.search-in:focus {
  outline: none;
  border-color: var(--line-hover);
}
.new-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--btn-new-text);
  background: var(--btn-new-bg);
  border-radius: var(--radius-pill);
  padding: 5px 13px;
}
.new-btn:hover {
  background: var(--btn-new-bg-hover);
}
.new-btn:disabled {
  background: var(--send-idle-bg);
  color: var(--send-idle-text);
  cursor: default;
}
.hidden-input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

.lv-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.lv-caption {
  font-family: var(--serif);
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--ink-2);
}
.lv-count {
  font-size: 12px;
  color: var(--ink-3);
}
.lv-note {
  margin-left: auto;
  font-size: 11.5px;
  color: var(--ink-3);
}

.action-error {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  color: var(--terra-soft);
  border: 1px dashed var(--terra-dashed);
  border-radius: var(--radius-s);
  padding: 8px 12px;
}

.rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.row {
  display: flex;
  align-items: center;
  gap: 13px;
  border: 1px solid var(--line);
  background: var(--bg-raise);
  border-radius: var(--radius-m);
  padding: 10px 14px;
}
.row:hover {
  border-color: var(--line-2);
}
.badge {
  flex: none;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--serif);
  font-size: 13px;
  font-weight: 600;
  color: var(--amber-soft);
  background: var(--amber-wash);
  border: 1px solid var(--amber-border-weak);
  border-radius: var(--radius-s);
}
.row-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.row-title-line {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}
.row-name {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.row-size {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-3);
  flex: none;
}
.row-parse {
  font-size: 10.5px;
  flex: none;
  color: var(--ink-3);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-pill);
  padding: 0 7px;
}
.row-parse[data-s='parsed'] {
  color: var(--ok);
  border-color: var(--line-hover);
}
.row-parse[data-s='failed'],
.row-parse[data-s='unsupported'] {
  color: var(--terra-soft);
  border-color: var(--terra-dashed);
}
.notes {
  align-self: flex-start;
  text-align: left;
  font-size: 11.5px;
  color: var(--ink-3);
  font-style: italic;
  padding: 0;
}
.notes:hover {
  color: var(--amber-soft);
}
.notes-edit {
  display: flex;
  gap: 6px;
}
.notes-in {
  flex: 1;
  max-width: 420px;
  font-size: 12px;
  color: var(--ink);
  background: var(--bg-sink);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-s);
  padding: 3px 9px;
}
.notes-in:focus {
  outline: none;
  border-color: var(--line-hover);
}
.mini {
  font-size: 11.5px;
  color: var(--ink-2);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-s);
  padding: 3px 9px;
}
.mini:hover {
  border-color: var(--line-hover);
  color: var(--amber-soft);
}
.row-date {
  flex: none;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-3);
}
.del {
  flex: none;
  color: var(--ink-3);
  border-radius: var(--radius-s);
  padding: 3px;
}
.del:hover {
  color: var(--terra-soft);
}
</style>
