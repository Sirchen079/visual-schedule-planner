<script setup>
import { computed, onMounted, onBeforeUnmount, provide, ref } from 'vue'
import { useTasks } from './composables/useTasks'
import { useReminders } from './composables/useReminders'
import { restoreTask } from './api/tasks'
import { getTodayBriefing, listAiConfigs, runAutopilot } from './api/ai'
import { getSettings } from './api/settings'
import BoardView from './views/BoardView.vue'
import OverviewView from './views/OverviewView.vue'
import LibraryView from './views/LibraryView.vue'
import AssistantView from './views/AssistantView.vue'
import ReportView from './views/ReportView.vue'
import AssistantFloat from './views/AssistantFloat.vue'
import CaptureView from './views/CaptureView.vue'
import CalendarView from './views/CalendarView.vue'
import TimelineView from './views/TimelineView.vue'
import HabitsView from './views/HabitsView.vue'
import JournalView from './views/JournalView.vue'
import GoalsView from './views/GoalsView.vue'
import TrashView from './views/TrashView.vue'
import TaskModal from './components/TaskModal.vue'
import RemindersPanel from './components/RemindersPanel.vue'
import ArtIcon from './components/ArtIcon.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import FeaturePanel from './components/FeaturePanel.vue'
import FocusTimer from './components/FocusTimer.vue'
import StartupReminder from './components/StartupReminder.vue'
import BriefingCard from './components/BriefingCard.vue'
import AutopilotCard from './components/AutopilotCard.vue'
import CommandPalette from './components/CommandPalette.vue'
import WelcomeModal from './components/WelcomeModal.vue'
import BaseModal from './components/ui/BaseModal.vue'
import AppSpinner from './components/ui/AppSpinner.vue'

const { tasks, loading, error, load, add, update, remove } = useTasks()
const { upcoming, overdue, triggered, count, panelOpen, unreadCount, start: startReminders, refresh: refreshReminders } = useReminders()

// 独立提醒小窗：?view=reminder 时只渲染提醒组件（frameless 小窗专用）
// 悬浮窗：?view=assistant 时只渲染助手悬浮组件
// 快速捕获小窗：?view=capture 时只渲染全局捕获组件（Ctrl+Shift+A 唤出）
// 开机自启主窗口：?autostart=1 时不挂载启动弹窗（提醒由独立小窗承载）
const urlParams = new URLSearchParams(location.search)
const isReminderWindow = urlParams.get('view') === 'reminder'
const isAssistantFloatWindow = urlParams.get('view') === 'assistant'
const isCaptureWindow = urlParams.get('view') === 'capture'
const isAutoStartHost = urlParams.get('autostart') === '1'

