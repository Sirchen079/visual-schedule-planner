<script setup>
import { computed, inject, onMounted, ref, watch } from 'vue'
import TaskForm from './TaskForm.vue'
import ArtIcon from './ArtIcon.vue'
import BaseModal from './ui/BaseModal.vue'
import { attachFile, detachFile, getContentUrl, listFiles } from '../api/files'
import { createSubtask, deleteSubtask, updateSubtask } from '../api/tasks'
import { startTimer } from '../api/timer'
import { breakdownSubtasks, scheduleTaskAi } from '../api/ai'
import { getSettings } from '../api/settings'

const props = defineProps({
  open: { type: Boolean, default: false },
  task: { type: Object, default: null },
  // 新建时的预填数据（如日历双击格子传入 { due_date }），透传给 TaskForm
  initial: { type: Object, default: null },
})
const emit = defineEmits(['save', 'delete', 'close', 'changed'])

// 全局 toast（App.vue provide）；提供降级以防组件树外调用
const toast = inject('toast', { success: () => {}, error: () => {}, info: () => {}, undo: () => {} })

// ---- 内嵌 AI 动作（功能面板「内嵌 AI 动作」开关控制渲染；无启用模型配置时禁用）----
const aiAvailable = inject('ai-available', ref(false))
const inlineAiEnabled = ref(false)
const aiBusy = ref(false)

onMounted(async () => {
  try {
    const s = await getSettings()
    inlineAiEnabled.value = s.feature_inline_ai_enabled !== 'false'
  } catch {
    // 读取失败按关闭处理，不展示按钮
  }
})

const aiDisabledTitle = '需先在助手中启用模型配置'
// 已有子任务时不可再拆解（后端 409 口径），用禁用态提前说明
const breakdownDisabled = computed(
  () => !aiAvailable.value || aiBusy.value || subtasks.value.length > 0
)
const breakdownTitle = computed(() => {
  if (!aiAvailable.value) return aiDisabledTitle
  if (subtasks.value.length > 0) return '已有子任务，如需重新拆解请先清空'
  return '让 AI 把任务拆成可执行的小步骤'
})
const scheduleDisabled = computed(() => !aiAvailable.value || aiBusy.value)
const scheduleTitle = computed(() =>
  aiAvailable.value ? '让 AI 挑一个合适的日子排进日程' : aiDisabledTitle
)

async function aiBreakdown() {
  const t = props.task
  if (!t || breakdownDisabled.value) return
  aiBusy.value = true
  try {
    const res = await breakdownSubtasks(t.id)
    const created = res?.subtasks || []
    subtasks.value = [...subtasks.value, ...created]
    toast.success(`已拆成 ${created.length} 个子任务`)
    emit('changed')
  } catch (e) {
    toast.error(`AI 拆解失败：${e.message}`)
  } finally {
    aiBusy.value = false
  }
}

async function aiSchedule() {
  const t = props.task
  if (!t || scheduleDisabled.value) return
  aiBusy.value = true
  try {
    const res = await scheduleTaskAi(t.id)
    toast.success(`已安排到 ${scheduleDateLabel(res?.date)}`)
    emit('changed')
    window.dispatchEvent(new Event('tasks:refresh'))
  } catch (e) {
    toast.error(`AI 排程失败：${e.message}`)
  } finally {
    aiBusy.value = false
  }
}

function scheduleDateLabel(dateStr) {
  if (!dateStr) return '日程'
  const d = new Date(`${dateStr}T00:00:00`)
  return `${d.getMonth() + 1}月${d.getDate()}日`
}

// 开始专注：调计时接口并 toast，派 focus:start 事件让 FocusTimer 同步状态，随后关闭弹窗
async function startFocus() {
  const t = props.task
  if (!t) return
  try {
    await startTimer(t.id)
    toast.success(`已开始专注《${t.title}》`)
    window.dispatchEvent(new CustomEvent('focus:start', { detail: t }))
    emit('close')
  } catch (e) {
    toast.error(`开始专注失败：${e.message}`)
  }
}

const allFiles = ref([])
const selectedFileId = ref('')
const fileError = ref(null)

