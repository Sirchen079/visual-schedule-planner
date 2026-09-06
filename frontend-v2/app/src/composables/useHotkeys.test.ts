/**
 * 全局快捷键单测——覆盖 keymap.ts「实现约束」点名的守卫规则：
 * 输入聚焦不触发（Esc 与 Ctrl+, 例外）、IME 组字不触发、Esc 分层顺序、
 * g 前缀超时/错键作废、无审批时 y/n 无效；另覆盖键位数据单源与 r 键 route→reload 映射。
 *
 * vitest 环境为 node（无 DOM）：事件用普通对象按 HotkeyEvent 形状构造，
 * 直接调 createHotkeyController 的 handle；端口注册表用 resetHotkeyPortsForTest 隔离用例。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { eventCombo, SHORTCUTS } from '../keymap'
import { registerEscLayer, registerFocusFormControl, resetHotkeyPortsForTest } from './hotkeyPorts'
import { buildReloadMap, createHotkeyController, G_CHORD_MS, type HotkeyControllerDeps } from './useHotkeys'

const BODY = { tagName: 'BODY', isContentEditable: false }
const INPUT = { tagName: 'INPUT', isContentEditable: false }
const TEXTAREA = { tagName: 'TEXTAREA', isContentEditable: false }

type EvOpts = Partial<{ ctrlKey: boolean; altKey: boolean; shiftKey: boolean; isComposing: boolean; target: unknown }>

function ev(key: string, opts: EvOpts = {}): { key: string; ctrlKey: boolean; altKey: boolean; shiftKey: boolean; isComposing: boolean; target: unknown } {
  return { key, ctrlKey: false, altKey: false, shiftKey: false, isComposing: false, target: BODY, ...opts }
}

function makeDeps(): HotkeyControllerDeps {
  return {
    router: { push: vi.fn() },
    routePath: () => '/',
    run: { pendingApproval: null, isActive: false, approve: vi.fn(), reject: vi.fn(), cancel: vi.fn() },
    focus: { isRunning: false, start: vi.fn(), stop: vi.fn() },
    notifications: { panelOpen: false, openPanel: vi.fn(), closePanel: vi.fn() },
    isShortcutsOpen: () => false,
    setShortcutsOpen: vi.fn(),
    focusChatInput: vi.fn(),
    reloadRoute: vi.fn(),
  }
}

/** 把 overlay 开关接到本地变量（Esc 分层用例需要真实状态流转） */
function wireOverlay(deps: HotkeyControllerDeps): { set(v: boolean): void; get(): boolean } {
  let open = false
  deps.isShortcutsOpen = () => open
  deps.setShortcutsOpen = (v) => {
    open = v
  }
  return { set: (v) => (open = v), get: () => open }
}

/** 清空微任务/宏任务队列（startBreak 这类 async 分发落定用） */
const flush = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0))

describe('eventCombo 事件规范化', () => {
  it('单键与修饰键组合', () => {
    expect(eventCombo(ev('g'))).toBe('g')
    expect(eventCombo(ev('F', { shiftKey: true }))).toBe('shift+f')
    expect(eventCombo(ev(',', { ctrlKey: true }))).toBe('ctrl+,')
    expect(eventCombo(ev('r', { ctrlKey: true }))).toBe('ctrl+r') // 不绑定，但会作废 g 窗
    expect(eventCombo(ev('ArrowLeft'))).toBe('arrowleft')
  })

  it('? 双入口与不参与体系的情况', () => {
    expect(eventCombo(ev('?'))).toBe('?')
    expect(eventCombo(ev('/', { shiftKey: true }))).toBe('?') // Shift+/ 兜底
    expect(eventCombo(ev('/', { ctrlKey: true }))).toBe('ctrl+/')
    expect(eventCombo(ev('?'))).not.toBe('')
    expect(eventCombo(ev('/', { shiftKey: true, ctrlKey: true }))).toBe('ctrl+/')
    expect(eventCombo(ev('Shift'))).toBe('') // 纯修饰键：不作废 g 窗
    expect(eventCombo(ev('/', { altKey: true }))).toBe('')
  })
})