onMounted(() => {
  // 小窗/悬浮窗/捕获窗专用窗口：不加载主界面数据、不启动轮询/通知
  if (isReminderWindow || isAssistantFloatWindow || isCaptureWindow) {
    // 悬浮窗是透明窗口，清除 body/html 背景渐变，避免方形底色从圆角/圆形外露出
    if (isAssistantFloatWindow) {
      document.documentElement.style.background = 'transparent'
      document.body.style.background = 'transparent'
    }
    return
  }
  load().then(maybeShowWelcome)
  // 功能开关：读取一次，控制导航/计时器等入口可见性
  getSettings().then(applyFeatureSettings).catch(() => {})
  // AI 配置可用性：启动读一次 provide 给各内嵌 AI 按钮（变动不频繁，不订阅更新）
  listAiConfigs()
    .then((configs) => {
      aiAvailable.value = (configs || []).some((c) => c?.enabled)
    })
    .catch(() => {})
  // 主窗口：接收小窗「去处理」传来的 taskId，打开对应任务编辑
  window.electronAPI?.onFocusTask?.((taskId) => {
    const t = tasks.value.find((x) => x.id === taskId)
    if (t) openEdit(t)
  })
  // 关闭询问：主窗口 close 行为为「每次询问」时，主进程发 ask-close，弹框让用户选
  window.electronAPI?.onAskClose?.(() => {
    confirmDialog({
      title: '关闭知时',
      message: '退出知时会结束后台运行；最小化到托盘则保持后台运行。如需固定此行为，可在设置中调整。',
      confirmText: '退出知时',
      cancelText: '最小化到托盘',
      danger: true,
    }).then((ok) => {
      window.electronAPI?.answerClose?.(ok ? 'quit' : 'minimize')
    })
  })
  // 主窗口重新获得焦点时静默刷新任务，确保悬浮窗里 AI 建的任务同步到看板
  window.addEventListener('focus', onFocusReload)
  window.addEventListener('keydown', onGlobalKeydown)
  // 任务卡右键菜单等组件内直接改库后，经该事件通知主界面静默刷新
  window.addEventListener('tasks:refresh', onTasksRefresh)
  // 每日晨报：设置开启且今天未展示过时拉取，排在启动提醒关闭之后展示
  void prepareBriefing()
  // 秘书自动档：设置开启且今天未展示过时执行，与晨报同一排队策略（先于晨报）
  void prepareAutopilot()
  // 开机自启的主窗口：提醒已由独立小窗承载，跳过通知轮询避免重复弹窗
  if (isAutoStartHost) return
  if (window.Notification && Notification.permission === 'default') {
    Notification.requestPermission().catch(() => {})
  }
  startReminders()
})

function onFocusReload() {
  load(true)
}

// 首次启动引导：任务加载完成后判断，onboarding_done 未完成且任务为空
// （全新用户）才显示欢迎页；老用户升级后已有数据，不打扰。
const welcomeOpen = ref(false)
async function maybeShowWelcome() {
  try {
    const s = await getSettings()
    if (s.onboarding_done !== '1' && !tasks.value.length) welcomeOpen.value = true
  } catch {
    // 设置读取失败不弹引导，不影响主流程
  }
}
function onTasksRefresh() {
  load(true)
}
onBeforeUnmount(() => {
  window.removeEventListener('focus', onFocusReload)
  window.removeEventListener('keydown', onGlobalKeydown)
  window.removeEventListener('tasks:refresh', onTasksRefresh)
  colorSchemeMql?.removeEventListener?.('change', onColorSchemeChange)
})

const view = ref('board')
// 功能开关（功能管理面板）：关闭只隐藏入口，数据保留
const features = ref({ habits: true, journal: true, goals: true, timer: true })
const featuresOpen = ref(false)
const tabs = [
  { key: 'board', label: '看板', icon: 'board' },
  { key: 'overview', label: '总览', icon: 'overview' },
  { key: 'calendar', label: '日历', icon: 'calendar' },
  { key: 'timeline', label: '时间轴', icon: 'timeline' },
  { key: 'habits', label: '习惯', icon: 'check', feature: 'habits' },
  { key: 'journal', label: '日记', icon: 'file', feature: 'journal' },
  { key: 'goals', label: '目标', icon: 'flag', feature: 'goals' },
  { key: 'library', label: '资料库', icon: 'library' },
  { key: 'report', label: '日报周报', icon: 'archive' },
  { key: 'trash', label: '回收站', icon: 'trash' },
]
// 可见视图 = 未被功能开关关闭的视图；快捷键/命令面板共用此列表
const visibleTabs = computed(() => tabs.filter((t) => !t.feature || features.value[t.feature]))

function applyFeatureSettings(s) {
  features.value = {
    habits: s.feature_habits_enabled !== 'false',
    journal: s.feature_journal_enabled !== 'false',
    goals: s.feature_goals_enabled !== 'false',
    timer: s.feature_timer_enabled !== 'false',
  }
  // 当前视图被关闭时回落到看板
  const current = tabs.find((t) => t.key === view.value)
  if (current?.feature && !features.value[current.feature]) view.value = 'board'
}

