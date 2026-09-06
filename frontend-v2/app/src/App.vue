<script setup lang="ts">
/**
 * 应用壳（视觉基准：design-demos/final-shell.html）：
 * ① 60px 图标导航轨（B 的骨架 × C 的暖暗温度）② AI 对话列（常驻主角，570px）
 * ③ 标签内容区（RouterView）。图标为内联 SVG（AppIcon），无 emoji。
 */
import { computed, nextTick, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import AppIcon, { type IconName } from './components/AppIcon.vue'
import ProjectLink from './components/ProjectLink.vue'
import ChatPanel from './components/chat/ChatPanel.vue'
import NotificationBell from './components/shell/NotificationBell.vue'
import FocusBar from './components/shell/FocusBar.vue'
import ShortcutsOverlay from './components/shell/ShortcutsOverlay.vue'
import { useHotkeys } from './composables/useHotkeys'
import { CHAT_FOCUS_KEY, registerEscLayer, type ChatFocusRegistry } from './composables/hotkeyPorts'
import { useConversationStore } from './stores/conversation'
import { useRunStore } from './stores/run'
import { useScheduleStore } from './stores/schedule'
import { useNotificationsStore } from './stores/notifications'
import { useFocusStore } from './stores/focus'
import { useTasksStore } from './stores/tasks'
import { useGoalsStore } from './stores/goals'
import { useHabitsStore } from './stores/habits'
import { useJournalStore } from './stores/journal'
import { useLibraryStore } from './stores/library'
import { routes } from './router'
import type { NavMeta } from './router'

const ICON_BY_ROUTE: Record<string, IconName> = {
  today: 'today',
  inbox: 'inbox',
  research: 'research',
  calendar: 'calendar',
  board: 'board',
  timeline: 'timeline',
  habits: 'habits',
  journal: 'journal',
  ledger: 'ledger',
  goals: 'goals',
  library: 'library',
  reports: 'reports',
  trash: 'trash',
  settings: 'settings',
}

const navMeta = (r: (typeof routes)[number]): NavMeta => (r.meta as unknown as NavMeta | undefined) ?? { title: '', group: 'main' }
const navMain = computed(() => routes.filter((r) => navMeta(r).group === 'main'))
const navAux = computed(() => routes.filter((r) => navMeta(r).group === 'aux'))

const route = useRoute()
/** router 未 ready 时 route.name 为 undefined（find 结果可能为空），需容错。 */
const headTitle = computed(() => {
  const current = routes.find((r) => r.name === route.name)
  return current ? navMeta(current).title : '知时'
})

/** 内容头：今日页挂日期，其余挂一句话说明。 */
const localNow = ref(new Date())
let clockTimer: ReturnType<typeof setInterval> | null = null
function refreshLocalClock() { localNow.value = new Date() }
const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六']
const headNote = computed(() => {
  const now = localNow.value
  return `${now.getMonth() + 1} 月 ${now.getDate()} 日 星期${WEEKDAYS[now.getDay()]}`
})

const clock = computed(() => {
  const n = localNow.value
  return `${String(n.getHours()).padStart(2, '0')}:${String(n.getMinutes()).padStart(2, '0')}`
})

const conversationStore = useConversationStore()
const notificationsStore = useNotificationsStore()
const focusStore = useFocusStore()
onMounted(() => {
  refreshLocalClock()
  clockTimer = setInterval(refreshLocalClock, 1000)
  window.addEventListener('focus', refreshLocalClock)
  document.addEventListener('visibilitychange', refreshLocalClock)
  window.addEventListener('zhishi:tasks-changed', refreshDesktopTasks)
  window.addEventListener('focus', refreshDesktopTasks)
  void conversationStore.refresh()
  void scheduleStore.loadToday() // 预热今日视图（默认落地页）
  notificationsStore.startPolling() // 通知未读数 30s 轮询（页面隐藏时暂停）
  void focusStore.init() // 恢复进行中的番茄钟 + 今日累计
  narrowMQ.addEventListener('change', onNarrowMQChange) // 断点穿越复位抽屉态
})
onUnmounted(() => {
  if (clockTimer !== null) clearInterval(clockTimer)
  window.removeEventListener('focus', refreshLocalClock)
  document.removeEventListener('visibilitychange', refreshLocalClock)
  window.removeEventListener('zhishi:tasks-changed', refreshDesktopTasks)
  window.removeEventListener('focus', refreshDesktopTasks)
  // 绝不泄漏 interval：轮询与秒针都是壳层级定时器，随壳层卸载一并停掉
  notificationsStore.stopPolling()
  focusStore.dispose()
  narrowMQ.removeEventListener('change', onNarrowMQChange)
  deregChatDrawerEsc?.() // 卸载时 watcher 已停，Esc 分层条目须手动注销
  deregChatDrawerEsc = null
})

const runStore = useRunStore()
const scheduleStore = useScheduleStore()
const tasksStore = useTasksStore()
const goalsStore = useGoalsStore()
const habitsStore = useHabitsStore()
const journalStore = useJournalStore()
const libraryStore = useLibraryStore()

watch(() => localNow.value.toDateString(), () => { void scheduleStore.loadToday() })

function refreshDesktopTasks() {
  void scheduleStore.refreshAll()
  void tasksStore.refreshAll()
}

/* ---- 全局键盘快捷键（M4e）：单一注册点在 useHotkeys 内，App 只负责接线与浮层开关 ---- */
const router = useRouter()
const shortcutsOpen = ref(false)

/**
 * c 键聚焦对话输入框：ChatInput 挂载时向本注册表登记 textarea 聚焦函数。
 * 选型 provide/inject 而非 window CustomEvent：类型安全、无全局事件副作用、
 * 单测可直调注册函数；而非 props 透传：ChatInput 深藏在 ChatPanel 内，穿层污染中间组件。
 */
const chatFocusFn = ref<(() => void) | null>(null)
provide(CHAT_FOCUS_KEY, {
  register(fn) {
    chatFocusFn.value = fn
    return () => {
      if (chatFocusFn.value === fn) chatFocusFn.value = null
    }
  },
} satisfies ChatFocusRegistry)

/* ---- 窄屏（<1000px）对话抽屉 ----
 * ≥1000px：对话列常驻 570px（现状，零改动）；<1000px：ChatPanel 不占 flex 位，
 * 内容区占满导航轨以外全部宽度，对话列由 isNarrow + chatDrawerOpen 两状态驱动成
 * fixed 抽屉（定位/层谱样式在 ChatPanel 的 .chat-as-drawer，开关入口在导航轨）。
 * 断点穿越即复位抽屉态：宽屏无抽屉概念，从宽拉窄时默认关。 */
const narrowMQ = window.matchMedia('(max-width: 999px)')
const isNarrow = ref(narrowMQ.matches)
const chatDrawerOpen = ref(false)
const onNarrowMQChange = (e: MediaQueryListEvent): void => {
  isNarrow.value = e.matches
  chatDrawerOpen.value = false
}

/** 抽屉开着才注册 tier 2 的 Esc 分层条目（守卫 4 第②层），关了即注销（照 FocusBar 模式）。 */
let deregChatDrawerEsc: (() => void) | null = null
watch(
  () => isNarrow.value && chatDrawerOpen.value,
  (open) => {
    if (open) {
      deregChatDrawerEsc = registerEscLayer({ tier: 2, close: () => (chatDrawerOpen.value = false) })
    } else {
      deregChatDrawerEsc?.()
      deregChatDrawerEsc = null
    }
  },
)

/** 传给 ChatPanel 的抽屉态 class（fallthrough 合并到 .chat 根元素；宽屏不加任何 class）。 */
const chatPanelClass = computed(() => {
  if (!isNarrow.value) return undefined
  return chatDrawerOpen.value ? 'chat-as-drawer' : 'chat-drawer-hidden'
})

useHotkeys({
  router,
  routePath: () => route.path,
  isShortcutsOpen: () => shortcutsOpen.value,
  setShortcutsOpen: (open) => {
    shortcutsOpen.value = open
  },
  focusChatInput: () => {
    // 窄屏且抽屉关着：先开抽屉再聚焦（display:none 下 textarea 无法聚焦，
    // 且 Vue 的 class 切换在 nextTick 落 DOM，须等一拍）；宽屏/已开则直聚焦（现状不变）。
    if (!isNarrow.value || chatDrawerOpen.value) {
      chatFocusFn.value?.()
      return
    }
    chatDrawerOpen.value = true
    void nextTick(() => chatFocusFn.value?.())
  },
})

/**
 * run done（唯一权威流结束）后自动刷新全部已加载数据域（M3 扩展）：
 * AI 写操作（create_event/create_task/check_in_habit/write_journal/update_kr_progress/
 * bulk_delete_files 等裸名工具）落库发生在 done 之前，因此 phase 收敛到 completed
 * （或 cancelled——保守覆盖）时逐域拉一次；各 store 只刷「已加载过的部分」，
 * 用户没进过的视图不白发请求。今日/日历/看板/时间轴/习惯/日记/目标/资料库即见新数据。
 * awaiting_approval 不刷新：审批未决尚无写操作（幽灵块由 run store 响应式投影）。
 */
watch(
  () => runStore.phase,
  (p, prev) => {
    if (!prev || (p !== 'completed' && p !== 'cancelled')) return
    void scheduleStore.refreshAll()
    void tasksStore.refreshAll()
    void goalsStore.refreshAll()
    void habitsStore.refreshAll()
    void journalStore.refreshAll()
    void libraryStore.refreshAll()
  },
)
</script>

<template>
  <div class="app-shell">
    <!-- ① 图标导航轨 -->
    <nav class="rail" aria-label="主导航">
      <div class="logo" title="知时">
        <img src="/favicon.svg" width="34" height="34" alt="知时">
      </div>
      <div class="brandname">知时</div>

      <!-- 窄屏（<1000px）对话抽屉开关：宽屏对话列常驻，本按钮 display:none，导航轨像素级不变 -->
      <button
        class="nav-ic nav-chat-toggle"
        :class="{ 'drawer-active': isNarrow && chatDrawerOpen }"
        title="对话"
        aria-label="对话"
        :aria-expanded="isNarrow ? chatDrawerOpen : undefined"
        @click="chatDrawerOpen = !chatDrawerOpen"
      >
        <AppIcon name="chat" />
      </button>

      <div class="nav-group">
        <RouterLink
          v-for="r in navMain"
          :key="r.name"
          :to="r.path"
          class="nav-ic"
          :title="navMeta(r).title"
          :aria-label="navMeta(r).title"
        >
          <AppIcon :name="ICON_BY_ROUTE[String(r.name)] ?? 'today'" />
        </RouterLink>
      </div>

      <div class="spacer" />
      <hr />
      <div class="nav-group">
        <RouterLink
          v-for="r in navAux"
          :key="r.name"
          :to="r.path"
          class="nav-ic"
          :title="navMeta(r).title"
          :aria-label="navMeta(r).title"
        >
          <AppIcon :name="ICON_BY_ROUTE[String(r.name)] ?? 'reports'" />
          <span v-if="r.name === 'settings'" class="nav-settings-label">设置</span>
        </RouterLink>
      </div>
    </nav>

    <!-- ② AI 对话列：≥1000px 常驻；<1000px 为抽屉（class 驱动，见 ChatPanel），开启时铺背衬 -->
    <div
      v-if="isNarrow && chatDrawerOpen"
      class="chat-drawer-backdrop"
      aria-hidden="true"
      @click="chatDrawerOpen = false"
    />
    <ChatPanel :class="chatPanelClass" />

    <!-- ③ 标签内容区 -->
    <main class="content">
      <header class="content-head">
        <span class="ch-title">{{ headTitle }}</span>
        <span class="ch-note">{{ headNote }}</span>
        <div class="ch-right">
          <div id="head-actions" class="head-actions" />
          <ProjectLink />
          <NotificationBell />
          <span class="clock">{{ clock }}</span>
          <span class="chip-amber" title="记录保存在本机；使用外部 AI 时，相关消息和附件会发送给所配置的模型服务。">本地保存 · AI 按需连接</span>
        </div>
      </header>
      <div class="content-body">
        <RouterView />
      </div>
    </main>

    <!-- 番茄钟浮动条：壳层右下 fixed，全页面可见 -->
    <FocusBar />

    <!-- 快捷键速查浮层：? / Ctrl+/ 开关，Esc 或点击背板关闭（均由 useHotkeys 分发） -->
    <ShortcutsOverlay :open="shortcutsOpen" @close="shortcutsOpen = false" />
  </div>
</template>

<style scoped>
.nav-ic:has(.nav-settings-label) { flex-direction:column; gap:2px; height:48px; }
.nav-settings-label { font-size:10px; line-height:12px; }
.app-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

/* ① 导航轨 */
.rail {
  width: var(--rail-w);
  height: 100%;
  flex: none;
  background: var(--bg-rail);
  border-right: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 0 14px;
}
.logo {
  width: 34px;
  height: 34px;
  flex: none;
  overflow: hidden;
  border-radius: 8px;
}
.logo svg {
  width: 34px;
  height: 34px;
}
.brandname {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.18em;
  color: var(--ink-2);
  margin: 6px 0 14px;
  line-height: 1;
  text-indent: 0.18em;
}
.nav-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.rail hr {
  width: 26px;
  border: none;
  border-top: 1px solid var(--line-2);
  margin: 12px 0 10px;
}
.nav-ic {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ink-3);
}
.nav-ic:hover {
  background: var(--nav-hover-bg);
  color: var(--ink-2);
}
.nav-ic.router-link-active {
  background: var(--nav-active-bg);
  color: var(--amber-soft);
}
/* 窄屏抽屉开关的选中态：沿用导航轨 active 体系（amber wash + 琥珀图标） */
.nav-chat-toggle.drawer-active {
  background: var(--nav-active-bg);
  color: var(--amber-soft);
}
/* 仅 <1000px 显示（覆盖 .nav-ic 的 display:flex）；宽屏隐藏保证现状零回归 */
.nav-chat-toggle {
  display: none;
  margin-bottom: 10px;
}
.spacer {
  flex: 1;
}