describe('键位数据单源（keymap.ts）', () => {
  it('g 前缀路由与 keymap.ts 导航表逐条一致', () => {
    const nav = SHORTCUTS.filter((s) => s.group === 'nav')
    expect(nav.map((s) => s.route)).toEqual([
      '/',
      '/calendar',
      '/board',
      '/timeline',
      '/habits',
      '/journal',
      '/goals',
      '/library',
      '/reports',
      '/trash',
    ])
    expect(nav.map((s) => s.chordKey)).toEqual(['t', 'c', 'b', 'l', 'h', 'j', 'g', 'i', 'r', 'd'])
  })

  it('三个分组齐全且每组非空；速查浮层双入口键共享一条数据', () => {
    const groups = new Set(SHORTCUTS.map((s) => s.group))
    expect([...groups].sort()).toEqual(['calendar', 'global', 'nav'])
    for (const g of ['global', 'nav', 'calendar'] as const) {
      expect(SHORTCUTS.filter((s) => s.group === g).length).toBeGreaterThan(0)
    }
    const overlayToggle = SHORTCUTS.find((s) => s.id === 'shortcuts')
    expect(overlayToggle?.combos).toEqual(['?', 'ctrl+/'])
  })
})

describe('输入守卫（焦点在 input/textarea 时仅 Esc 与 Ctrl+, 放行）', () => {
  let deps: HotkeyControllerDeps
  beforeEach(() => {
    deps = makeDeps()
  })

  it('输入框中的普通键不触发任何动作，g 也不开前缀窗', () => {
    const c = createHotkeyController(deps)
    c.handle(ev('f', { target: INPUT }))
    c.handle(ev('u', { target: TEXTAREA }))
    c.handle(ev('c', { target: INPUT }))
    c.handle(ev('?', { target: INPUT }))
    c.handle(ev('g', { target: INPUT }))
    c.handle(ev('t')) // 窗从未打开，t 不应导航
    expect(deps.focus.start).not.toHaveBeenCalled()
    expect(deps.notifications.openPanel).not.toHaveBeenCalled()
    expect(deps.focusChatInput).not.toHaveBeenCalled()
    expect(deps.setShortcutsOpen).not.toHaveBeenCalled()
    expect(deps.router.push).not.toHaveBeenCalled()
  })

  it('Esc 例外：输入框中仍分层关闭浮层', () => {
    const overlay = wireOverlay(deps)
    overlay.set(true)
    const c = createHotkeyController(deps)
    c.handle(ev('Escape', { target: TEXTAREA }))
    expect(overlay.get()).toBe(false)
  })

  it('Ctrl+, 例外：输入框中也打开设置页', () => {
    const c = createHotkeyController(deps)
    c.handle(ev(',', { ctrlKey: true, target: INPUT }))
    expect(deps.router.push).toHaveBeenCalledWith('/settings')
  })
})

describe('IME 守卫（isComposing 一律不触发）', () => {
  let deps: HotkeyControllerDeps
  beforeEach(() => {
    deps = makeDeps()
  })

  it('组字中的 g 不开前缀窗，随后的 t 不导航', () => {
    const c = createHotkeyController(deps)
    c.handle(ev('g', { isComposing: true }))
    c.handle(ev('t'))
    expect(deps.router.push).not.toHaveBeenCalled()
  })

  it('组字中的 ? 不开速查浮层', () => {
    const c = createHotkeyController(deps)
    c.handle(ev('?', { isComposing: true }))
    expect(deps.setShortcutsOpen).not.toHaveBeenCalled()
  })
})

