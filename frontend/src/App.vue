<script setup>
import { onMounted, ref } from 'vue'
import { useTasks } from './composables/useTasks'
import { useReminders } from './composables/useReminders'
import BoardView from './views/BoardView.vue'
import OverviewView from './views/OverviewView.vue'
import LibraryView from './views/LibraryView.vue'
import CalendarView from './views/CalendarView.vue'
import TaskModal from './components/TaskModal.vue'
import RemindersPanel from './components/RemindersPanel.vue'

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
  if (confirm(`删除「${t.title}」？`)) {
    await remove(t.id)
    closeModal()
  }
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
</script>

<template>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <span class="brand-icon float">🌊</span>
        <span class="brand-text gradient-text">可视化日程</span>
      </div>

      <nav class="tabs">
        <button
          v-for="tab in [
            { key: 'board', label: '看板' },
            { key: 'overview', label: '总览' },
            { key: 'calendar', label: '日历' },
            { key: 'library', label: '资料库' },
          ]"
          :key="tab.key"
          :class="['tab', view === tab.key && 'active']"
          @click="view = tab.key"
        >
          {{ tab.label }}
        </button>
      </nav>

      <div class="topbar-actions">
        <button
          class="ghost icon bell-btn"
          :class="{ has: count > 0 }"
          :title="count > 0 ? `有 ${count} 条提醒` : '提醒'"
          @click="panelOpen = true; refreshReminders()"
        >
          <span class="bell">🔔</span>
          <span v-if="count" class="badge">{{ count > 99 ? '99+' : count }}</span>
        </button>
        <button
          class="ghost icon theme-btn"
          @click="toggleTheme"
          :title="theme === 'light' ? '切换深色' : '切换浅色'"
        >
          <span class="theme-icon">{{ theme === 'light' ? '🌙' : '☀️' }}</span>
        </button>
        <button class="ghost shutdown" :disabled="shuttingDown" @click="shutdownService">
          {{ shuttingDown ? '正在关闭…' : '关闭服务' }}
        </button>
      </div>
    </header>

    <main class="content">
      <div v-if="loading" class="center muted">
        <span class="spinner"></span>
        <p>加载中…</p>
      </div>
      <div v-else-if="error" class="center">
        <p class="muted">⚠️ {{ error }}</p>
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
        <LibraryView v-else />
      </Transition>
    </main>

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
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin: 14px 24px 0;
  padding: 10px 14px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  box-shadow: var(--shadow-md), var(--shadow-inset);
  flex-shrink: 0;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-left: 6px;
}

.brand-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--accent-soft), var(--sea-100));
  font-size: 20px;
  box-shadow: 0 3px 12px var(--accent-glow), var(--shadow-inset);
}

.brand-text {
  font-size: 17px;
  font-weight: 800;
  letter-spacing: 0.8px;
}

.tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  background: var(--surface-2);
  padding: 4px;
  border-radius: var(--radius-pill);
  box-shadow: var(--shadow-inset);
}

.tab {
  position: relative;
  background: transparent;
  color: var(--text-soft);
  padding: 7px 20px;
  border-radius: var(--radius-pill);
  font-size: 14px;
  font-weight: 600;
  box-shadow: none;
  overflow: hidden;
  transition: color 0.25s ease;
}

.tab::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, var(--accent), var(--sea-400));
  border-radius: var(--radius-pill);
  opacity: 0;
  transform: scale(0.9);
  transition: opacity 0.3s ease, transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
  z-index: -1;
}

.tab.active {
  color: #fff;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
}

.tab.active::before {
  opacity: 1;
  transform: scale(1);
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
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
}

.bell-btn {
  position: relative;
  padding: 0;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
}
.bell {
  font-size: 17px;
  transition: transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.bell-btn:hover .bell {
  transform: rotate(12deg) scale(1.12);
}
.bell-btn.has .bell {
  animation: ring 1.6s ease-in-out infinite;
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
@keyframes ring {
  0%, 60%, 100% { transform: rotate(0); }
  70% { transform: rotate(-12deg); }
  80% { transform: rotate(10deg); }
  90% { transform: rotate(-6deg); }
}

.theme-icon {
  font-size: 17px;
  display: inline-block;
  transition: transform 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.theme-btn:hover .theme-icon {
  transform: rotate(25deg) scale(1.15);
}

.shutdown {
  color: var(--text-soft);
  white-space: nowrap;
  font-weight: 500;
}

.content {
  flex: 1;
  padding: 24px 28px 32px;
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
  }
  .brand-text {
    display: none;
  }
  .tabs {
    position: static;
    transform: none;
    flex: 1;
    justify-content: center;
  }
  .tab {
    padding: 6px 12px;
    font-size: 13px;
  }
  .shutdown span {
    display: none;
  }
  .shutdown::after {
    content: '关闭';
  }
  .content {
    padding: 16px 14px 24px;
  }
}
</style>
