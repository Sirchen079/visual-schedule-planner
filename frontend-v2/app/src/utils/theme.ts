/**
 * 外观主题（'dark' | 'light'）读写助手，main.ts 首帧引导 / SettingsView 切换 /
 * settings store 跨端口调和三处共用。
 * re #065（re gpt6astra #063 major）：桌面壳每次随机端口，localStorage 按 origin（含端口）
 * 隔离 → 主题的跨端口权威源是 8421 后端 settings KV 的 ui.theme 键；localStorage 只作
 * 本 origin 的首帧秒刷缓存，挂载后由 store.reconcileTheme() 以远端为准调和。
 */
export type ThemeName = 'dark' | 'light'

export const THEME_KEY = 'zhishi-theme'

/** 读本 origin 首帧缓存；读不到存储（隐私模式等）按缺省暗色走。 */
export function readLocalTheme(): ThemeName {
  try {
    return localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

/** 当前生效主题（以 documentElement 为准，main.ts 已引导）。 */
export function currentTheme(): ThemeName {
  return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark'
}

/**
 * 落到 documentElement + localStorage。dark 也显式设置，让 [data-theme='light']
 * 选择器语义与运行时状态始终一致；写不进存储时当前会话内仍生效。
 */
export function applyTheme(t: ThemeName): void {
  document.documentElement.dataset.theme = t
  try {
    localStorage.setItem(THEME_KEY, t)
  } catch {
    // 隐私模式等：当前会话内仍生效
  }
}