// 主题模式：auto（跟随系统 prefers-color-scheme）/ light / dark。
// 默认 auto——首次启动与隔夜系统切换深浅色时都能自动跟随；用户手动选择后
// 转为显式 light/dark，不再被系统覆盖。
// localStorage.theme 兼容旧值：'light'/'dark' 视为显式选择，缺失或异常回落 auto。
const THEME_KEY = 'theme'
const VALID_THEME_MODES = ['auto', 'light', 'dark']
const colorSchemeMql = window.matchMedia?.('(prefers-color-scheme: dark)')
function readThemeMode() {
  const v = localStorage.getItem(THEME_KEY)
  return VALID_THEME_MODES.includes(v) ? v : 'auto'
}
const themeMode = ref(readThemeMode())
// 实际渲染的主题：auto 解析为当前系统值；显式模式直接用其值
const resolvedTheme = computed(
  () => (themeMode.value === 'auto' ? (colorSchemeMql?.matches ? 'dark' : 'light') : themeMode.value)
)
function applyTheme() {
  document.documentElement.setAttribute('data-theme', resolvedTheme.value)
  localStorage.setItem(THEME_KEY, themeMode.value)
}
function setThemeMode(mode) {
  if (!VALID_THEME_MODES.includes(mode)) return
  themeMode.value = mode
  applyTheme()
}
function onColorSchemeChange() {
  // 仅 auto 模式跟随系统；显式 light/dark 不被系统覆盖
  if (themeMode.value === 'auto') applyTheme()
}
applyTheme()
colorSchemeMql?.addEventListener?.('change', onColorSchemeChange)
// 供设置面板「外观」section 切换主题模式（含回到「跟随系统」）
provide('theme-mode', { themeMode, setThemeMode })
const shuttingDown = ref(false)
const settingsOpen = ref(false)

// 应用内确认对话框（替代原生 confirm）：由 App 顶层 provide，任意后代 inject 调用，
// 返回 Promise<boolean>。支持 danger 样式与 Enter/Esc 键盘操作。
const confirmState = ref({
  open: false,
  title: '请确认',
  message: '',
  confirmText: '确定',
  cancelText: '取消',
  danger: false,
})
let confirmResolver = null
function confirmDialog(options) {
  return new Promise((resolve) => {
    confirmResolver = resolve
    confirmState.value = {
      open: true,
      title: '请确认',
      message: '',
      confirmText: '确定',
      cancelText: '取消',
      danger: false,
      ...options,
    }
  })
}
function resolveConfirmDialog(value) {
  confirmState.value.open = false
  if (confirmResolver) {
    confirmResolver(value)
    confirmResolver = null
  }
}
provide('confirm-dialog', confirmDialog)

function toggleTheme() {
  // 顶栏按钮：在浅/深色之间切换；点击即退出「跟随系统」，转为显式选择
  setThemeMode(resolvedTheme.value === 'light' ? 'dark' : 'light')
}

const modalOpen = ref(false)
const editing = ref(null)
// 新建任务的预填数据（目前只有日历月格子双击会传入 due_date）
const createInitial = ref(null)
function openCreate(initial = null) {
  editing.value = null
  createInitial.value = initial
  modalOpen.value = true
}
function openEdit(t) {
  editing.value = t
  modalOpen.value = true
}
function closeModal() {
  modalOpen.value = false
  editing.value = null
  createInitial.value = null
}

async function onSave(payload) {
  try {
    if (editing.value) {
      await update(editing.value.id, payload)
    } else {
      await add(payload)
    }
    closeModal()
  } catch (e) {
    // 保存失败保持 TaskModal 打开，避免用户误以为已保存
    toastService.error(`保存失败：${e.message}`)
  }
}
// 看板右侧栏快速新建：标题已由 BoardView 做自然语言解析，可带日期/时间/优先级/标签
async function onQuickCreate(payload) {
  try {
    await add(payload)
  } catch (e) {
    toastService.error(`创建失败：${e.message}`)
  }
}
async function onDelete(t) {
  const ok = await confirmDialog({
    title: '移入回收站',
    message: `「${t.title}」将移入回收站，可在回收站恢复。`,
    confirmText: '移入回收站',
  })
  if (!ok) return
  await remove(t.id)
  closeModal()
  toastService.undo(`已将「${t.title}」移入回收站`, async () => {
    await restoreTask(t.id)
    await load()
  })
}
async function onStatusChange(task, status) {
  try {
    await update(task.id, { status })
  } catch (e) {
    toastService.error(`状态更新失败：${e.message}`)
  }
}

