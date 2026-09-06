/**
 * 全局快捷键定义，同时供事件处理和快捷键帮助使用。
 */

/** 分组：全局 / 导航（g 前缀）/ 日历视图（仅 /calendar 生效，由视图注册注销） */
export type ShortcutGroup = 'global' | 'nav' | 'calendar'

export interface ShortcutDef {
  /** 分发用稳定 id（useHotkeys 的 dispatch switch 只认 id，不重复写字符串键位） */
  id: string
  group: ShortcutGroup
  /** 展示文案（浮层 kbd 内原样渲染），如 '? / Ctrl+/'、'g t'、'Shift+F' */
  keys: string
  /** 说明文案（浮层右列） */
  desc: string
  /** 命中的 combo 列表（速查浮层的双入口键共享一条数据，如 ['?', 'ctrl+/']） */
  combos?: string[]
  /** g 前缀第二键（仅 nav 组；小写单字母） */
  chordKey?: string
  /** nav 组目标路由 */
  route?: string
}

export const GROUP_ORDER: ShortcutGroup[] = ['global', 'nav', 'calendar']

export const GROUP_LABELS: Record<ShortcutGroup, string> = {
  global: '全局',
  nav: '导航（g 前缀）',
  calendar: '日历视图（仅 /calendar）',
}

export const SHORTCUTS: ShortcutDef[] = [
  // ---- 全局 ----
  {
    id: 'shortcuts',
    group: 'global',
    keys: '? / Ctrl+/',
    desc: '开关「快捷键速查」浮层',
    combos: ['?', 'ctrl+/'],
  },
  { id: 'compose', group: 'global', keys: 'c', desc: '聚焦对话输入框（光标落到 ChatInput）', combos: ['c'] },
  {
    id: 'escape',
    group: 'global',
    keys: 'Esc',
    desc: '分层关闭：速查浮层 → 通知面板/番茄钟表单 → 域内浮层 → 取消 run',
    combos: ['esc'],
  },
  { id: 'approve', group: 'global', keys: 'y', desc: '批准挂起的审批动作（仅审批卡挂起时）', combos: ['y'] },
  { id: 'deny', group: 'global', keys: 'n', desc: '拒绝挂起的审批动作（仅审批卡挂起时）', combos: ['n'] },
  {
    id: 'focus-toggle',
    group: 'global',
    keys: 'f',
    desc: '番茄钟：空闲→展开开始表单；进行中→结束当前',
    combos: ['f'],
  },
  {
    id: 'focus-break',
    group: 'global',
    keys: 'Shift+F',
    desc: '开始一段休息（进行中为结束并转休息）',
    combos: ['shift+f'],
  },
  { id: 'notifications', group: 'global', keys: 'u', desc: '开关通知面板（等价于点铃铛）', combos: ['u'] },
  { id: 'reload', group: 'global', keys: 'r', desc: '刷新当前视图数据（调当前域 store 的 load）', combos: ['r'] },
  { id: 'open-settings', group: 'global', keys: 'Ctrl+,', desc: '打开设置页（桌面应用惯例，输入框中也生效）', combos: ['ctrl+,'] },
  // ---- 导航（g 前缀）----
  { id: 'nav-today', group: 'nav', keys: 'g t', desc: '今日', chordKey: 't', route: '/' },
  { id: 'nav-calendar', group: 'nav', keys: 'g c', desc: '日历', chordKey: 'c', route: '/calendar' },
  { id: 'nav-board', group: 'nav', keys: 'g b', desc: '看板', chordKey: 'b', route: '/board' },
  { id: 'nav-timeline', group: 'nav', keys: 'g l', desc: '时间轴', chordKey: 'l', route: '/timeline' },
  { id: 'nav-habits', group: 'nav', keys: 'g h', desc: '习惯', chordKey: 'h', route: '/habits' },
  { id: 'nav-journal', group: 'nav', keys: 'g j', desc: '日记', chordKey: 'j', route: '/journal' },
  { id: 'nav-goals', group: 'nav', keys: 'g g', desc: '目标', chordKey: 'g', route: '/goals' },
  { id: 'nav-library', group: 'nav', keys: 'g i', desc: '资料库', chordKey: 'i', route: '/library' },
  { id: 'nav-reports', group: 'nav', keys: 'g r', desc: '报表', chordKey: 'r', route: '/reports' },
  { id: 'nav-trash', group: 'nav', keys: 'g d', desc: '回收站', chordKey: 'd', route: '/trash' },
  // ---- 日历视图（仅 /calendar；CalendarView 经 useViewHotkeys 注册/注销）----
  { id: 'cal-prev', group: 'calendar', keys: '←', desc: '上一周', combos: ['arrowleft'] },
  { id: 'cal-next', group: 'calendar', keys: '→', desc: '下一周', combos: ['arrowright'] },
  { id: 'cal-today', group: 'calendar', keys: 't', desc: '回到本周', combos: ['t'] },
]

