<script setup>
import { onMounted, onBeforeUnmount, provide, ref } from 'vue'
import { useTasks } from './composables/useTasks'
import { useReminders } from './composables/useReminders'
import { restoreTask } from './api/tasks'
import BoardView from './views/BoardView.vue'
import OverviewView from './views/OverviewView.vue'
import LibraryView from './views/LibraryView.vue'
import AssistantView from './views/AssistantView.vue'
import ReportView from './views/ReportView.vue'
import AssistantFloat from './views/AssistantFloat.vue'
import CalendarView from './views/CalendarView.vue'
import TimelineView from './views/TimelineView.vue'
import TrashView from './views/TrashView.vue'
import TaskModal from './components/TaskModal.vue'
import RemindersPanel from './components/RemindersPanel.vue'
import ArtIcon from './components/ArtIcon.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import StartupReminder from './components/StartupReminder.vue'
import BaseModal from './components/ui/BaseModal.vue'
import AppSpinner from './components/ui/AppSpinner.vue'

const { tasks, loading, error, load, add, update, remove } = useTasks()
const { upcoming, overdue, count, panelOpen, start: startReminders, refresh: refreshReminders } = useReminders()

// 独立提醒小窗：?view=reminder 时只渲染提醒组件（frameless 小窗专用）
// 悬浮窗：?view=assistant 时只渲染助手悬浮组件
// 开机自启主窗口：?autostart=1 时不挂载启动弹窗（提醒由独立小窗承载）
const urlParams = new URLSearchParams(location.search)
const isReminderWindow = urlParams.get('view') === 'reminder'
const isAssistantFloatWindow = urlParams.get('view') === 'assistant'
const isAutoStartHost = urlParams.get('autostart') === '1'

onMounted(() => {
  // 小窗/悬浮窗专用窗口：不加载主界面数据、不启动轮询/通知
  if (isReminderWindow || isAssistantFloatWindow) {
    // 悬浮窗是透明窗口，清除 body/html 背景渐变，避免方形底色从圆角/圆形外露出
    if (isAssistantFloatWindow) {
      document.documentElement.style.background = 'transparent'
      document.body.style.background = 'transparent'
    }
    return
  }
  load()
  // 主窗口：接收小窗「去处理」传来的 taskId，打开对应任务编辑
  window.electronAPI?.onFocusTask?.((taskId) => {
    const t = tasks.value.find((x) => x.id === taskId)
    if (t) openEdit(t)
  })
  // 关闭询问：主窗口 close 行为为「每次询问」时，主进程发 ask-close，弹框让用户选
  window.electronAPI?.onAskClose?.(() => {
    confirmDialog({
      title: '关闭知时',
      message: '退出知时会结束后台运行；最小化到托盘则保持后台运行。如需固定此行为，可在设置中调整。',
      confirmText: '退出知时',
      cancelText: '最小化到托盘',
      danger: true,
    }).then((ok) => {
      window.electronAPI?.answerClose?.(ok ? 'quit' : 'minimize')
    })
  })
  // 主窗口重新获得焦点时静默刷新任务，确保悬浮窗里 AI 建的任务同步到看板
  window.addEventListener('focus', onFocusReload)
  window.addEventListener('keydown', onGlobalKeydown)
  // 开机自启的主窗口：提醒已由独立小窗承载，跳过通知轮询避免重复弹窗
  if (isAutoStartHost) return
  if (window.Notification && Notification.permission === 'default') {
    Notification.requestPermission().catch(() => {})
  }
  startReminders()
})

function onFocusReload() {
  load(true)
}
onBeforeUnmount(() => {
  window.removeEventListener('focus', onFocusReload)
  window.removeEventListener('keydown', onGlobalKeydown)
})

