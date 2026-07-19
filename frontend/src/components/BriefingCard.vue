<script setup>
// 每日晨报卡片：应用启动时在主窗口顶层展示今日晨报（AI 生成或规则模板）。
// 层级与动画参考 StartupReminder；Esc / 点击遮罩 / 按钮关闭，同一天只自动弹一次（由 App 节流）。
import { computed, onBeforeUnmount, onMounted } from 'vue'
import ArtIcon from './ArtIcon.vue'
import MarkdownText from './MarkdownText.vue'

const props = defineProps({
  report: { type: Object, required: true },
})
const emit = defineEmits(['close'])

const dateLabel = computed(() => {
  const d = new Date()
  return `${d.getMonth() + 1} 月 ${d.getDate()} 日`
})
// 无 AI 配置时后端以规则模板生成，model_name 固定为「规则模板」
const modelName = computed(() => props.report.model_name || '规则模板')

function close() {
  emit('close')
}

// 把晨报正文带进助手输入框，由用户确认后发送（沿用 assistant:prompt 通道）
function askAssistant() {
  window.dispatchEvent(
    new CustomEvent('assistant:prompt', {
      detail: {
        text: `${props.report.content || ''}\n\n基于晨报帮我安排今天`,
      },
    })
  )
  close()
}

function onKeydown(e) {
  if (e.key === 'Escape') close()
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Transition name="modal">
    <div class="overlay" @click.self="close">
      <div class="panel" role="dialog" aria-modal="true" aria-label="今日晨报">
        <div class="head">
          <div class="head-title">
            <ArtIcon name="brand" tone="aqua" :size="30" tile label="今日晨报" />
            <div class="head-text">
              <span class="title">今日晨报 · {{ dateLabel }}</span>
              <span class="model-badge">{{ modelName }}</span>
            </div>
          </div>
          <button class="ghost close-btn" @click="close" title="关闭">
            <ArtIcon name="close" tone="pearl" :size="18" label="关闭" />
          </button>
        </div>

        <div class="content">
          <MarkdownText :content="report.content" />
        </div>

        <div class="actions">
          <button class="ghost ask-btn" @click="askAssistant">
            <ArtIcon name="assistant" tone="aqua" :size="16" />
            <span>问助手</span>
          </button>
          <button @click="close">知道了</button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  z-index: 150;
  background: var(--overlay-bg);
  backdrop-filter: blur(7px);
  -webkit-backdrop-filter: blur(7px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.panel {
  width: 560px;
  max-width: 92vw;
  max-height: calc(100vh - 60px);
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl), var(--shadow-inset);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  padding: 22px;
}

.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 14px;
  flex-shrink: 0;
}
.head-title {
  display: inline-flex;
  align-items: center;
  gap: 12px;
}
.head-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.title {
  font-size: 18px;
  font-weight: 800;
  color: var(--text);
}
.model-badge {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  background: var(--accent-soft);
  color: var(--accent-hover);
  border: 1px solid color-mix(in srgb, var(--accent) 22%, var(--border));
}
.close-btn {
  width: 34px;
  height: 34px;
  min-width: 34px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
}

.content {
  min-height: 0;
  overflow: auto;
  padding-right: 4px;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
  flex-shrink: 0;
}
.ask-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.22s ease;
}
.modal-enter-active .panel,
.modal-leave-active .panel {
  transition: opacity 0.22s ease, transform 0.28s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
.modal-enter-from .panel,
.modal-leave-to .panel {
  opacity: 0;
  transform: translateY(14px) scale(0.96);
}
</style>