async function shutdownService() {
  const isDesktop = !!window.electronAPI?.isDesktop
  const ok = await confirmDialog({
    title: isDesktop ? '关闭知时' : '关闭本地服务',
    message: isDesktop
      ? '将退出程序并保存当前数据；下次可从开始菜单或桌面快捷方式重新打开。'
      : '关闭后网页会停止响应；下次双击 start.bat 可重新启动。',
    confirmText: '关闭',
    danger: true,
  })
  if (!ok) return
  shuttingDown.value = true
  try {
    await fetch('/shutdown', { method: 'POST' })
  } catch {
    // 服务退出时连接可能被浏览器判定为中断，这是预期情况。
  }
}

// 全局操作反馈 toast:success / error / info / undo,自动消失。
// 由 App 顶层 provide,任意后代 inject('toast') 调用。
const toast = ref(null)
let toastTimer = null
function showToast(message, { type = 'info', undo = null, duration = 5000 } = {}) {
  toast.value = { message, type, undo }
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (toast.value = null), duration)
}
const toastService = {
  success: (msg, opts = {}) => showToast(msg, { ...opts, type: 'success' }),
  error: (msg, opts = {}) => showToast(msg, { ...opts, type: 'error', duration: 7000 }),
  info: (msg, opts = {}) => showToast(msg, { ...opts, type: 'info' }),
  undo: (msg, undoFn) => showToast(msg, { type: 'info', undo: undoFn, duration: 6000 }),
}
provide('toast', toastService)