/* ③ 内容区 */
.content {
  flex: 1;
  min-width: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--app-glow), var(--bg-app);
}
/* 内容头：单行 46px（min-height 兜底 + 上下 5px 内边距，单行时与旧版 height:46 像素一致：
 * 内容盒 36px 居中，控件顶点不变）；日历等控件多的路由在窄幅下整体折行到第二行
 * （align-items:center + row-gap 保证第二行行高与间距对齐），绝不让文本竖排折行。 */
.content-head {
  min-height: 46px;
  flex: none;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
  padding: 5px 20px;
  border-bottom: 1px solid var(--line);
  background: var(--head-bar-bg);
}
.ch-title {
  font-family: var(--serif);
  font-size: 17px;
  font-weight: 600;
  letter-spacing: 0.04em;
  white-space: nowrap;
}
.ch-note {
  font-size: 12.5px;
  color: var(--ink-3);
  margin-left: 4px;
  padding-left: 12px;
  border-left: 1px solid var(--line-2);
  white-space: nowrap;
}
.ch-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 4px 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 4px 10px;
  flex-wrap: wrap;
  /* 不设 justify-content：保持 flex-start，避免改动绝对定位子元素的静态位置
   * （如资料库的 1×1 hidden-input）；折行续行自然左对齐。 */
}
.clock {
  font-family: var(--serif);
  font-size: 15px;
  color: var(--ink-2);
  letter-spacing: 0.06em;
}
.chip-amber {
  font-size: 12px;
  font-weight: 600;
  color: var(--amber-soft);
  border: 1px solid var(--amber-border);
  background: var(--amber-wash-strong);
  border-radius: var(--radius-pill);
  padding: 4px 11px;
  white-space: nowrap;
}
.content-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
}

/* ---- 窄屏对话抽屉 ----
 * 背衬从导航轨右缘铺起：轨道保持可点（再点「对话」即收起、可直接切视图）。
 * 层谱（全壳升序）：内容区(auto) < 番茄钟条(25) < 会话列表(30) < 背衬(35) <
 * 抽屉(36) < 通知面板(40/41) < 事件详情卡(60) < 速查浮层(70)。
 */
.chat-drawer-backdrop {
  position: fixed;
  top: 0;
  bottom: 0;
  left: var(--rail-w);
  right: 0;
  background: var(--overlay-backdrop);
  z-index: 35;
}
@media (max-width: 999px) {
  .nav-chat-toggle {
    display: flex;
  }
}
/* 内容头防挤（次要优化）：窄幅下本地优先 chip 让位，时钟与铃铛保留 */
@media (max-width: 1099.98px) {
  .chip-amber {
    display: none;
  }
}
</style>