/** 键盘事件的最小形状（真实 KeyboardEvent 结构兼容，单测可传普通对象） */
export interface HotkeyEvent {
  key: string
  ctrlKey?: boolean
  altKey?: boolean
  shiftKey?: boolean
  isComposing?: boolean
  target?: unknown
  /** 真实 DOM 事件才有：命中已绑定键（Esc 除外）时阻止浏览器默认行为 */
  preventDefault?: () => void
}

/**
 * 事件 → 规范 combo（纯函数）。返回 '' 表示不参与快捷键体系：
 * Alt 组合、Esc/Ctrl+Esc、裸 '/'、纯修饰键单按（Shift/Ctrl/Alt/Meta 等）。
 * 纯修饰键必须中性：物理按键序列里 Shift+F 会先落下 Shift 的 keydown，
 * 若它作废 g 窗，任何带 Shift 的第二键都永远到不了 chord 判定。
 */
const MODIFIER_ONLY = new Set(['shift', 'control', 'alt', 'meta', 'capslock'])

export function eventCombo(e: HotkeyEvent): string {
  if (e.altKey) return ''
  const ctrl = e.ctrlKey === true
  const key = e.key
  if (key === 'Escape') return ctrl ? '' : 'esc'
  if (key === '?') return ctrl ? '' : '?'
  if (key === '/') {
    if (ctrl) return 'ctrl+/'
    return e.shiftKey === true ? '?' : '' // Shift+/ 在多数布局已是 '?'，此处兜底
  }
  if (key === ',') return ctrl ? 'ctrl+,' : ''
  if (MODIFIER_ONLY.has(key.toLowerCase())) return ''
  if (key.length === 1) {
    const lower = key.toLowerCase()
    if (ctrl) return `ctrl+${lower}` // ctrl+字母/数字：不绑定（让位浏览器/系统惯例），仅作废 g 窗
    if (e.shiftKey === true && /[a-z]/.test(lower)) return `shift+${lower}`
    return lower
  }
  return key.toLowerCase() // 命名键（Enter/Tab/ArrowLeft…）：规范化小写，可作废 g 窗但不绑定
}

/** 输入守卫（快捷键守卫 1）：焦点在这些目标上时全局键一律不触发（Esc 与 Ctrl+, 例外放行）。 */
export function isEditableTarget(target: unknown): boolean {
  const el = target as { tagName?: unknown; isContentEditable?: unknown } | null | undefined
  if (!el || typeof el !== 'object') return false
  if (el.isContentEditable === true) return true
  const tag = typeof el.tagName === 'string' ? el.tagName.toUpperCase() : ''
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
}

/** 按 combo 查全局键定义（查不到 = 该键未绑定，静默）。 */
export function findGlobalDef(combo: string): ShortcutDef | undefined {
  return SHORTCUTS.find((s) => s.group === 'global' && s.combos?.includes(combo))
}

/** 按 g 前缀第二键查导航定义（仅接受 eventCombo 输出的裸小写字母）。 */
export function findNavDefByChord(combo: string): ShortcutDef | undefined {
  return SHORTCUTS.find((s) => s.group === 'nav' && s.chordKey === combo)
}
