<script setup>
import { onMounted, ref } from 'vue'
import { useTasks } from './composables/useTasks'
import BoardView from './views/BoardView.vue'
import OverviewView from './views/OverviewView.vue'
import LibraryView from './views/LibraryView.vue'
import TaskModal from './components/TaskModal.vue'

const { tasks, loading, error, load, add, update, remove } = useTasks()
onMounted(load)

const view = ref('board') // board | overview | library

const theme = ref(localStorage.getItem('theme') || 'light')
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
</script>

<template>
  <div class="app">
    <header class="topbar">
      <div class="brand">📋 可视化日程</div>
      <nav class="tabs">
        <button :class="['tab', view === 'board' && 'active']" @click="view = 'board'">看板</button>
        <button :class="['tab', view === 'overview' && 'active']" @click="view = 'overview'">总览</button>
        <button :class="['tab', view === 'library' && 'active']" @click="view = 'library'">资料库</button>
      </nav>
      <button class="ghost icon" @click="toggleTheme" :title="theme === 'light' ? '切换深色' : '切换浅色'">
        {{ theme === 'light' ? '🌙' : '☀️' }}
      </button>
    </header>

    <main class="content">
      <div v-if="loading" class="center muted">加载中…</div>
      <div v-else-if="error" class="center">
        <p class="muted">⚠️ {{ error }}</p>
        <button @click="load">重试</button>
      </div>
      <template v-else>
        <BoardView
          v-if="view === 'board'"
          :tasks="tasks"
          @open="openEdit"
          @create="openCreate"
          @update-status="onStatusChange"
        />
        <OverviewView v-else-if="view === 'overview'" :tasks="tasks" @open="openEdit" />
        <LibraryView v-else />
      </template>
    </main>

    <TaskModal
      v-if="modalOpen"
      :task="editing"
      @save="onSave"
      @delete="onDelete"
      @changed="load"
      @close="closeModal"
    />
  </div>
</template>

<style scoped>
.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
}
.topbar {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 14px 24px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}
.brand {
  font-size: 18px;
  font-weight: 700;
}
.tabs {
  display: flex;
  gap: 8px;
  flex: 1;
}
.tab {
  background: transparent;
  color: var(--text-soft);
}
.tab.active {
  background: var(--accent);
  color: #fff;
}
.icon {
  font-size: 18px;
  padding: 8px 12px;
}
.content {
  flex: 1;
  padding: 20px 24px;
  overflow: auto;
}
.center {
  text-align: center;
  padding: 48px;
}
</style>