// 组件常驻挂载、由 open 控制显隐(保证开合动画完整);
// 每次打开时按当前 task 重置内部状态,避免串用上次的内容。
watch(
  () => props.open,
  async (isOpen) => {
    if (!isOpen) return
    subtasks.value = [...(props.task?.subtasks || [])]
    newSub.value = ''
    selectedFileId.value = ''
    fileError.value = null
    if (props.task) {
      try {
        allFiles.value = await listFiles()
      } catch (e) {
        fileError.value = e.message
      }
    }
  }
)

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
  <BaseModal :open="open" size="md" :label="task ? '编辑任务' : '新建任务'" @close="emit('close')">
    <div class="modal">
      <div class="modal-head">
        <div class="modal-title">{{ task ? '编辑任务' : '新建任务' }}</div>
      </div>

      <TaskForm :model-value="task" :initial="initial" @save="(p) => emit('save', p)" @cancel="emit('close')" />

      <section v-if="task" class="files-section">
        <h3>
          <ArtIcon name="library" tone="aqua" :size="24" tile label="关联资料" />
          <span>关联资料</span>
        </h3>
        <p v-if="fileError" class="muted error-text">{{ fileError }}</p>
        <div v-if="!task.files?.length" class="muted empty-text">还没有关联资料。</div>
        <TransitionGroup name="list" tag="div">
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
        </TransitionGroup>
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
        <TransitionGroup name="list" tag="div">
          <div class="subtask-row" :class="{ done: s.done }" v-for="s in subtasks" :key="s.id">
            <label class="sub-check">
              <input type="checkbox" :checked="s.done" @change="toggleSub(s)" />
              <span :class="{ done: s.done }">{{ s.title }}</span>
            </label>
            <button class="ghost sub-del" @click="removeSub(s)">
              <ArtIcon name="close" tone="pearl" :size="16" label="删除子任务" />
            </button>
          </div>
        </TransitionGroup>
        <div class="sub-add">
          <input v-model="newSub" placeholder="添加子任务，回车确认" @keydown.enter.prevent="addSub" />
          <button type="button" @click="addSub">
            <ArtIcon name="plus" tone="pearl" :size="18" />
            <span>添加</span>
          </button>
        </div>
      </section>

      <div v-if="task" class="modal-foot">
        <div class="foot-left">
          <button type="button" class="ghost icon-text-btn" @click="startFocus">
            <ArtIcon name="priority" tone="aqua" :size="18" />
            <span>开始专注</span>
          </button>
          <template v-if="inlineAiEnabled">
            <button
              type="button"
              class="ghost icon-text-btn"
              :disabled="breakdownDisabled"
              :title="breakdownTitle"
              @click="aiBreakdown"
            >
              <ArtIcon name="steps" tone="mint" :size="18" />
              <span>AI 拆解</span>
            </button>
            <button
              type="button"
              class="ghost icon-text-btn"
              :disabled="scheduleDisabled"
              :title="scheduleTitle"
              @click="aiSchedule"
            >
              <ArtIcon name="calendar" tone="aqua" :size="18" />
              <span>AI 排程</span>
            </button>
          </template>
        </div>
        <button class="danger icon-text-btn" @click="emit('delete', task)">
          <ArtIcon name="trash" tone="pearl" :size="18" />
          <span>删除任务</span>
        </button>
      </div>
    </div>
  </BaseModal>
</template>

<style scoped>
/* overlay / Esc / 焦点陷阱 / z-index 统一由 BaseModal 承担，
   这里只保留弹窗内部内容布局 */
.modal {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 22px;
}

.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 18px;
  font-weight: 800;
  flex-shrink: 0;
  gap: 12px;
  /* 避开 BaseModal 右上角关闭钮 */
  padding-right: 40px;
}

.modal-title {
  color: var(--text);
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

.modal-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 2px;
  flex-wrap: wrap;
}

.foot-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.danger {
  margin-top: 2px;
}

.modal-foot .danger {
  margin-top: 0;
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
  box-shadow: inset 0 1px 2px color-mix(in srgb, var(--overlay-bg) 20%, transparent);
}

.sub-progress-fill {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--sea-300));
  border-radius: var(--radius-pill);
  transition: width 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.subtask-row.done {
  background: color-mix(in srgb, var(--success) 8%, transparent);
  border-color: color-mix(in srgb, var(--success) 22%, transparent);
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
