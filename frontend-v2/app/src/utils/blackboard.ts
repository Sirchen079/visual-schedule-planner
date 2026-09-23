/**
 * 黑板 iframe 运行时：错误捕获 + 高度自适应（机制借鉴 WorkBuddy show_widget 的
 * 沙箱引导脚本——window.onerror/unhandledrejection 按相位回报宿主，宿主钳制高度）。
 * 纯字符串工具，不依赖 DOM，可在 node 环境测试。
 */

/** 注入 AI 页面的引导脚本：报错回报（前 5 条，防风暴）+ 内容高度回报。 */
const RUNTIME_JS = `(function(){
  'use strict';
  var reported = 0;
  function report(kind, message, detail){
    if (reported++ >= 5) return;
    try {
      parent.postMessage({ type: 'blackboard:error', kind: kind,
        message: String(message || '').slice(0, 500),
        detail: String(detail || '').slice(0, 800) }, '*');
    } catch (_) {}
  }
  window.addEventListener('error', function(e){
    report('script', e.message, (e.error && e.error.stack) || (e.filename ? e.filename + ':' + e.lineno : ''));
  }, true);
  window.addEventListener('unhandledrejection', function(e){
    var r = e.reason;
    report('promise', (r && r.message) || String(r), (r && r.stack) || '');
  });
  var last = -1;
  function postHeight(){
    var h = Math.ceil(document.documentElement.getBoundingClientRect().height);
    if (h > 0 && h !== last) {
      last = h;
      try { parent.postMessage({ type: 'blackboard:height', height: h }, '*'); } catch (_) {}
    }
  }
  if (typeof ResizeObserver !== 'undefined') new ResizeObserver(postHeight).observe(document.documentElement);
  window.addEventListener('load', postHeight);
  setTimeout(postHeight, 60);
})();`

/** 把引导脚本注入 AI 的完整文档，或把片段包成完整文档。 */
export function buildBoardDoc(html: string): string {
  const script = `<script>${RUNTIME_JS}<\/script>`
  if (/<html[\s>]/i.test(html)) {
    if (/<head[\s>]/i.test(html)) return html.replace(/<head[^>]*>/i, (m) => m + script)
    return html.replace(/<html[^>]*>/i, (m) => m + script)
  }
  return `<!DOCTYPE html><html><head><meta charset="utf-8">${script}</head><body style="margin:0">${html}</body></html>`
}

export const BOARD_MIN_HEIGHT = 160
export const BOARD_MAX_HEIGHT = 1000
/** 未收到高度回报时的兜底（与面板 CSS 的初始高度一致） */
export const BOARD_FALLBACK_HEIGHT = 420

export function clampBoardHeight(px: number): number {
  if (!Number.isFinite(px)) return BOARD_FALLBACK_HEIGHT
  return Math.min(Math.max(Math.round(px), BOARD_MIN_HEIGHT), BOARD_MAX_HEIGHT)
}

/** 宿主侧的 iframe 消息（错误回报 / 高度回报） */
export type BoardHostMessage =
  | { type: 'blackboard:error'; kind: 'script' | 'promise'; message: string; detail: string }
  | { type: 'blackboard:height'; height: number }

export function parseBoardMessage(data: unknown): BoardHostMessage | null {
  if (!data || typeof data !== 'object') return null
  const d = data as Record<string, unknown>
  if (d.type === 'blackboard:error' && typeof d.message === 'string' && d.message) {
    return { type: 'blackboard:error',
      kind: d.kind === 'promise' ? 'promise' : 'script',
      message: d.message, detail: typeof d.detail === 'string' ? d.detail : '' }
  }
  if (d.type === 'blackboard:height' && typeof d.height === 'number') {
    return { type: 'blackboard:height', height: d.height }
  }
  return null
}
