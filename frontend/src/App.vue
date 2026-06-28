<script setup>
import { onMounted, ref } from 'vue'
import { useTasks } from './composables/useTasks'
import { useReminders } from './composables/useReminders'
import { restoreTask } from './api/tasks'
import BoardView from './views/BoardView.vue'
import OverviewView from './views/OverviewView.vue'
import LibraryView from './views/LibraryView.vue'
import AssistantView from './views/AssistantView.vue'
import CalendarView from './views/CalendarView.vue'
import TimelineView from './views/TimelineView.vue'
import TrashView from './views/TrashView.vue'
import TaskModal from './components/TaskModal.vue'
import RemindersPanel from './components/RemindersPanel.vue'
import ArtIcon from './components/ArtIcon.vue'

const { tasks, loading, error, load, add, update, remove } = useTasks()
const { upcoming, overdue, count, panelOpen, start: startReminders, refresh: refreshReminders } = useReminders()
onMounted(() => {
  load()
  // 请求通知权限并启动运行时轮询提醒（仅程序运行时生效）
  if (window.Notification && Notification.permission === 'default') {
    Notification.requestPermission().catch(() => {})
  }
  startReminders()
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
  if (!confirm(`将「${t.title}」移入回收站？（可在回收站恢复）`)) return
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
  if (!confirm('确定关闭本地服务吗？关闭后网页会停止响应；下次双击 start.bat 可重新启动。')) return
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
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <ArtIcon name="brand" tone="aqua" :size="38" tile label="可视化日程" />
        <span class="brand-text">可视化日程</span>
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

    <TaskModal
      v-if="modalOpen"
      :task="editing"
      @save="onSave"
      @delete="onDelete"
      @changed="load"
      @close="closeModal"
    />

    <RemindersPanel
      v-if="panelOpen"
      :upcoming="upcoming"
      :overdue="overdue"
      @open="(t) => { panelOpen = false; openEdit(t) }"
      @close="panelOpen = false"
    />

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

.content {
  flex: 1;
  padding: 22px 28px 32px;
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
