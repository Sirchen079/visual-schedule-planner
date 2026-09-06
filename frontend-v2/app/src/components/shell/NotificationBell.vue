<script setup lang="ts">
/**
 * 头部通知铃铛（内容头右侧、时钟旁）：未读徽标 + 下拉通知面板。
 * - 未读数来自 notifications store 的 30s 轮询（壳层启停），0 不显示数字，99+ 封顶
 * - 面板每次打开重拉列表；逐条「已读」/顶部「全部已读」就地落章（本地增量维护未读数）
 * - 点外面关闭：透明点击层垫在面板下（ConversationList 同款手法，无全局监听可泄漏）
 * - 空态/加载/错误三态用 DomainState（空态在浮层里压紧内边距）
 */
import { computed } from 'vue'
import AppIcon from '../AppIcon.vue'
import DomainState from '../domain/DomainState.vue'
import { useNotificationsStore } from '../../stores/notifications'
import type { Notification } from '../../api/notifications'
import { notificationTarget } from '../../api/notificationTarget'

const store = useNotificationsStore()

const badgeLabel = computed(() => (store.unreadCount > 99 ? '99+' : String(store.unreadCount)))

function timeLabel(n: Notification): string {
  if (!n.remind_at) return ''
  const d = new Date(n.remind_at)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getMonth() + 1}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function openFollowup(n: Notification) { store.closePanel(); if (n.read_at === null) void store.markRead(n.id) }

function toggle(): void {
  if (store.panelOpen) store.closePanel()
  else void store.openPanel()
}
</script>

<template>
  <div class="bell-wrap">
    <button
      class="bell"
      :data-open="store.panelOpen"
      :aria-label="`通知（未读 ${store.unreadCount} 条）`"
      title="通知"
      @click="toggle"
    >
      <AppIcon name="bell" :size="17" />
      <span v-if="store.unreadCount > 0" class="badge">{{ badgeLabel }}</span>
    </button>

    <button
      v-if="store.panelOpen"
      class="click-away"
      aria-label="关闭通知面板"
      tabindex="-1"
      @click="store.closePanel()"
    />

    <div v-if="store.panelOpen" class="panel" role="dialog" aria-label="通知面板">
      <header class="p-head">
        <span class="cap">通知</span>
        <button
          v-if="store.unreadCount > 0"
          class="read-all"
          :disabled="store.markingAll"
          @click="store.markAllRead()"
        >
          {{ store.markingAll ? '标记中…' : '全部已读' }}
        </button>
      </header>
      <p v-if="store.actionError" class="warn" role="alert">{{ store.actionError }}</p>
      <DomainState
        class="p-state"
        :loading="store.loading"
        loading-text="正在拉取通知…"
        :error="store.error"
        :empty="!store.loading && !store.error && store.notifications !== null && store.notifications.length === 0"
        empty-title="暂无通知"
        @retry="store.openPanel()"
      >
        任务提醒与系统通知会出现在这里。
      </DomainState>
      <ul v-if="store.notifications && store.notifications.length > 0" class="list">
        <li v-for="n in store.notifications" :key="n.id" :data-unread="n.read_at === null">
          <div class="li-top">
            <span class="li-title">{{ n.title || '（无标题）' }}</span>
            <span v-if="timeLabel(n)" class="li-time">{{ timeLabel(n) }}</span>
          </div>
          <p v-if="n.body" class="li-body">{{ n.body }}</p>
          <RouterLink v-if="notificationTarget(n.target_path, n.task_id)" class="li-open" :to="notificationTarget(n.target_path, n.task_id)!" @click="openFollowup(n)">{{ n.kind === 'bill_reminder' ? '查看账单' : n.kind === 'research_watch' ? '查看资料跟进' : n.kind === 'followup' ? '查看跟进' : n.kind === 'event_reminder' ? '查看日程' : '查看任务' }} →</RouterLink>
          <button
            v-if="n.read_at === null"
            class="li-read"
            :disabled="store.markingRead.includes(n.id)"
            @click="store.markRead(n.id)"
          >
            {{ store.markingRead.includes(n.id) ? '标记中…' : '已读' }}
          </button>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.li-open { display:inline-block; color:var(--amber); font-size:12px; margin:0 12px 8px 0; }
.bell-wrap {
  position: relative;
  display: flex;
  align-items: center;
}
.bell {
  position: relative;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-s);
  color: var(--ink-3);
}
.bell:hover,
.bell[data-open='true'] {
  background: var(--ink-wash);
  color: var(--ink-2);
}
.badge {
  position: absolute;
  top: -3px;
  right: -6px;
  min-width: 16px;
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 600;
  line-height: 1;
  text-align: center;
  color: var(--btn-new-text);
  background: var(--terra);
  border-radius: var(--radius-pill);
  padding: 2px 4px;
}

/* 点外面关闭：透明点击层 */
.click-away {
  position: fixed;
  inset: 0;
  z-index: 40;
  cursor: default;
}
.panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 41;
  width: 336px;
  max-width: calc(100vw - 24px);
  max-height: 440px;
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
  border-bottom: 1px solid var(--line);
}
.cap {
  font-family: var(--mono);
  font-size: 11.5px;
  letter-spacing: 0.18em;
  color: var(--ink-3);
}
.read-all {
  margin-left: auto;
  font-size: 11.5px;
  color: var(--amber-soft);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-pill);
  padding: 2px 10px;
}
.read-all:hover:not(:disabled) {
  border-color: var(--line-hover);
}
.read-all:disabled {
  /* 浅色 --ctl-disabled-opacity=0.75（禁用文字须 ≥3:1）；暗色 fallback 0.5 不变 */
  opacity: var(--ctl-disabled-opacity, 0.5);
  cursor: default;
}
.warn {
  flex: none;
  font-size: 12px;
  color: var(--terra-soft);
  padding: 8px 14px 0;
}
.p-state {
  flex: none;
  overflow: auto;
}
/* DomainState 空态在浮层里压紧（默认 56px 上下留白是给整页的） */
.p-state :deep(.ds-empty) {
  padding: 26px 20px;
}
.p-state :deep(.ds-mark) {
  font-size: 16px;
}
.p-state :deep(.ds-error) {
  margin: 10px 14px;
}

.list {
  overflow: auto;
  padding: 6px 6px 8px;
}
.list li {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 9px 10px 9px 14px;
  border-radius: var(--radius-s);
}
.list li[data-unread='true'] {
  background: var(--amber-wash);
}
.list li[data-unread='true']::before {
  content: '';
  position: absolute;
  left: 5px;
  top: 12px;
  bottom: 12px;
  width: 2px;
  border-radius: 1px;
  background: var(--amber-soft);
}
.li-top {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}
.li-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
li[data-unread='false'] .li-title {
  font-weight: 400;
  color: var(--ink-2);
}
.li-time {
  flex: none;
  margin-left: auto;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-3);
}
.li-body {
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--ink-2);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.li-read {
  align-self: flex-start;
  font-size: 11px;
  color: var(--amber-soft);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-pill);
  padding: 1px 9px;
  margin-top: 2px;
}
.li-read:hover:not(:disabled) {
  border-color: var(--line-hover);
}
.li-read:disabled {
  /* 同 read-all：浅色 0.75、暗色 fallback 0.5 不变 */
  opacity: var(--ctl-disabled-opacity, 0.5);
  cursor: default;
}

@media (max-width: 880px) {
  .panel {
    position: fixed;
    top: 52px;
    left: 12px;
    right: 12px;
    width: auto;
    max-width: none;
  }
}
</style>