const view = ref('board')
const tabs = [
  { key: 'board', label: '看板', icon: 'board' },
  { key: 'overview', label: '总览', icon: 'overview' },
  { key: 'calendar', label: '日历', icon: 'calendar' },
  { key: 'timeline', label: '时间轴', icon: 'timeline' },
  { key: 'library', label: '资料库', icon: 'library' },
  { key: 'report', label: '日报周报', icon: 'archive' },
  { key: 'trash', label: '回收站', icon: 'trash' },
]

// 主题：有手动选择用手动选择；首次启动跟随系统 prefers-color-scheme
const storedTheme = localStorage.getItem('theme')
const theme = ref(
  storedTheme ||
    (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
)
const shuttingDown = ref(false)
const settingsOpen = ref(false)

// 应用内确认对话框（替代原生 confirm）：由 App 顶层 provide，任意后代 inject 调用，
// 返回 Promise<boolean>。支持 danger 样式与 Enter/Esc 键盘操作。
const confirmState = ref({
  open: false,
  title: '请确认',
  message: '',
  confirmText: '确定',
  cancelText: '取消',
  danger: false,
})
let confirmResolver = null
function confirmDialog(options) {
  return new Promise((resolve) => {
    confirmResolver = resolve
    confirmState.value = {
      open: true,
      title: '请确认',
      message: '',
      confirmText: '确定',
      cancelText: '取消',
      danger: false,
      ...options,
    }
  })
}
function resolveConfirmDialog(value) {
  confirmState.value.open = false
  if (confirmResolver) {
    confirmResolver(value)
    confirmResolver = null
  }
}
provide('confirm-dialog', confirmDialog)

function applyTheme() {
  document.documentElement.setAttribute('data-theme', theme.value)
  localStorage.setItem('theme', theme.value)
}
applyTheme()
function toggleTheme() {
  theme.value = theme.value === 'light' ? 'dark' : 'light'
  applyTheme()
}

const modalOpen = ref(false)
const editing = ref(null)
function openCreate() {
  editing.value = null
  modalOpen.value = true
}
function openEdit(t) {
  editing.value = t
  modalOpen.value = true
}
function closeModal() {
  modalOpen.value = false
  editing.value = null
}

async function onSave(payload) {
  if (editing.value) {
    await update(editing.value.id, payload)
  } else {
    await add(payload)
  }
  closeModal()
}
// 看板右侧栏快速新建：只带标题和目标列，其余走后端默认值
async function onQuickCreate({ title, status }) {
  await add({ title, status })
}
async function onDelete(t) {
  const ok = await confirmDialog({
    title: '移入回收站',
    message: `「${t.title}」将移入回收站，可在回收站恢复。`,
    confirmText: '移入回收站',
  })
  if (!ok) return
  await remove(t.id)
  closeModal()
  toastService.undo(`已将「${t.title}」移入回收站`, async () => {
    await restoreTask(t.id)
    await load()
  })
}
async function onStatusChange(task, status) {
  await update(task.id, { status })
}

async function shutdownService() {
  const isDesktop = !!window.electronAPI?.isDesktop
  const ok = await confirmDialog({
    title: isDesktop ? '关闭知时' : '关闭本地服务',
    message: isDesktop
      ? '将退出程序并保存当前数据；下次可从开始菜单或桌面快捷方式重新打开。'
      : '关闭后网页会停止响应；下次双击 start.bat 可重新启动。',
    confirmText: '关闭',
    danger: true,
  })
  if (!ok) return
  shuttingDown.value = true
  try {
    await fetch('/shutdown', { method: 'POST' })
  } catch {
    // 服务退出时连接可能被浏览器判定为中断，这是预期情况。
  }
}

// 全局操作反馈 toast:success / error / info / undo,自动消失。
// 由 App 顶层 provide,任意后代 inject('toast') 调用。
const toast = ref(null)
let toastTimer = null
function showToast(message, { type = 'info', undo = null, duration = 5000 } = {}) {
  toast.value = { message, type, undo }
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (toast.value = null), duration)
}
const toastService = {
  success: (msg, opts = {}) => showToast(msg, { ...opts, type: 'success' }),
  error: (msg, opts = {}) => showToast(msg, { ...opts, type: 'error', duration: 7000 }),
  info: (msg, opts = {}) => showToast(msg, { ...opts, type: 'info' }),
  undo: (msg, undoFn) => showToast(msg, { type: 'info', undo: undoFn, duration: 6000 }),
}
provide('toast', toastService)
const toastMeta = {
  success: { icon: 'check', tone: 'mint' },
  error: { icon: 'alert', tone: 'coral' },
  info: { icon: 'bell', tone: 'aqua' },
}
function dismissToast() {
  clearTimeout(toastTimer)
  toast.value = null
}
async function undoDelete() {
  if (!toast.value?.undo) return
  try {
    await toast.value.undo()
  } finally {
    dismissToast()
  }
}

