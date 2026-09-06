/**
 * 主题读取、应用与持久化。
 * 后端 ui.theme 跨端口保存用户偏好；localStorage 仅缓存当前来源的首帧主题。
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
