<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import ArtIcon from './ArtIcon.vue'
import SegmentedControl from './ui/SegmentedControl.vue'
import EmptyState from './ui/EmptyState.vue'
import AppSpinner from './ui/AppSpinner.vue'
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from '../api/notifications'
import { getTask } from '../api/tasks'
import { refreshUnreadCount } from '../composables/useReminders'

defineProps({
  upcoming: { type: Array, required: true },
  overdue: { type: Array, required: true },
  triggered: { type: Array, default: () => [] },
})
const emit = defineEmits(['open', 'close'])

const tab = ref('remind')
const tabOptions = [
  { value: 'remind', label: '提醒' },
  { value: 'notice', label: '通知' },
]

function onKeydown(event) {
  if (event.key === 'Escape') emit('close')
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

function fmt(d) {
  if (!d) return ''
  return new Date(d).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

// 偏移分钟 → 中文文案（截止时 / 提前N分钟 / 提前N小时 / 提前N天）
function offsetLabel(minutes) {
  if (!minutes) return '截止时'
  if (minutes % 1440 === 0) return `提前${minutes / 1440}天`
  if (minutes % 60 === 0) return `提前${minutes / 60}小时`
  return `提前${minutes}分钟`
}

function triggeredDueTime(item) {
  return item.task?.due_time || String(item.due_at || '').slice(11, 16)
}

// ---- 通知中心 ----
const notifications = ref([])
const noticesLoading = ref(false)
const markingAll = ref(false)
const unreadInList = computed(() => notifications.value.filter((n) => !n.read_at).length)

// 切到「通知」页时拉取一次历史列表
watch(tab, (value) => {
  if (value === 'notice') loadNotifications()
})

async function loadNotifications() {
  noticesLoading.value = true
  try {
    notifications.value = await listNotifications(50)
  } catch {
    // 网络波动等：保持现状，由空态/旧数据兜底
  } finally {
    noticesLoading.value = false
  }
}

// 创建时间 → 相对时间（x 分钟前 / x 小时前 / x 天前）
function relativeTime(value) {
  if (!value) return ''
  const time = new Date(value).getTime()
  if (Number.isNaN(time)) return ''
  const minutes = Math.floor((Date.now() - time) / 60000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时前`
  return `${Math.floor(hours / 24)} 天前`
}

// 点击通知：标记已读（角标即时刷新），并打开对应任务编辑；任务已删除时仅完成已读
async function openNotification(n) {
  if (!n.read_at) {
    markNotificationRead(n.id)
      .then((res) => {
        n.read_at = res?.read_at || new Date().toISOString()
        refreshUnreadCount()
      })
      .catch(() => {})
  }
  try {
    const task = await getTask(n.task_id)
    emit('open', task)
  } catch {
    // 任务可能已删除：不跳转
  }
}

async function markAllRead() {
  if (!unreadInList.value || markingAll.value) return
  markingAll.value = true
  try {
    await markAllNotificationsRead()
    const now = new Date().toISOString()
    notifications.value = notifications.value.map((n) => (n.read_at ? n : { ...n, read_at: now }))
    refreshUnreadCount()
  } catch {
    // 失败保持原状，可重试
  } finally {
    markingAll.value = false
  }
}
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <div class="panel">
      <div class="head">
        <div class="head-title">
          <ArtIcon name="bell" tone="aqua" :size="28" tile :label="tab === 'remind' ? '提醒' : '通知'" />
          <span>{{ tab === 'remind' ? '提醒' : '通知' }}</span>
        </div>
        <button class="ghost close-btn" @click="emit('close')">
          <ArtIcon name="close" tone="pearl" :size="18" />
          <span>关闭</span>
        </button>
      </div>

      <SegmentedControl v-model="tab" :options="tabOptions" size="sm" class="panel-tabs" />

      <template v-if="tab === 'remind'">
        <section v-if="triggered.length" class="section">
          <h3 class="section-title triggered-title">
            <ArtIcon name="bell" tone="sand" :size="18" />
            到点提醒（{{ triggered.length }}）
          </h3>
          <div
            class="item"
            v-for="item in triggered"
            :key="`${item.task.id}-${item.remind_at}`"
            @click="emit('open', item.task)"
          >
            <div class="item-main">
              <span class="title">{{ item.task.title }}</span>
              <span class="muted">截止 {{ triggeredDueTime(item) }} · {{ offsetLabel(item.offset_minutes) }}</span>
            </div>
            <span class="tag now">
              <ArtIcon name="bell" tone="sand" :size="15" />
              <span>到点</span>
            </span>
          </div>
        </section>

        <section v-if="overdue.length" class="section">
          <h3 class="section-title overdue-title">
            <ArtIcon name="priority" tone="coral" :size="18" />
            已逾期（{{ overdue.length }}）
          </h3>
          <div class="item overdue" v-for="t in overdue" :key="t.id" @click="emit('open', t)">
            <div class="item-main">
              <span class="title">{{ t.title }}</span>
              <span class="muted">{{ fmt(t.due_date) }}</span>
            </div>
            <span class="tag urgent">
              <ArtIcon name="priority" tone="coral" :size="15" />
              <span>逾期</span>
            </span>
          </div>
        </section>

        <section v-if="upcoming.length" class="section">
          <h3 class="section-title">
            <ArtIcon name="calendar" tone="aqua" :size="18" />
            即将到期（24 小时内，{{ upcoming.length }}）
          </h3>
          <div class="item" v-for="t in upcoming" :key="t.id" @click="emit('open', t)">
            <div class="item-main">
              <span class="title">{{ t.title }}</span>
              <span class="muted">{{ fmt(t.due_date) }}</span>
            </div>
            <span class="tag soon">
              <ArtIcon name="bell" tone="aqua" :size="15" />
              <span>快到期</span>
            </span>
          </div>
        </section>

        <div v-if="!overdue.length && !upcoming.length && !triggered.length" class="empty">
          <div class="empty-title">节奏平稳</div>
          <div class="muted">暂无到期或逾期任务。</div>
        </div>
      </template>

      <template v-else>
        <section v-if="notifications.length" class="section notice-section">
          <h3 class="section-title">
            <ArtIcon name="bell" tone="sand" :size="18" />
            通知记录{{ unreadInList ? `（未读 ${unreadInList}）` : '' }}
            <button class="ghost compact mark-all" :disabled="!unreadInList || markingAll" @click="markAllRead">
              <ArtIcon name="check" tone="aqua" :size="15" />
              <span>全部已读</span>
            </button>
          </h3>
          <div
            class="item notice-item"
            :class="{ unread: !n.read_at }"
            v-for="n in notifications"
            :key="n.id"
            @click="openNotification(n)"
          >
            <ArtIcon name="bell" tone="sand" :size="18" class="notice-icon" />
            <div class="item-main">
              <span class="title">{{ n.title }}</span>
              <span class="muted">{{ n.body }}</span>
            </div>
            <span class="notice-time">{{ relativeTime(n.created_at) }}</span>
          </div>
        </section>
        <div v-else-if="noticesLoading" class="notice-loading">
          <AppSpinner size="md" label="正在加载通知..." />
        </div>
        <EmptyState
          v-else
          icon="bell"
          title="暂无通知"
          hint="提醒到点后会自动记录在这里，可随时回溯。"
        />
      </template>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  z-index: 120;
  background: var(--overlay-bg);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  padding: 82px 24px 24px;
}

.panel {
  width: 400px;
  max-width: 92vw;
  max-height: calc(100vh - 110px);
  overflow: auto;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl), var(--shadow-inset);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  padding: 22px;
  position: relative;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.head-title {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  font-size: 18px;
  font-weight: 800;
  color: var(--text);
}

.close-btn {
  min-height: 34px;
  padding: 7px 12px;
  display: flex;
  align-items: center;
  gap: 5px;
  justify-content: center;
  border-radius: var(--radius-sm);
}

.panel-tabs {
  display: flex;
  width: 100%;
  margin-bottom: 16px;
}

.panel-tabs :deep(.seg-item) {
  flex: 1;
  justify-content: center;
}

.section {
  margin-bottom: 18px;
}

.section:last-child {
  margin-bottom: 0;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-soft);
}

.overdue-title {
  color: var(--pri-high);
}

.triggered-title {
  color: var(--warning);
}

.item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 11px 13px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  margin-bottom: 7px;
  background: var(--surface-2);
  border: 1px solid transparent;
  transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease, background 0.15s ease;
}

.item:hover {
  transform: translateX(2px);
  box-shadow: var(--shadow-sm);
  border-color: var(--border);
  background: var(--surface);
}

.item-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
  font-size: 14px;
}

.tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 700;
  padding: 3px 9px;
  border-radius: var(--radius-pill);
  flex-shrink: 0;
}

.tag.urgent {
  background: color-mix(in srgb, var(--danger) 12%, transparent);
  color: var(--pri-high);
}

.tag.soon {
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  color: var(--accent-hover);
}

.tag.now {
  background: color-mix(in srgb, var(--warning) 14%, transparent);
  color: var(--warning);
}

.empty {
  text-align: center;
  padding: 40px 10px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.empty-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

/* ---- 通知中心 ---- */
.mark-all {
  margin-left: auto;
  min-height: 26px;
  padding: 3px 10px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}

.notice-item .notice-icon {
  flex-shrink: 0;
}

.notice-time {
  flex-shrink: 0;
  align-self: flex-start;
  font-size: 11px;
  color: var(--text-soft);
}

/* 未读：左侧 accent 色条 + 标题加粗；用 inset 阴影避免布局位移 */
.notice-item.unread {
  box-shadow: inset 3px 0 0 var(--accent);
}

.notice-item.unread:hover {
  box-shadow: var(--shadow-sm), inset 3px 0 0 var(--accent);
}

.notice-item.unread .title {
  font-weight: 700;
}

.notice-loading {
  display: grid;
  place-items: center;
  min-height: 160px;
}

@media (max-width: 480px) {
  .overlay {
    padding: 76px 12px 12px;
  }
  .panel {
    width: 100%;
    max-height: calc(100vh - 95px);
    padding: 18px;
  }
}
</style>