// 全局快捷键:? 打开帮助;各视图自己的快捷键(如看板 / 与 N)在视图内注册
const shortcutsOpen = ref(false)
const shortcutGroups = [
  {
    name: '全局',
    items: [
      { keys: ['?'], desc: '打开快捷键帮助' },
      { keys: ['Esc'], desc: '关闭弹层' },
    ],
  },
  {
    name: '看板',
    items: [
      { keys: ['/'], desc: '聚焦搜索框' },
      { keys: ['N'], desc: '新建任务' },
    ],
  },
]
function onGlobalKeydown(e) {
  const tag = e.target?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target?.isContentEditable) return
  if (e.key === '?' || (e.shiftKey && e.key === '/')) {
    e.preventDefault()
    shortcutsOpen.value = !shortcutsOpen.value
  }
}
</script>

<template>
  <StartupReminder v-if="isReminderWindow" host-window />
  <AssistantFloat v-else-if="isAssistantFloatWindow" />
  <div v-else class="app">
    <header class="topbar">
      <div class="brand">
        <ArtIcon name="brand" tone="aqua" :size="38" tile label="知时" />
        <span class="brand-text">知时</span>
      </div>

      <nav class="tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          :class="['tab', view === tab.key && 'active']"
          :aria-label="tab.label"
          :title="tab.label"
          @click="view = tab.key"
        >
          <ArtIcon :name="tab.icon" :tone="view === tab.key ? 'aqua' : 'pearl'" :size="20" />
          <span class="tab-label">{{ tab.label }}</span>
        </button>
      </nav>

      <div class="topbar-actions">
        <button
          class="ghost icon bell-btn"
          :class="{ has: count > 0 }"
          :title="count > 0 ? `有 ${count} 条提醒` : '提醒'"
          @click="panelOpen = true; refreshReminders()"
        >
          <ArtIcon name="bell" tone="aqua" :size="20" label="提醒" />
          <span v-if="count" class="badge">{{ count > 99 ? '99+' : count }}</span>
        </button>
        <button
          class="ghost icon theme-btn"
          @click="toggleTheme"
          :title="theme === 'light' ? '切换深色' : '切换浅色'"
        >
          <ArtIcon
            :name="theme === 'light' ? 'moon' : 'sun'"
            tone="aqua"
            :size="20"
            :label="theme === 'light' ? '切换深色' : '切换浅色'"
          />
        </button>
        <button class="ghost settings" @click="settingsOpen = true" title="设置">
          <span>设置</span>
        </button>
        <button class="ghost shutdown" :disabled="shuttingDown" @click="shutdownService">
          <span>{{ shuttingDown ? '正在关闭…' : '关闭服务' }}</span>
        </button>
      </div>
    </header>

    <main class="content">
      <div v-if="loading" class="center muted">
        <AppSpinner size="lg" label="加载中" />
        <p>加载中…</p>
      </div>
      <div v-else-if="error" class="center">
        <p class="muted">请求未完成：{{ error }}</p>
        <button @click="load">重试</button>
      </div>
      <Transition name="fade" mode="out-in" v-else>
        <BoardView
          v-if="view === 'board'"
          :tasks="tasks"
          @open="openEdit"
          @create="openCreate"
          @update-status="onStatusChange"
          @quick-create="onQuickCreate"
        />
        <OverviewView v-else-if="view === 'overview'" :tasks="tasks" @open="openEdit" />
        <CalendarView v-else-if="view === 'calendar'" :tasks="tasks" @open="openEdit" @create="openCreate" />
        <TimelineView v-else-if="view === 'timeline'" :tasks="tasks" @open="openEdit" @create="openCreate" />
        <ReportView v-else-if="view === 'report'" @changed="load" />
        <TrashView v-else-if="view === 'trash'" @changed="load" />
        <LibraryView v-else />
      </Transition>
    </main>

    <AssistantView @changed="load" />

    <TaskModal
      :open="modalOpen"
      :task="editing"
      @save="onSave"
      @delete="onDelete"
      @changed="load"
      @close="closeModal"
    />

    <Transition name="pop">
      <RemindersPanel
        v-if="panelOpen"
        :upcoming="upcoming"
        :overdue="overdue"
        @open="(t) => { panelOpen = false; openEdit(t) }"
        @close="panelOpen = false"
      />
    </Transition>

    <SettingsPanel :open="settingsOpen" @close="settingsOpen = false" />

    <ConfirmDialog
      :open="confirmState.open"
      :title="confirmState.title"
      :message="confirmState.message"
      :confirm-text="confirmState.confirmText"
      :cancel-text="confirmState.cancelText"
      :danger="confirmState.danger"
      @confirm="resolveConfirmDialog(true)"
      @cancel="resolveConfirmDialog(false)"
    />

    <StartupReminder v-if="!isAutoStartHost" @open="openEdit" />

    <Transition name="toast">
      <div v-if="toast" :class="['toast', `toast-${toast.type}`]">
        <span class="toast-bar"></span>
        <ArtIcon
          class="toast-icon"
          :name="toastMeta[toast.type]?.icon || 'bell'"
          :tone="toastMeta[toast.type]?.tone || 'aqua'"
          :size="22"
          tile
          label="提示"
        />
        <span class="toast-msg">{{ toast.message }}</span>
        <button v-if="toast.undo" class="toast-undo" @click="undoDelete">撤销</button>
        <button class="ghost toast-close" @click="dismissToast">
          <ArtIcon name="close" tone="pearl" :size="16" label="关闭提示" />
        </button>
      </div>
    </Transition>

    <BaseModal :open="shortcutsOpen" size="sm" label="快捷键帮助" @close="shortcutsOpen = false">
      <div class="shortcuts-body">
        <h3>快捷键</h3>
        <div v-for="group in shortcutGroups" :key="group.name" class="shortcut-group">
          <p class="shortcut-group-name muted">{{ group.name }}</p>
          <div v-for="item in group.items" :key="item.desc" class="shortcut-row">
            <span class="shortcut-keys">
              <kbd v-for="k in item.keys" :key="k">{{ k }}</kbd>
            </span>
            <span class="shortcut-desc">{{ item.desc }}</span>
          </div>
        </div>
      </div>
    </BaseModal>
  </div>
