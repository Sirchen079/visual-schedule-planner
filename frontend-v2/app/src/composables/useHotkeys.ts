/**
 * 全局键盘快捷键（M4e）——唯一注册点。
 *
 * 结构：
 * - keymap.ts：键位数据单源（combos/chordKey/id 驱动绑定与速查浮层）。
 * - hotkeyPorts.ts：跨组件端口（Esc 分层条目、番茄钟表单控制、对话输入框聚焦入口）。
 * - createHotkeyController：纯逻辑分发器（不碰 window，单测直接喂事件对象）。
 * - useHotkeys / useViewHotkeys：唯一两处 window keydown 监听——前者在 App 壳层注册
 *   全局键，后者供视图注册自己的域内键（如日历 ←/→/t），挂载注册、卸载注销。
 *
 * 守卫规则实现（docs/KEYMAP.md）：输入守卫（仅 Esc 与 Ctrl+, 例外）→ IME 守卫 →
 * g 前缀 800ms 窗（超时/错键作废）→ Esc 分层（一次只关一层）→ 条件键（y/n 仅审批挂起时）。
 */
import { onUnmounted } from 'vue'
import {
  eventCombo,
  findGlobalDef,
  findNavDefByChord,
  isEditableTarget,
  type HotkeyEvent,
} from '../keymap'
import { getFocusFormControl, topEscLayer } from './hotkeyPorts'
import { useFocusStore } from '../stores/focus'
import { useGoalsStore } from '../stores/goals'
import { useHabitsStore } from '../stores/habits'
import { useJournalStore } from '../stores/journal'
import { useLibraryStore } from '../stores/library'
import { useNotificationsStore } from '../stores/notifications'
import { useReportsStore } from '../stores/reports'
import { useRunStore } from '../stores/run'
import { useScheduleStore } from '../stores/schedule'
import { useSettingsStore } from '../stores/settings'
import { useTasksStore } from '../stores/tasks'

/** g 前缀窗时长（毫秒）：按下 g 后 800ms 内等第二键，超时作废。 */
export const G_CHORD_MS = 800

/** r 键的 route → 域 store 刷新映射（未知路由不动作）。方法名各域不同，集中在此一张表。 */
export interface ReloadStores {
  schedule: { loadToday(): unknown; refreshAll(): unknown }
  tasks: { load(): unknown; refreshAll(): unknown }
  goals: { refreshAll(): unknown }
  habits: { refreshAll(): unknown }
  journal: { refreshAll(): unknown }
  library: { refreshAll(): unknown; loadTrash(): unknown }
  reports: { load(): unknown }
  settings: { loadAll(): unknown }
}

export function buildReloadMap(s: ReloadStores): Record<string, () => void> {
  return {
    '/': () => void s.schedule.loadToday(), // 今日
    '/calendar': () => void s.schedule.refreshAll(), // 日历：今日 + 已加载的周/日/月一次拉齐
    '/board': () => void s.tasks.load(), // 看板
    '/timeline': () => void s.tasks.refreshAll(), // 时间轴：列 + range 一起拉
    '/habits': () => void s.habits.refreshAll(),
    '/journal': () => void s.journal.refreshAll(),
    '/goals': () => void s.goals.refreshAll(),
    '/library': () => void s.library.refreshAll(),
    '/reports': () => void s.reports.load(),
    // 文件回收站走 library 域 store；任务回收站是 TrashView 组件本地态，无 store 级入口
    '/trash': () => void s.library.loadTrash(),
    '/settings': () => void s.settings.loadAll(),
  }
}