// AI 配置可用性（是否有 enabled 的模型配置）：onMounted 时读一次，
// provide 给任务/日记等处的内嵌 AI 按钮做禁用态判断
const aiAvailable = ref(false)
provide('ai-available', aiAvailable)
const toastMeta = {
  success: { icon: 'check', tone: 'mint' },
  error: { icon: 'alert', tone: 'coral' },
  info: { icon: 'bell', tone: 'aqua' },
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

// ---- 每日晨报（幕僚线，默认关闭）----
// 设置键 proactive_briefing_enabled === 'true' 且 localStorage zs-briefing-shown 非今天时，
// 启动后拉取今日晨报；与 StartupReminder 同一天各自只弹一次，晨报排在启动提醒关闭之后。
const BRIEFING_SHOWN_KEY = 'zs-briefing-shown'
const briefingReport = ref(null)
let briefingPending = false
// StartupReminder 的 closed 可能早于本组件 onMounted（当日已节流时同步 emit），
// 记录已发生的事实，prepare 阶段据此直接展示，避免排队丢失
let startupReminderDone = false

function todayKey() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

async function prepareBriefing() {
  if (localStorage.getItem(BRIEFING_SHOWN_KEY) === todayKey()) return
  try {
    const s = await getSettings()
    if (s.proactive_briefing_enabled !== 'true') return
  } catch {
    return
  }
  briefingPending = true
  // 自启主窗口不挂载 StartupReminder（或它已 closed），可直接展示；否则等其 closed 事件排队
  if (isAutoStartHost || startupReminderDone) void showBriefing()
}

function onStartupReminderClosed() {
  startupReminderDone = true
  // 先自动档后晨报；自动档不弹时 showAutopilot 内部会把晨报接上
  if (autopilotPending) void showAutopilot()
  else if (briefingPending) void showBriefing()
}

async function showBriefing() {
  if (!briefingPending || briefingReport.value) return
  briefingPending = false
  try {
    briefingReport.value = await getTodayBriefing()
    localStorage.setItem(BRIEFING_SHOWN_KEY, todayKey())
  } catch {
    // 接口失败静默不展示；不写日期，下次启动可重试
  }
}

// ---- 秘书自动档（默认关闭）----
// 设置键 feature_autopilot_enabled === 'true' 且 localStorage zs-autopilot-shown 非今天时，
// 启动后执行当日自动档；有代办成果才弹卡，排在启动提醒关闭之后、晨报之前。
const AUTOPILOT_SHOWN_KEY = 'zs-autopilot-shown'
const autopilotResult = ref(null)
let autopilotPending = false

async function prepareAutopilot() {
  if (localStorage.getItem(AUTOPILOT_SHOWN_KEY) === todayKey()) return
  try {
    const s = await getSettings()
    if (s.feature_autopilot_enabled !== 'true') return
  } catch {
    return
  }
  autopilotPending = true
  // 自启主窗口不挂载 StartupReminder（或它已 closed），可直接展示；否则等其 closed 事件排队
  if (isAutoStartHost || startupReminderDone) void showAutopilot()
}

async function showAutopilot() {
  if (!autopilotPending || autopilotResult.value) return
  autopilotPending = false
  try {
    const result = await runAutopilot()
    if (result?.ran && result.actions?.length) {
      autopilotResult.value = result
      localStorage.setItem(AUTOPILOT_SHOWN_KEY, todayKey())
      return
    }
    // ran:true 但无代办成果：当天已跑过，记录日期避免重复执行
    if (result?.ran) localStorage.setItem(AUTOPILOT_SHOWN_KEY, todayKey())
  } catch {
    // 接口失败静默不弹；不写日期，下次启动可重试
  }
  // 无可展示内容：晨报在排队则直接接上
  if (briefingPending) void showBriefing()
}

function onAutopilotClosed() {
  autopilotResult.value = null
  // 自动档关后再弹晨报，避免两张卡叠在一起
  if (briefingPending) void showBriefing()
}

// ---- 命令面板（Ctrl/Cmd+K）----
const paletteOpen = ref(false)

// 「新建 xxx」快速创建：面板已按可选注入的解析器产出 payload，这里直接落库
async function onPaletteQuickCreate(payload) {
  try {
    await add(payload)
    toastService.success(`已创建「${payload.title}」`)
  } catch (e) {
    toastService.error(`创建失败：${e.message}`)
  }
}

// 全局快捷键:? 打开帮助;各视图自己的快捷键(如看板 / 与 N)在视图内注册
const shortcutsOpen = ref(false)
const shortcutGroups = [
  {
    name: '全局',
    items: [
      { keys: ['Ctrl/⌘', 'K'], desc: '命令面板' },
      { keys: ['1–9'], desc: '切换九个视图' },
      { keys: ['?'], desc: '打开快捷键帮助' },
      { keys: ['Esc'], desc: '关闭弹层' },
    ],
  },
  {
    name: '看板',
    items: [
      { keys: ['/'], desc: '聚焦搜索框' },
      { keys: ['N'], desc: '新建任务' },
    ],
  },
]
function onGlobalKeydown(e) {
  // Ctrl/Cmd+K 命令面板：输入框聚焦时也要能用，先于输入元素判断
  if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    paletteOpen.value = !paletteOpen.value
    return
  }
  const tag = e.target?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target?.isContentEditable) return
  if (e.key === '?' || (e.shiftKey && e.key === '/')) {
    e.preventDefault()
    shortcutsOpen.value = !shortcutsOpen.value
    return
  }
  // 数字 1-N 切换视图（不带修饰键、不在输入元素内；N = 可见视图数量）
  if (!e.ctrlKey && !e.metaKey && !e.altKey && e.key >= '1' && e.key <= String(visibleTabs.value.length)) {
    const tab = visibleTabs.value[Number(e.key) - 1]
    if (tab) {
      e.preventDefault()
      view.value = tab.key
    }
  }
}
</script>

