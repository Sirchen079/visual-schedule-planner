/**
 * 快捷键体系的跨组件端口（M4e）。
 *
 * 为什么存在：KEYMAP 要求 window keydown 只有 useHotkeys 一处监听（单一注册点），
 * 但 Esc 分层（②番茄钟表单 / ③域内浮层）与 c 键聚焦对话输入框需要触达深处的组件状态
 * （FocusBar 的开始表单、CalendarView 的详情卡、ChatInput 的 textarea）。
 * 本模块只存「回调句柄」，不挂任何监听——组件在 setup 里注册，useHotkeys 的统一分发消费。
 *
 * 层级约定（KEYMAP 守卫 4）：tier 2 = 通知面板之外的应用级表单（番茄钟开始表单），
 * tier 3 = 域内浮层（事件详情便签卡）。通知面板由 store 的 panelOpen 直接读取，不经过这里。
 */
import type { InjectionKey } from 'vue'

export interface EscLayerEntry {
  tier: 2 | 3
  close: () => void
}

interface EscLayerRecord extends EscLayerEntry {
  id: number
}

const escLayers: EscLayerRecord[] = []
let escSeq = 0

/** 注册一个 Esc 分层条目；返回注销函数（组件卸载/关闭时必须调用，防泄漏）。 */
export function registerEscLayer(entry: EscLayerEntry): () => void {
  const id = ++escSeq
  escLayers.push({ id, ...entry })
  return () => {
    const i = escLayers.findIndex((x) => x.id === id)
    if (i >= 0) escLayers.splice(i, 1)
  }
}

/** 当前 Esc 应关的最内层：先 tier 2 后 tier 3，同层后注册的先关（LIFO）。 */
export function topEscLayer(): EscLayerEntry | null {
  for (const tier of [2, 3] as const) {
    for (let i = escLayers.length - 1; i >= 0; i--) {
      if (escLayers[i].tier === tier) return escLayers[i]
    }
  }
  return null
}

/** 番茄钟开始表单控制（FocusBar 注册）：f 键展开、Esc 第②层收起。 */
export interface FocusFormControl {
  expand: () => void
  collapse: () => void
}

let focusFormControl: FocusFormControl | null = null

export function registerFocusFormControl(ctl: FocusFormControl): () => void {
  focusFormControl = ctl
  return () => {
    if (focusFormControl === ctl) focusFormControl = null
  }
}

export function getFocusFormControl(): FocusFormControl | null {
  return focusFormControl
}

/**
 * 对话输入框聚焦入口的注册表（ChatInput 注册、App.vue provide、c 键消费）。
 * 走 provide/inject 而非 window CustomEvent：类型安全、无全局副作用、单测可直调；
 * 而非 props 透传：ChatInput 深藏在 ChatPanel 内，穿层会污染中间组件。
 */
export interface ChatFocusRegistry {
  register(fn: () => void): () => void
}

export const CHAT_FOCUS_KEY: InjectionKey<ChatFocusRegistry> = Symbol('zhishi-chat-focus')

/** 仅测试用：清空全部端口注册，避免用例间串扰。生产代码不得调用。 */
export function resetHotkeyPortsForTest(): void {
  escLayers.length = 0
  focusFormControl = null
}
