// 「问助手」统一入口：把预填 prompt 经 CustomEvent 送入助手输入框（由用户确认发送）。
// 通道与 CalendarView/BriefingCard 一致：AssistantView 监听 assistant:prompt。
export function askAssistant(text) {
  window.dispatchEvent(
    new CustomEvent('assistant:prompt', {
      detail: { text },
    })
  )
}