<template>
  <StartupReminder v-if="isReminderWindow" host-window />
  <AssistantFloat v-else-if="isAssistantFloatWindow" />
  <CaptureView v-else-if="isCaptureWindow" />
  <div v-else class="app">
    <header class="topbar">
      <div class="brand">
        <ArtIcon name="brand" tone="aqua" :size="38" tile label="知时" />
        <span class="brand-text">知时</span>
      </div>

      <nav class="tabs">
        <button
          v-for="tab in visibleTabs"
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
          :class="{ has: count > 0 || unreadCount > 0 }"
          :title="unreadCount > 0 ? `有 ${unreadCount} 条未读通知` : count > 0 ? `有 ${count} 条提醒` : '提醒'"
          @click="panelOpen = true; refreshReminders()"
        >
          <ArtIcon name="bell" tone="aqua" :size="20" label="提醒" />
          <span v-if="unreadCount || count" class="badge">{{ (unreadCount || count) > 99 ? '99+' : (unreadCount || count) }}</span>
        </button>
        <button
          class="ghost icon theme-btn"
          @click="toggleTheme"
          :title="resolvedTheme === 'light' ? '切换深色' : '切换浅色'"
        >
          <ArtIcon
            :name="resolvedTheme === 'light' ? 'moon' : 'sun'"
            tone="aqua"
            :size="20"
            :label="resolvedTheme === 'light' ? '切换深色' : '切换浅色'"
          />
        </button>
        <button class="ghost icon" @click="featuresOpen = true" title="功能管理">
          <ArtIcon name="sort" tone="aqua" :size="20" label="功能管理" />
        </button>
        <button class="ghost settings" @click="settingsOpen = true" title="设置">
          <span>设置</span>
        </button>
        <button class="ghost shutdown" :disabled="shuttingDown" @click="shutdownService">
          <span>{{ shuttingDown ? '正在关闭…' : '关闭服务' }}</span>
        </button>
      </div>
    </header>

    <main class="content">
      <div v-if="loading" class="center muted">
        <AppSpinner size="lg" label="加载中" />
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
          @quick-create="onQuickCreate"
        />
        <OverviewView v-else-if="view === 'overview'" :tasks="tasks" @open="openEdit" />
        <CalendarView v-else-if="view === 'calendar'" :tasks="tasks" @open="openEdit" @create="openCreate" @changed="load" />
        <TimelineView v-else-if="view === 'timeline'" :tasks="tasks" @open="openEdit" @create="openCreate" @changed="load(true)" />
        <HabitsView v-else-if="view === 'habits'" />
        <JournalView v-else-if="view === 'journal'" />
        <GoalsView v-else-if="view === 'goals'" />
        <ReportView v-else-if="view === 'report'" @changed="load" />
        <TrashView v-else-if="view === 'trash'" @changed="load" />
        <LibraryView v-else />
      </Transition>
    </main>

    <AssistantView @changed="load" />

    <TaskModal
      :open="modalOpen"
      :task="editing"
      :initial="createInitial"
      @save="onSave"
      @delete="onDelete"
      @changed="load"
      @close="closeModal"
    />

    <Transition name="pop">
      <RemindersPanel
        v-if="panelOpen"
        :upcoming="upcoming"
        :overdue="overdue"
        :triggered="triggered"
        @open="(t) => { panelOpen = false; openEdit(t) }"
        @close="panelOpen = false"
      />
    </Transition>

    <SettingsPanel :open="settingsOpen" @close="settingsOpen = false" />
    <WelcomeModal :open="welcomeOpen" @done="welcomeOpen = false" />
    <FeaturePanel :open="featuresOpen" @close="featuresOpen = false" @changed="applyFeatureSettings" />
    <FocusTimer v-if="features.timer" />

    <CommandPalette
      :open="paletteOpen"
      :tabs="visibleTabs"
      @close="paletteOpen = false"
      @navigate="(k) => (view = k)"
      @open-settings="settingsOpen = true"
      @toggle-theme="toggleTheme"
      @open-task="openEdit"
      @create-task="openCreate"
      @quick-create="onPaletteQuickCreate"
    />

    <ConfirmDialog
      :open="confirmState.open"
      :title="confirmState.title"
      :message="confirmState.message"
      :confirm-text="confirmState.confirmText"
      :cancel-text="confirmState.cancelText"
      :danger="confirmState.danger"
      @confirm="resolveConfirmDialog(true)"
      @cancel="resolveConfirmDialog(false)"
    />

    <StartupReminder v-if="!isAutoStartHost" @open="openEdit" @closed="onStartupReminderClosed" />

    <AutopilotCard
      v-if="autopilotResult"
      :result="autopilotResult"
      @close="onAutopilotClosed"
    />

    <BriefingCard
      v-if="briefingReport"
      :report="briefingReport"
      @close="briefingReport = null"
    />

    <Transition name="toast">
      <div v-if="toast" :class="['toast', `toast-${toast.type}`]">
        <span class="toast-bar"></span>
        <ArtIcon
          class="toast-icon"
          :name="toastMeta[toast.type]?.icon || 'bell'"
          :tone="toastMeta[toast.type]?.tone || 'aqua'"
          :size="22"
          tile
          label="提示"
        />
        <span class="toast-msg">{{ toast.message }}</span>
        <button v-if="toast.undo" class="toast-undo" @click="undoDelete">撤销</button>
        <button class="ghost toast-close" @click="dismissToast">
          <ArtIcon name="close" tone="pearl" :size="16" label="关闭提示" />
        </button>
      </div>
    </Transition>

    <BaseModal :open="shortcutsOpen" size="sm" label="快捷键帮助" @close="shortcutsOpen = false">
      <div class="shortcuts-body">
        <h3>快捷键</h3>
        <div v-for="group in shortcutGroups" :key="group.name" class="shortcut-group">
          <p class="shortcut-group-name muted">{{ group.name }}</p>
          <div v-for="item in group.items" :key="item.desc" class="shortcut-row">
            <span class="shortcut-keys">
              <kbd v-for="k in item.keys" :key="k">{{ k }}</kbd>
            </span>
            <span class="shortcut-desc">{{ item.desc }}</span>
          </div>
        </div>
      </div>
    </BaseModal>
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
  background: var(--tab-hover);
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
  box-shadow: 0 2px 6px color-mix(in srgb, var(--danger) 50%, transparent);
}
.shutdown {
  color: var(--text-soft);
  white-space: nowrap;
  font-weight: 500;
}

