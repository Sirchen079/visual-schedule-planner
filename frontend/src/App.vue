<script setup>
import { onMounted, onBeforeUnmount, provide, ref } from 'vue'
import { useTasks } from './composables/useTasks'
import { useReminders } from './composables/useReminders'
import { restoreTask } from './api/tasks'
import BoardView from './views/BoardView.vue'
import OverviewView from './views/OverviewView.vue'
import LibraryView from './views/LibraryView.vue'
import AssistantView from './views/AssistantView.vue'
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
})

const view = ref('board')
const tabs = [
  { key: 'board', label: '看板', icon: 'board' },
  { key: 'overview', label: '总览', icon: 'overview' },
  { key: 'calendar', label: '日历', icon: 'calendar' },
  { key: 'timeline', label: '时间轴', icon: 'timeline' },
  { key: 'library', label: '资料库', icon: 'library' },
  { key: 'trash', label: '回收站', icon: 'trash' },
]

const theme = ref(localStorage.getItem('theme') || 'light')
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
async function onDelete(t) {
  const ok = await confirmDialog({
    title: '移入回收站',
    message: `「${t.title}」将移入回收站，可在回收站恢复。`,
    confirmText: '移入回收站',
  })
  if (!ok) return
  await remove(t.id)
  closeModal()
  showToast(`已将「${t.title}」移入回收站`, async () => {
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

// 删除后给一次"撤销恢复"的机会（软删可恢复）
const toast = ref(null)
let toastTimer = null
function showToast(message, undoFn) {
  toast.value = { message, undo: undoFn }
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (toast.value = null), 6000)
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
        <span class="spinner"></span>
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
        />
        <OverviewView v-else-if="view === 'overview'" :tasks="tasks" @open="openEdit" />
        <CalendarView v-else-if="view === 'calendar'" :tasks="tasks" @open="openEdit" @create="openCreate" />
        <TimelineView v-else-if="view === 'timeline'" :tasks="tasks" @open="openEdit" @create="openCreate" />
        <TrashView v-else-if="view === 'trash'" @changed="load" />
        <LibraryView v-else />
      </Transition>
    </main>

    <AssistantView @changed="load" />

    <Transition name="pop">
      <TaskModal
        v-if="modalOpen"
        :task="editing"
        @save="onSave"
        @delete="onDelete"
        @changed="load"
        @close="closeModal"
      />
    </Transition>

    <Transition name="pop">
      <RemindersPanel
        v-if="panelOpen"
        :upcoming="upcoming"
        :overdue="overdue"
        @open="(t) => { panelOpen = false; openEdit(t) }"
        @close="panelOpen = false"
      />
    </Transition>

    <Transition name="pop">
      <SettingsPanel v-if="settingsOpen" @close="settingsOpen = false" />
    </Transition>

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
      <div v-if="toast" class="toast">
        <span class="toast-bar"></span>
        <ArtIcon class="toast-icon" name="restore" tone="mint" :size="22" tile label="撤销" />
        <span class="toast-msg">{{ toast.message }}</span>
        <button class="toast-undo" @click="undoDelete">撤销</button>
        <button class="ghost toast-close" @click="dismissToast">
          <ArtIcon name="close" tone="pearl" :size="16" label="关闭提示" />
        </button>
      </div>
    </Transition>
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
  background: rgba(255, 255, 255, 0.4);
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
  box-shadow: 0 2px 6px rgba(242, 107, 122, 0.5);
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
  padding: 22px clamp(16px, 2vw, 32px) 32px;
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

.spinner {
  width: 36px;
  height: 36px;
  border: 3px solid var(--surface-2);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
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
  background: linear-gradient(180deg, var(--sea-300), var(--accent), var(--foam-400));
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
</style>
