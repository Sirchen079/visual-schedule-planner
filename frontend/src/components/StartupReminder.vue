<script setup>
// 启动提醒：应用挂载后拉取未来 7 天的 DDL 与今日安排，按紧迫度分档措辞展示。
// 同一天只自动弹一次（localStorage 节流），避免反复打开打扰；点击条目可跳转编辑。
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import ArtIcon from './ArtIcon.vue'
import { getDueReminders } from '../api/reminders'
import { getDaySchedule } from '../api/schedule'

const props = defineProps({
  hostWindow: { type: Boolean, default: false },
})
const emit = defineEmits(['open'])

const THROTTLE_KEY = 'startup_reminder_last_date'
const WINDOW_HOURS = 168 // 覆盖未来 7 天的 DDL

const visible = ref(false)
// [{ tier, items: [{ task, tone, badge, line }] }]
const sections = ref([])
const todayCount = ref(0)
const headline = ref('')

const dateLabel = computed(() => {
  const d = new Date()
  return `${d.getMonth() + 1} 月 ${d.getDate()} 日`
})

function dateKey() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// 以「自然天」差值计剩余天数，避免几小时误差把"今天"算成 1 天
function daysUntil(dueDate) {
  const due = new Date(dueDate)
  const now = new Date()
  const a = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const b = new Date(due.getFullYear(), due.getMonth(), due.getDate())
  return Math.round((b - a) / 86400000)
}

function classify(task) {
  const days = daysUntil(task.due_date)
  if (days < 0)
    return {
      tier: 'overdue',
      tone: 'coral',
      badge: `逾期 ${-days} 天`,
      line: `已逾期 ${-days} 天 ·《${task.title}》—— 建议尽快处理，或顺手改个截止时间`,
    }
  if (days === 0)
    return {
      tier: 'today',
      tone: 'coral',
      badge: '今天截止',
      line: `今天截止 ·《${task.title}》—— 别让它拖到明天`,
    }
  if (days <= 3)
    return {
      tier: 'soon',
      tone: 'sand',
      badge: `还剩 ${days} 天`,
      line: `还剩 ${days} 天 ·《${task.title}》—— 可以开始收尾了`,
    }
  return {
    tier: 'later',
    tone: 'aqua',
    badge: `还有 ${days} 天`,
    line: `还有 ${days} 天 ·《${task.title}》—— 提前安排更从容`,
  }
}

const TIER_ORDER = ['overdue', 'today', 'soon', 'later']
const TIER_LABEL = {
  overdue: '已逾期',
  today: '今天截止',
  soon: '临近（1–3 天）',
  later: '稍后（4–7 天）',
}

async function check() {
  if (localStorage.getItem(THROTTLE_KEY) === dateKey()) return
  try {
    const [due, schedule] = await Promise.all([
      getDueReminders(WINDOW_HOURS),
      getDaySchedule(dateKey()).catch(() => null),
    ])
    const all = [...(due.overdue || []), ...(due.upcoming || [])]
    const byTier = {}
    for (const task of all) {
      const c = classify(task)
      ;(byTier[c.tier] ||= []).push({ task, ...c })
    }
    sections.value = TIER_ORDER.filter((t) => byTier[t]?.length).map((t) => ({
      tier: t,
      items: byTier[t],
    }))

    const s = schedule?.summary
    todayCount.value = s ? s.must_do + s.planned + s.in_progress_today : 0

    const ddl = all.length
    if (ddl && todayCount.value) {
      headline.value = `今日 ${todayCount.value} 项 · 其中 ${ddl} 项临近截止`
    } else if (ddl) {
      headline.value = `${ddl} 项任务临近截止`
    } else if (todayCount.value) {
      headline.value = `今日 ${todayCount.value} 项待处理`
    }

    if (sections.value.length || todayCount.value > 0) {
      visible.value = true
      localStorage.setItem(THROTTLE_KEY, dateKey())
      // 独立小窗：内容就绪后再显示窗口，避免白屏
      if (props.hostWindow) window.electronAPI?.showSelf?.()
    } else if (props.hostWindow) {
      // 小窗无提醒内容：静默关闭，不打扰
      window.electronAPI?.closeSelf?.()
    }
  } catch {
    // 拉取失败：独立小窗静默关闭避免残留隐藏窗口；主窗口模态无妨
    if (props.hostWindow) window.electronAPI?.closeSelf?.()
  }
}