.settings {
  color: var(--text-soft);
  white-space: nowrap;
  font-weight: 500;
}

.content {
  flex: 1;
  padding: 16px clamp(16px, 2vw, 32px) 28px;
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
  background: linear-gradient(180deg, var(--sea-300), var(--accent));
}

.toast-success .toast-bar {
  background: linear-gradient(180deg, var(--foam-300), var(--success));
}

.toast-error .toast-bar {
  background: linear-gradient(180deg, var(--coral-300), var(--danger));
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

.shortcuts-body {
  padding: 26px 24px 20px;
}

.shortcuts-body h3 {
  margin: 0 0 14px;
  font-size: 17px;
  font-weight: 800;
  color: var(--text);
}

.shortcut-group + .shortcut-group {
  margin-top: 14px;
}

.shortcut-group-name {
  margin: 0 0 6px;
  font-weight: 700;
}

.shortcut-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 5px 0;
}

.shortcut-keys {
  min-width: 64px;
  display: inline-flex;
  gap: 4px;
}

.shortcut-keys kbd {
  padding: 3px 8px;
  border-radius: 6px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-bottom-width: 2px;
  font-family: inherit;
  font-size: 12px;
  font-weight: 700;
  color: var(--text);
}

.shortcut-desc {
  font-size: 13px;
  color: var(--text-soft);
}
</style>
