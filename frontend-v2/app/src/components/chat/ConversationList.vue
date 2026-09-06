<script setup lang="ts">
/**
 * 会话列表面板（chat-head 下拉）：GET /ai/conversations 列表、新建会话、切换加载历史。
 */
import { onMounted } from 'vue'
import { useConversationStore } from '../../stores/conversation'
import { useRunStore } from '../../stores/run'
import AppIcon from '../AppIcon.vue'

const emit = defineEmits<{ close: [] }>()
const conv = useConversationStore()
const run = useRunStore()

onMounted(() => {
  void conv.refresh()
})

function timeShort(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getMonth() + 1}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function pick(id: number): void {
  void conv.select(id)
  emit('close')
}

function startNew(): void {
  conv.startNew()
  emit('close')
}
</script>

<template>
  <div class="conv-wrap">
    <div class="backdrop" @click="emit('close')" />
    <div class="panel" role="dialog" aria-label="会话列表">
      <div class="p-head">
        <span class="cap">会话</span>
        <button class="new" :disabled="run.hasLiveStream() || conv.sending || conv.initializing" title="新建会话" @click="startNew">
          <AppIcon name="plus" :size="12" />
          新建会话
        </button>
      </div>
      <p v-if="run.hasLiveStream()" class="note">任务进行中，暂不能新建会话；切换会话可查看历史。</p>
      <p v-if="conv.error" class="note warn">{{ conv.error }}</p>
      <p v-if="!conv.conversations.length && !conv.error" class="note">还没有会话 —— 发出第一条消息即自动创建。</p>
      <ul class="list">
        <li
          v-for="c in conv.conversations"
          :key="c.id"
          :data-active="c.id === conv.activeId"
          @click="pick(c.id)"
        >
          <span class="t">{{ c.title || `会话 ${c.id}` }}</span>
          <span class="m">{{ timeShort(c.updated_at) }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.conv-wrap {
  position: absolute;
  inset: 0;
  z-index: 30;
}
.backdrop {
  position: absolute;
  inset: 0;
  background: var(--overlay-backdrop);
}
.panel {
  position: absolute;
  top: 8px;
  left: 16px;
  right: 16px;
  max-height: 420px;
  display: flex;
  flex-direction: column;
  background: var(--bg-raise);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-l);
  box-shadow: var(--shadow-panel);
  overflow: hidden;
}
.p-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px 8px;
  flex: none;
}
.cap {
  font-family: var(--mono);
  font-size: 11.5px;
  letter-spacing: 0.18em;
  color: var(--ink-3);
}
.new {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 600;
  color: var(--btn-new-text);
  background: var(--btn-new-bg);
  padding: 5px 11px;
  border-radius: 8px;
}
.new:hover:not(:disabled) {
  background: var(--btn-new-bg-hover);
}
.new:disabled {
  /* 实底填充白字禁用件：浅色 solid 档 0.9 才 ≥3:1；暗色 fallback 0.5 不变 */
  opacity: var(--ctl-disabled-opacity-solid, 0.5);
  cursor: not-allowed;
}
.note {
  padding: 0 16px 8px;
  font-size: 12px;
  color: var(--ink-3);
  line-height: 1.6;
}
.note.warn {
  color: var(--terra-soft);
}
.list {
  overflow: auto;
  padding: 0 6px 8px;
}
.list li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border-radius: 8px;
  cursor: pointer;
}
.list li:hover {
  background: var(--ink-wash);
}
.list li[data-active='true'] {
  background: var(--nav-active-bg);
}
.list .t {
  font-size: 13px;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.list li[data-active='true'] .t {
  color: var(--amber-soft);
}
.list .m {
  margin-left: auto;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-3);
  flex: none;
}
</style>