/** 分发器依赖（结构最小类型：真实 Pinia store / vue-router 均可结构兼容，单测传桩）。 */
export interface HotkeyControllerDeps {
  router: { push(path: string): unknown }
  /** 当前路由 path（r 键查 reload 映射表用） */
  routePath(): string
  run: {
    pendingApproval: { actionId: number; outcome: string | null } | null
    isActive: boolean
    approve(actionId: number): unknown
    reject(actionId: number): unknown
    cancel(): unknown
  }
  focus: {
    isRunning: boolean
    start(kind: 'focus' | 'break', taskTitle?: string): unknown
    stop(): unknown
  }
  notifications: {
    panelOpen: boolean
    openPanel(): unknown
    closePanel(): unknown
  }
  isShortcutsOpen(): boolean
  setShortcutsOpen(open: boolean): void
  /** 聚焦对话输入框（ChatInput 经 hotkeyPorts 的 provide 注册表登记） */
  focusChatInput(): void
  /** r 键：按当前路由刷新对应域 store（映射表未知路由时不动作） */
  reloadRoute(path: string): void
}

export interface HotkeyController {
  handle(e: HotkeyEvent): void
  /** 清理 g 前缀窗定时器（壳层卸载时调用，绝不泄漏）。 */
  dispose(): void
}

/**
 * 创建全局键分发器。不持有任何 DOM 引用：事件以 HotkeyEvent 形状传入，
 * 便于单测用普通对象模拟（vitest 环境为 node，无 DOM）。
 */
export function createHotkeyController(deps: HotkeyControllerDeps): HotkeyController {
  let chordTimer: ReturnType<typeof setTimeout> | null = null
  const clearChord = (): void => {
    if (chordTimer !== null) {
      clearTimeout(chordTimer)
      chordTimer = null
    }
  }

  /** Esc 分层（KEYMAP 守卫 4）：从内到外一次只关一层。 */
  function handleEsc(): void {
    if (deps.isShortcutsOpen()) {
      deps.setShortcutsOpen(false) // ① 速查浮层
      return
    }
    if (deps.notifications.panelOpen) {
      deps.notifications.closePanel() // ② 通知面板
      return
    }
    const layer = topEscLayer() // ② 番茄钟表单 / ③ 事件详情卡等域内浮层
    if (layer) {
      layer.close()
      return
    }
    if (deps.run.isActive) void deps.run.cancel() // ④ 取消进行中的 AI run
  }

  /** 按数据单源里的 id 分发动作；条件键（y/n/f/Shift+F）在此落守卫。 */
  function dispatchDef(id: string): void {
    switch (id) {
      case 'shortcuts':
        deps.setShortcutsOpen(!deps.isShortcutsOpen())
        break
      case 'compose':
        deps.focusChatInput()
        break
      case 'approve': {
        const p = deps.run.pendingApproval // 守卫 5：仅审批卡挂起时
        if (p && p.outcome === null) void deps.run.approve(p.actionId)
        break
      }
      case 'deny': {
        const p = deps.run.pendingApproval
        if (p && p.outcome === null) void deps.run.reject(p.actionId)
        break
      }
      case 'focus-toggle':
        // 「等价于点浮动条主按钮」：空闲展开开始表单（不直接 start）；进行中结束当前
        if (deps.focus.isRunning) void deps.focus.stop()
        else getFocusFormControl()?.expand()
        break
      case 'focus-break':
        void startBreak()
        break
      case 'notifications':
        if (deps.notifications.panelOpen) deps.notifications.closePanel()
        else void deps.notifications.openPanel()
        break
      case 'reload':
        deps.reloadRoute(deps.routePath())
        break
      case 'open-settings':
        void deps.router.push('/settings')
        break
    }
  }

  /** Shift+F：进行中=结束并转休息。必须等 stop 落定再 start（start 有 current 非空守卫）。 */
  async function startBreak(): Promise<void> {
    if (deps.focus.isRunning) await deps.focus.stop()
    await deps.focus.start('break')
  }

  function handle(e: HotkeyEvent): void {
    // 守卫 2：IME 组字中一律不触发（'?'、'g' 等都是合法拼音成分）；也不作废 g 窗，由超时回收
    if (e.isComposing) return
    const combo = eventCombo(e)
    if (combo === '') return // 纯修饰键单按 / Alt 组合等：不动作、不作废 g 窗

    // g 前缀第二键（守卫 3）：窗内任意键都结算窗口——命中 chord 即导航；其余按「错键作废」
    // 吞掉（不触发该键自身动作，与 GitHub 式序列键一致）。
    if (chordTimer !== null) {
      clearChord()
      if (!editableAt(e)) {
        const chord = findNavDefByChord(combo)
        if (chord?.route) {
          e.preventDefault?.()
          void deps.router.push(chord.route)
        }
      }
      return
    }

    // 守卫 1：输入焦点内仅放行 Esc 与 Ctrl+,（守卫 1 的两个例外键）
    if (editableAt(e) && combo !== 'esc' && combo !== 'ctrl+,') return

    if (combo === 'esc') {
      handleEsc()
      return
    }

    if (combo === 'g') {
      // g 本身不产生动作，只开 800ms 等第二键
      clearChord()
      chordTimer = setTimeout(() => {
        chordTimer = null
      }, G_CHORD_MS)
      return
    }

    const def = findGlobalDef(combo)
    if (!def) return
    if (combo !== 'esc') e.preventDefault?.() // Esc 交给浏览器（退出全屏等系统行为不拦）
    dispatchDef(def.id)
  }

  function editableAt(e: HotkeyEvent): boolean {
    return isEditableTarget(e.target)
  }

  return {
    handle,
    dispose: clearChord,
  }
}