function onKeydown(e) {
  if (visible.value && e.key === 'Escape') close()
}
function close() {
  if (props.hostWindow) {
    window.electronAPI?.closeSelf?.()
    return
  }
  visible.value = false
}
function goHandle() {
  const first = sections.value.flatMap((s) => s.items)[0]
  if (props.hostWindow) {
    // 独立小窗：唤出主窗口并定位到最紧迫的任务
    if (first) window.electronAPI?.showMainWithTask?.(first.task.id)
    else window.electronAPI?.showMain?.()
  } else if (first) {
    emit('open', first.task)
  }
  close()
}

onMounted(check)
onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Transition name="modal">
    <div v-if="visible" class="overlay" :class="{ 'is-window': hostWindow }" @click.self="close">
      <div class="panel">
        <div class="head">
          <div class="head-title">
            <ArtIcon name="bell" tone="aqua" :size="30" tile label="今日提醒" />
            <div class="head-text">
              <span class="title">今日提醒</span>
              <span class="date">{{ dateLabel }}</span>
            </div>
          </div>
          <button class="ghost close-btn" @click="close" title="关闭">
            <ArtIcon name="close" tone="pearl" :size="18" label="关闭" />
          </button>
        </div>

        <p v-if="headline" class="headline">{{ headline }}</p>

        <section v-for="s in sections" :key="s.tier" class="section">
          <h3 class="section-title" :class="`tier-${s.tier}`">
            <span class="dot"></span>{{ TIER_LABEL[s.tier] }}（{{ s.items.length }}）
          </h3>
          <div
            class="item"
            v-for="entry in s.items"
            :key="entry.task.id"
            @click="emit('open', entry.task)"
          >
            <span class="badge" :class="`tone-${entry.tone}`">{{ entry.badge }}</span>
            <span class="line">{{ entry.line }}</span>
          </div>
        </section>

        <div v-if="todayCount && !sections.length" class="quiet muted">
          暂无临近截止的任务，节奏平稳。
        </div>

        <div class="actions">
          <button class="ghost" @click="close">知道了</button>
          <button v-if="sections.length" @click="goHandle">去处理</button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  z-index: 140;
  background: var(--overlay-bg);
  backdrop-filter: blur(7px);
  -webkit-backdrop-filter: blur(7px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.panel {
  width: 480px;
  max-width: 92vw;
  max-height: calc(100vh - 60px);
  overflow: auto;
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
  margin-bottom: 12px;
}
.head-title {
  display: inline-flex;
  align-items: center;
  gap: 12px;
}
.head-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.title {
  font-size: 18px;
  font-weight: 800;
  color: var(--text);
}
.date {
  font-size: 12px;
  color: var(--text-soft);
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

.headline {
  margin: 0 0 16px;
  padding: 10px 13px;
  border-radius: var(--radius-sm);
  background: var(--accent-soft);
  color: var(--accent-strong);
  font-size: 13px;
  font-weight: 700;
}

.section {
  margin-bottom: 16px;
}
.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 9px;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-soft);
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-muted);
}
.tier-overdue .dot,
.tier-today .dot {
  background: var(--danger);
}
.tier-soon .dot {
  background: var(--warning);
}
.tier-later .dot {
  background: var(--accent);
}
.tier-overdue,
.tier-today {
  color: var(--danger);
}

.item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 13px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  margin-bottom: 7px;
  background: var(--surface-2);
  border: 1px solid transparent;
  transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease,
    background 0.15s ease;
}
.item:hover {
  transform: translateX(2px);
  box-shadow: var(--shadow-sm);
  border-color: var(--border);
  background: var(--surface);
}
.badge {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  font-weight: 700;
  padding: 4px 10px;
  border-radius: var(--radius-pill);
  white-space: nowrap;
}
.badge.tone-coral {
  background: color-mix(in srgb, var(--danger) 13%, transparent);
  color: var(--danger);
}
.badge.tone-sand {
  background: color-mix(in srgb, var(--warning) 14%, transparent);
  color: var(--warning);
}
.badge.tone-aqua {
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  color: var(--accent-hover);
}
.line {
  min-width: 0;
  font-size: 13px;
  color: var(--text);
  line-height: 1.45;
}

.quiet {
  text-align: center;
  padding: 18px 10px;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
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

/* 独立小窗模式：铺满 frameless 窗口，去遮罩；标题栏可拖动 */
.overlay.is-window {
  background: transparent;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  padding: 0;
}
.overlay.is-window .panel {
  width: 100%;
  max-width: none;
  max-height: none;
  height: 100%;
  border-radius: 0;
  border: none;
  box-shadow: none;
}
.overlay.is-window .head {
  -webkit-app-region: drag;
}
.overlay.is-window .close-btn,
.overlay.is-window .actions,
.overlay.is-window .item {
  -webkit-app-region: no-drag;
}
</style>