describe('g 前缀窗（800ms，超时/错键作废）', () => {
  let deps: HotkeyControllerDeps
  beforeEach(() => {
    deps = makeDeps()
    resetHotkeyPortsForTest()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('g t → /；g c → /calendar；g g → /goals', () => {
    const c = createHotkeyController(deps)
    c.handle(ev('g'))
    c.handle(ev('t'))
    expect(deps.router.push).toHaveBeenCalledTimes(1)
    expect(deps.router.push).toHaveBeenLastCalledWith('/')
    c.handle(ev('g'))
    c.handle(ev('c'))
    expect(deps.router.push).toHaveBeenLastCalledWith('/calendar')
    c.handle(ev('g'))
    c.handle(ev('g'))
    expect(deps.router.push).toHaveBeenLastCalledWith('/goals')
  })

  it('g 本身不产生动作；错键作废且吞掉该键自身动作', () => {
    const ctl = { expand: vi.fn(), collapse: vi.fn() }
    registerFocusFormControl(ctl)
    const c = createHotkeyController(deps)
    c.handle(ev('g'))
    expect(deps.router.push).not.toHaveBeenCalled()
    c.handle(ev('f')) // 窗内的 f：作废 g 窗，不展开表单
    expect(ctl.expand).not.toHaveBeenCalled()
    c.handle(ev('x')) // 未知键：窗口已关，静默
    c.handle(ev('t'))
    expect(deps.router.push).not.toHaveBeenCalled() // 窗已被 f 作废，t 不导航
  })

  it('超时 800ms 后第二键作废', async () => {
    vi.useFakeTimers()
    const c = createHotkeyController(deps)
    c.handle(ev('g'))
    await vi.advanceTimersByTimeAsync(G_CHORD_MS + 10)
    c.handle(ev('t'))
    expect(deps.router.push).not.toHaveBeenCalled()
  })

  it('输入框内的按键也会作废 g 窗（且不触发自身动作）', () => {
    const c = createHotkeyController(deps)
    c.handle(ev('g'))
    c.handle(ev('t', { target: INPUT }))
    expect(deps.router.push).not.toHaveBeenCalled()
    c.handle(ev('t')) // 窗已被作废
    expect(deps.router.push).not.toHaveBeenCalled()
  })

  it('窗内的 Esc 按「错键」处理：只作废 g 窗，不分层关闭', () => {
    const overlay = wireOverlay(deps)
    overlay.set(true)
    const c = createHotkeyController(deps)
    c.handle(ev('g'))
    c.handle(ev('Escape'))
    expect(overlay.get()).toBe(true) // 浮层未被关：该 Esc 被序列窗吞掉
  })

  it('dispose 清理 g 窗定时器（不泄漏）', async () => {
    vi.useFakeTimers()
    const c = createHotkeyController(deps)
    c.handle(ev('g'))
    c.dispose()
    await vi.advanceTimersByTimeAsync(G_CHORD_MS + 10)
    c.handle(ev('t'))
    expect(deps.router.push).not.toHaveBeenCalled()
  })
})

describe('Esc 分层（一次只关一层）', () => {
  let deps: HotkeyControllerDeps
  beforeEach(() => {
    deps = makeDeps()
    resetHotkeyPortsForTest()
  })

  it('① 速查浮层 → ② 通知面板 → ④ 取消 run，逐层推进', () => {
    const overlay = wireOverlay(deps)
    overlay.set(true)
    deps.notifications.panelOpen = true
    // 桩要忠实于真实契约：closePanel 会把 panelOpen 落回 false（否则 Esc 永远停在②层）
    deps.notifications.closePanel = vi.fn(() => {
      deps.notifications.panelOpen = false
    })
    deps.run.isActive = true
    const c = createHotkeyController(deps)

    c.handle(ev('Escape'))
    expect(overlay.get()).toBe(false)
    expect(deps.notifications.closePanel).not.toHaveBeenCalled()

    c.handle(ev('Escape'))
    expect(deps.notifications.closePanel).toHaveBeenCalledTimes(1)
    expect(deps.run.cancel).not.toHaveBeenCalled()

    c.handle(ev('Escape'))
    expect(deps.run.cancel).toHaveBeenCalledTimes(1)
  })

  it('② 番茄钟表单先于 ③ 事件详情卡（tier 2 → tier 3），耗尽后才取消 run', () => {
    const closed: string[] = []
    // 忠实于组件契约：真实 FocusBar/EventDetailCard 关闭后（watch 同步观察状态翻转）
    // 会注销自己的分层条目，这里在 close 内同步注销模拟同一行为
    const d2 = registerEscLayer({
      tier: 2,
      close: () => {
        closed.push('focus-form')
        d2()
      },
    })
    const d3 = registerEscLayer({
      tier: 3,
      close: () => {
        closed.push('event-detail')
        d3()
      },
    })
    deps.run.isActive = true
    const c = createHotkeyController(deps)

    c.handle(ev('Escape'))
    expect(closed).toEqual(['focus-form'])
    c.handle(ev('Escape'))
    expect(closed).toEqual(['focus-form', 'event-detail'])
    c.handle(ev('Escape'))
    expect(deps.run.cancel).toHaveBeenCalledTimes(1)
  })

  it('同层多条目时后注册的先关（LIFO）', () => {
    const closed: string[] = []
    const a = registerEscLayer({ tier: 3, close: () => closed.push('a') })
    const b = registerEscLayer({
      tier: 3,
      close: () => {
        closed.push('b')
        b()
      },
    })
    const c = createHotkeyController(deps)
    c.handle(ev('Escape'))
    expect(closed).toEqual(['b'])
    b()
    a()
  })

  it('全部为空且 run 不活跃时 Esc 静默', () => {
    const c = createHotkeyController(deps)
    c.handle(ev('Escape'))
    expect(deps.run.cancel).not.toHaveBeenCalled()
    expect(deps.notifications.closePanel).not.toHaveBeenCalled()
  })
})

describe('条件键（y/n 仅审批挂起时）', () => {
  let deps: HotkeyControllerDeps
  beforeEach(() => {
    deps = makeDeps()
  })

  it('无挂起审批时 y/n 无效', () => {
    const c = createHotkeyController(deps)
    c.handle(ev('y'))
    c.handle(ev('n'))
    expect(deps.run.approve).not.toHaveBeenCalled()
    expect(deps.run.reject).not.toHaveBeenCalled()
  })

  it('审批挂起时 y 批准 / n 拒绝（带 actionId）；已结案的卡不再触发', () => {
    const c = createHotkeyController(deps)
    deps.run.pendingApproval = { actionId: 7, outcome: null }
    c.handle(ev('y'))
    expect(deps.run.approve).toHaveBeenCalledTimes(1)
    expect(deps.run.approve).toHaveBeenCalledWith(7)

    deps.run.pendingApproval = { actionId: 7, outcome: 'approved' } // 已落章（等 resume）
    c.handle(ev('y'))
    expect(deps.run.approve).toHaveBeenCalledTimes(1) // 不重复

    deps.run.pendingApproval = { actionId: 9, outcome: null }
    c.handle(ev('n'))
    expect(deps.run.reject).toHaveBeenCalledTimes(1)
    expect(deps.run.reject).toHaveBeenCalledWith(9)
  })
})

describe('f / Shift+F / u / c / r 接线', () => {
  let deps: HotkeyControllerDeps
  beforeEach(() => {
    deps = makeDeps()
    resetHotkeyPortsForTest()
  })

  it('f：空闲展开开始表单（不直接 start）；进行中结束当前', () => {
    const ctl = { expand: vi.fn(), collapse: vi.fn() }
    registerFocusFormControl(ctl)
    const c = createHotkeyController(deps)

    c.handle(ev('f'))
    expect(ctl.expand).toHaveBeenCalledTimes(1)
    expect(deps.focus.start).not.toHaveBeenCalled()

    deps.focus.isRunning = true
    c.handle(ev('f'))
    expect(deps.focus.stop).toHaveBeenCalledTimes(1)
    expect(ctl.expand).toHaveBeenCalledTimes(1) // 进行中不再展开表单
  })

  it('Shift+F：空闲直接开始休息', async () => {
    const c = createHotkeyController(deps)
    c.handle(ev('F', { shiftKey: true }))
    await flush()
    expect(deps.focus.start).toHaveBeenCalledWith('break')
    expect(deps.focus.stop).not.toHaveBeenCalled()
  })

  it('Shift+F：进行中先 stop 落定再转休息（顺序不倒置）', async () => {
    const order: string[] = []
    deps.focus.isRunning = true
    deps.focus.stop = vi.fn(async () => {
      order.push('stop')
    })
    deps.focus.start = vi.fn(async () => {
      order.push('start')
    })
    const c = createHotkeyController(deps)
    c.handle(ev('F', { shiftKey: true }))
    await flush()
    expect(order).toEqual(['stop', 'start'])
  })

  it('u：空闲开面板、开着关面板（等价于点铃铛）', () => {
    const c = createHotkeyController(deps)
    c.handle(ev('u'))
    expect(deps.notifications.openPanel).toHaveBeenCalledTimes(1)
    deps.notifications.panelOpen = true
    c.handle(ev('u'))
    expect(deps.notifications.closePanel).toHaveBeenCalledTimes(1)
  })

  it('? / Ctrl+/ 双入口开关速查浮层', () => {
    const overlay = wireOverlay(deps)
    const c = createHotkeyController(deps)
    c.handle(ev('?'))
    expect(overlay.get()).toBe(true)
    c.handle(ev('/', { ctrlKey: true }))
    expect(overlay.get()).toBe(false)
  })

  it('c：聚焦对话输入框', () => {
    const c = createHotkeyController(deps)
    c.handle(ev('c'))
    expect(deps.focusChatInput).toHaveBeenCalledTimes(1)
  })

  it('r：按当前路由触发对应域刷新；未映射路由不动作', () => {
    const c = createHotkeyController(deps)
    c.handle(ev('r'))
    expect(deps.reloadRoute).toHaveBeenCalledWith('/')
    deps.routePath = () => '/no-such-view'
    c.handle(ev('r'))
    expect(deps.reloadRoute).toHaveBeenCalledWith('/no-such-view') // 分发照发，映射表内无此路由则无动作
  })
})

describe('r 键 route → reload 映射表', () => {
  function fakeStores() {
    return {
      schedule: { loadToday: vi.fn(), refreshAll: vi.fn(), loadWeek: vi.fn() },
      tasks: { load: vi.fn(), refreshAll: vi.fn() },
      goals: { refreshAll: vi.fn() },
      habits: { refreshAll: vi.fn() },
      journal: { refreshAll: vi.fn() },
      library: { refreshAll: vi.fn(), loadTrash: vi.fn() },
      reports: { load: vi.fn() },
      settings: { loadAll: vi.fn() },
    }
  }

  it('已知路由逐条调对应域 store 的刷新方法', () => {
    const s = fakeStores()
    const map = buildReloadMap(s)
    map['/']()
    expect(s.schedule.loadToday).toHaveBeenCalledTimes(1)
    map['/calendar']()
    expect(s.schedule.refreshAll).toHaveBeenCalledTimes(1)
    map['/board']()
    expect(s.tasks.load).toHaveBeenCalledTimes(1)
    map['/timeline']()
    expect(s.tasks.refreshAll).toHaveBeenCalledTimes(1)
    map['/habits']()
    expect(s.habits.refreshAll).toHaveBeenCalledTimes(1)
    map['/journal']()
    expect(s.journal.refreshAll).toHaveBeenCalledTimes(1)
    map['/goals']()
    expect(s.goals.refreshAll).toHaveBeenCalledTimes(1)
    map['/library']()
    expect(s.library.refreshAll).toHaveBeenCalledTimes(1)
    map['/reports']()
    expect(s.reports.load).toHaveBeenCalledTimes(1)
    map['/trash']()
    expect(s.library.loadTrash).toHaveBeenCalledTimes(1)
    map['/settings']()
    expect(s.settings.loadAll).toHaveBeenCalledTimes(1)
  })

  it('未知路由不在映射表内（不动作）', () => {
    const s = fakeStores()
    const map = buildReloadMap(s)
    expect(map['/no-such-view']).toBeUndefined()
  })
})