/** App 壳层接线选项 */
export interface UseHotkeysOptions {
  router: { push(path: string): unknown }
  routePath(): string
  isShortcutsOpen(): boolean
  setShortcutsOpen(open: boolean): void
  focusChatInput(): void
}

/**
 * 全局键唯一注册点：App.vue onMounted 生命周期内调用，注册 window keydown，
 * onUnmounted 注销监听并清理 g 窗定时器（绝不泄漏）。
 */
export function useHotkeys(options: UseHotkeysOptions): void {
  const run = useRunStore()
  const focus = useFocusStore()
  const notifications = useNotificationsStore()
  const reloadMap = buildReloadMap({
    schedule: useScheduleStore(),
    tasks: useTasksStore(),
    goals: useGoalsStore(),
    habits: useHabitsStore(),
    journal: useJournalStore(),
    library: useLibraryStore(),
    reports: useReportsStore(),
    settings: useSettingsStore(),
  })
  const controller = createHotkeyController({
    router: options.router,
    routePath: options.routePath,
    run,
    focus,
    notifications,
    isShortcutsOpen: options.isShortcutsOpen,
    setShortcutsOpen: options.setShortcutsOpen,
    focusChatInput: options.focusChatInput,
    reloadRoute: (path) => reloadMap[path]?.(),
  })
  const onKeyDown = (e: KeyboardEvent): void => controller.handle(e)
  window.addEventListener('keydown', onKeyDown)
  onUnmounted(() => {
    window.removeEventListener('keydown', onKeyDown)
    controller.dispose()
  })
}

/**
 * 视图专属键注册（如日历 ←/→/t）：仅当前视图挂载期间生效，卸载即注销——
 * router 离开视图后绝不再触发。沿用同一套 eventCombo / 输入守卫 / IME 守卫。
 * 命中即 preventDefault（如方向键默认滚动）。
 */
export function useViewHotkeys(combos: string[], run: (combo: string) => void): void {
  const onKeyDown = (e: KeyboardEvent): void => {
    if (e.isComposing) return
    const combo = eventCombo(e)
    if (!combo || !combos.includes(combo)) return
    if (isEditableTarget(e.target)) return
    e.preventDefault()
    run(combo)
  }
  window.addEventListener('keydown', onKeyDown)
  onUnmounted(() => window.removeEventListener('keydown', onKeyDown))
}
