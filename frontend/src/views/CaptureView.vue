<script setup>
// 全局快速捕获小窗（?view=capture）：Ctrl+Shift+A 唤出，输入一句话回车即建任务。
// 自包含页面：直接调任务 API，不依赖 App 主界面数据；浏览器环境（无 electronAPI）也可正常使用。
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import ArtIcon from '../components/ArtIcon.vue'
import { createTask } from '../api/tasks'
import { formatQuickHint, parseQuickInput } from '../utils/quickparse'

const text = ref('')
const inputEl = ref(null)
const busy = ref(false)
// 反馈条：{ kind: 'success' | 'error', text }，自动消失；窗口保持开启可连续捕获
const feedback = ref(null)
let feedbackTimer = null

// 实时自然语言解析提示（日期/时间/优先级/标签 chips）
const hints = computed(() => {
  const value = text.value.trim()
  return value ? formatQuickHint(parseQuickInput(value)) : []
})

function focusInput() {
  nextTick(() => inputEl.value?.focus())
}

function showFeedback(kind, message, duration) {
  feedback.value = { kind, text: message }
  clearTimeout(feedbackTimer)
  feedbackTimer = setTimeout(() => (feedback.value = null), duration)
}

async function submit() {
  const value = text.value.trim()
  if (!value || busy.value) return
  const parsed = parseQuickInput(value)
  // payload 约定与看板快速新建一致：纯日期序列化为当天 23:59:59
  const payload = { title: parsed.title }
  if (parsed.due_date) payload.due_date = `${parsed.due_date}T23:59:59`
  if (parsed.due_time) payload.due_time = parsed.due_time
  if (parsed.priority) payload.priority = parsed.priority
  if (parsed.tags.length) payload.tags = parsed.tags
  busy.value = true
  try {
    await createTask(payload)
    text.value = ''
    showFeedback('success', `已创建《${payload.title}》`, 1500)
  } catch (e) {
    showFeedback('error', e?.message || '创建失败，请重试', 2500)
  } finally {
    busy.value = false
    focusInput()
  }
}

function closeSelf() {
  window.electronAPI?.captureClose?.()
}

function onKeydown(e) {
  if (e.key === 'Escape') {
    e.preventDefault()
    closeSelf()
  } else if (e.key === 'Enter') {
    e.preventDefault()
    // Ctrl+Enter 无内容时关闭小窗；其余情况回车即创建
    if (e.ctrlKey && !text.value.trim()) closeSelf()
    else submit()
  }
}

onMounted(() => {
  focusInput()
  // 小窗由快捷键再次唤出（hide -> show -> focus）时，确保输入框重新获得焦点
  window.addEventListener('focus', focusInput)
})
onUnmounted(() => {
  window.removeEventListener('focus', focusInput)
  clearTimeout(feedbackTimer)
})
</script>

<template>
  <div class="capture">
    <header class="capture-head">
      <ArtIcon name="brand" tone="aqua" :size="18" />
      <span class="capture-title">快速捕获</span>
      <span class="capture-tip muted">Enter 创建 · Esc 关闭</span>
    </header>
    <input
      ref="inputEl"
      v-model="text"
      class="capture-input"
      placeholder="一句话建任务：明天下午3点 交周报 !高 #工作"
      aria-label="快速捕获任务"
      @keydown="onKeydown"
    />
    <div v-if="hints.length" class="capture-hints">
      <span v-for="hint in hints" :key="hint" class="hint-chip">{{ hint }}</span>
    </div>
    <Transition name="fade">
      <p v-if="feedback" class="capture-feedback" :class="feedback.kind">{{ feedback.text }}</p>
    </Transition>
  </div>
</template>

<style scoped>
.capture {
  height: 100vh;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

/* 无边框窗口：标题栏区域可拖动（浏览器下该属性被忽略，无副作用） */
.capture-head {
  display: flex;
  align-items: center;
  gap: 8px;
  user-select: none;
  -webkit-app-region: drag;
}

.capture-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
}

.capture-tip {
  margin-left: auto;
  font-size: 11px;
}

.capture-input {
  width: 100%;
  height: 42px;
  padding: 0 12px;
  border-radius: var(--radius-sm);
  font-size: 14px;
}

.capture-hints {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.hint-chip {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 9px;
  border-radius: var(--radius-pill);
  background: var(--accent-soft);
  color: var(--accent-strong);
  font-size: 11px;
  font-weight: 700;
}

.capture-feedback {
  margin: 0;
  font-size: 12px;
  font-weight: 700;
}

.capture-feedback.success {
  color: var(--success);
}

.capture-feedback.error {
  color: var(--danger);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.18s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
