<script setup>
// 秘书自动档卡片：应用启动时展示秘书已代办的排程/拆解结果（风格对齐 BriefingCard）。
// 每条动作可单独撤销：排程项删日程条目，拆解项逐个删子任务（全删成功才移除该行）。
// Esc / 点击遮罩 / 「知道了」关闭；同一天只自动弹一次（由 App 节流）。
import { inject, onBeforeUnmount, onMounted, ref } from 'vue'
import ArtIcon from './ArtIcon.vue'
import { deleteScheduleEntry } from '../api/schedule'
import { deleteSubtask } from '../api/tasks'

const props = defineProps({
  // runAutopilot() 的响应：{ message, actions: [...] }
  result: { type: Object, required: true },
})
const emit = defineEmits(['close'])

const toast = inject('toast', { success: () => {}, error: () => {}, info: () => {}, undo: () => {} })

// 本地维护动作列表：撤销成功的行就地移除
const actions = ref([...(props.result.actions || [])])
// 撤销中的行（按对象身份标记），防止重复点击
const undoing = ref(new Set())

function actionKey(action, index) {
  return `${action.kind}-${action.task_id}-${index}`
}

function dateLabel(dateStr) {
  const d = new Date(`${dateStr}T00:00:00`)
  return `${d.getMonth() + 1}月${d.getDate()}日`
}

function breakdownSummary(action) {
  const titles = (action.subtasks || []).slice(0, 3)
  const suffix = (action.subtasks || []).length > 3 ? '…' : ''
  return `《${action.title}》拆成 ${(action.subtasks || []).length} 步：${titles.join('、')}${suffix}`
}

function removeRow(action) {
  actions.value = actions.value.filter((a) => a !== action)
}

async function undo(action) {
  if (undoing.value.has(action)) return
  undoing.value = new Set(undoing.value).add(action)
  try {
    if (action.kind === 'schedule') {
      await deleteScheduleEntry(action.entry_id)
      removeRow(action)
      toast.success(`已撤销《${action.title}》的排程`)
    } else {
      // 拆解：逐个删除子任务，全部成功才移除该行
      for (const subId of action.subtask_ids || []) {
        await deleteSubtask(action.task_id, subId)
      }
      removeRow(action)
      toast.success(`已撤销《${action.title}》的拆解`)
    }
    window.dispatchEvent(new Event('tasks:refresh'))
  } catch (e) {
    toast.error(`撤销失败：${e.message}`)
  } finally {
    const next = new Set(undoing.value)
    next.delete(action)
    undoing.value = next
  }
}

function close() {
  emit('close')
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
      <div class="panel" role="dialog" aria-modal="true" aria-label="秘书自动档">
        <div class="head">
          <div class="head-title">
            <ArtIcon name="assistant" tone="aqua" :size="30" tile label="秘书自动档" />
            <div class="head-text">
              <span class="title">秘书已为你办妥</span>
              <span v-if="result.message" class="summary muted">{{ result.message }}</span>
            </div>
          </div>
          <button class="ghost close-btn" @click="close" title="关闭">
            <ArtIcon name="close" tone="pearl" :size="18" label="关闭" />
          </button>
        </div>

        <div class="content">
          <TransitionGroup name="list" tag="div">
            <div v-for="(action, i) in actions" :key="actionKey(action, i)" class="action-row">
              <ArtIcon
                :name="action.kind === 'schedule' ? 'calendar' : 'steps'"
                :tone="action.kind === 'schedule' ? 'aqua' : 'mint'"
                :size="26"
                tile
                :label="action.kind === 'schedule' ? '自动排程' : '自动拆解'"
              />
              <span class="action-text">
                <template v-if="action.kind === 'schedule'">
                  《{{ action.title }}》→ {{ dateLabel(action.date) }}<span v-if="action.note" class="muted">（{{ action.note }}）</span>
                </template>
                <template v-else>
                  {{ breakdownSummary(action) }}
                </template>
              </span>
              <button
                class="ghost undo-btn"
                :disabled="undoing.has(action)"
                title="撤销这条代办"
                @click="undo(action)"
              >
                {{ undoing.has(action) ? '撤销中…' : '撤销' }}
              </button>
            </div>
          </TransitionGroup>
          <p v-if="!actions.length" class="muted empty-text">所有代办都已撤销。</p>
        </div>

        <div class="actions">
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
  min-width: 0;
}
.head-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.title {
  font-size: 18px;
  font-weight: 800;
  color: var(--text);
}
.summary {
  font-size: 12px;
  line-height: 1.5;
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

.action-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  border: 1px solid transparent;
  box-shadow: var(--shadow-inset);
  margin-bottom: 8px;
}
.action-text {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text);
}
.undo-btn {
  flex-shrink: 0;
  padding: 5px 12px;
  font-size: 12px;
  border-radius: var(--radius-sm);
}
.empty-text {
  padding: 12px 0;
  text-align: center;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
  flex-shrink: 0;
}

.list-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.list-leave-to {
  opacity: 0;
  transform: translateX(10px);
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