</template>

<style scoped>
.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}

.topbar {
  position: relative;
  z-index: 50;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 18px;
  margin: 14px 22px 0;
  padding: 10px 12px 10px 14px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  box-shadow: var(--shadow-sm), var(--shadow-inset);
  flex-shrink: 0;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.brand-text {
  font-size: 16px;
  font-weight: 800;
  color: var(--text);
  letter-spacing: 0;
  white-space: nowrap;
}

.tabs {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
  min-width: 0;
  overflow-x: auto;
  background: var(--surface-2);
  padding: 4px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-inset);
  scrollbar-width: none;
}

.tabs::-webkit-scrollbar {
  display: none;
}

.tab {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  background: transparent;
  color: var(--text-soft);
  padding: 7px 14px;
  border-radius: var(--radius-sm);
  font-size: 14px;
  font-weight: 650;
  white-space: nowrap;
  box-shadow: none;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}

.tab.active {
  color: var(--accent-strong);
  background: var(--accent-soft);
  border-color: color-mix(in srgb, var(--accent) 22%, var(--border));
}

.tab:not(.active):hover {
  color: var(--text);
  background: var(--tab-hover);
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.theme-btn {
  padding: 0;
  width: 38px;
  min-width: 38px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
}

.bell-btn {
  position: relative;
  padding: 0;
  width: 38px;
  min-width: 38px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
}
.badge {
  position: absolute;
  top: -2px;
  right: -2px;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: var(--pri-high);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  line-height: 18px;
  text-align: center;
  box-shadow: 0 2px 6px color-mix(in srgb, var(--danger) 50%, transparent);
}
.shutdown {
  color: var(--text-soft);
  white-space: nowrap;
  font-weight: 500;
}

.settings {
  color: var(--text-soft);
  white-space: nowrap;
  font-weight: 500;
}

.content {
  flex: 1;
  padding: 16px clamp(16px, 2vw, 32px) 28px;
  overflow: auto;
  min-height: 0;
}

.center {
  text-align: center;
  padding: 80px 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

@media (max-width: 720px) {
  .topbar {
    margin: 10px 12px 0;
    padding: 8px 10px;
    gap: 10px;
    grid-template-columns: auto minmax(0, 1fr) auto;
  }
  .brand-text {
    display: none;
  }
  .tabs {
    flex: 1;
    justify-content: flex-start;
    max-width: none;
    gap: 4px;
  }
  .tab {
    width: 38px;
    min-width: 38px;
    height: 34px;
    justify-content: center;
    padding: 0;
    font-size: 13px;
  }
  .tab :deep(.art-icon) {
    width: 22px;
    height: 22px;
  }
  .tab :deep(.art-icon svg) {
    width: 82%;
    height: 82%;
  }
  .tab-label {
    display: none;
  }
  .shutdown span {
    display: none;
  }
  .shutdown::after {
    content: '关闭';
  }
  .content {
    padding: 16px 14px 112px;
  }
}

.toast {
  position: fixed;
  bottom: 28px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 200;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 16px 11px 12px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg), var(--shadow-inset);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  font-size: 14px;
  overflow: hidden;
}

.toast-bar {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 5px;
  background: linear-gradient(180deg, var(--sea-300), var(--accent));
}

.toast-success .toast-bar {
  background: linear-gradient(180deg, var(--foam-300), var(--success));
}

.toast-error .toast-bar {
  background: linear-gradient(180deg, var(--coral-300), var(--danger));
}

.toast-icon {
  flex-shrink: 0;
}

.toast-msg {
  color: var(--text);
}

.toast-undo {
  padding: 6px 16px;
  font-size: 13px;
}

.toast-close {
  width: 30px;
  height: 30px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.3s ease, transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translate(-50%, 20px) scale(0.95);
}

.shortcuts-body {
  padding: 26px 24px 20px;
}

.shortcuts-body h3 {
  margin: 0 0 14px;
  font-size: 17px;
  font-weight: 800;
  color: var(--text);
}

.shortcut-group + .shortcut-group {
  margin-top: 14px;
}

.shortcut-group-name {
  margin: 0 0 6px;
  font-weight: 700;
}

.shortcut-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 5px 0;
}

.shortcut-keys {
  min-width: 64px;
  display: inline-flex;
  gap: 4px;
}

.shortcut-keys kbd {
  padding: 3px 8px;
  border-radius: 6px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-bottom-width: 2px;
  font-family: inherit;
  font-size: 12px;
  font-weight: 700;
  color: var(--text);
}

.shortcut-desc {
  font-size: 13px;
  color: var(--text-soft);
}
</style>
