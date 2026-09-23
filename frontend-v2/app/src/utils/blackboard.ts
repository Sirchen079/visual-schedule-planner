/**
 * 黑板 iframe 运行时：持久沙箱文档 + postMessage 协议。
 *
 * 宿主 → iframe：blackboard:update（流式半成品挂载，脚本不执行）、
 * blackboard:finalize（整页挂载，脚本重创建为可执行元素）、blackboard:theme（深浅色）。
 * iframe → 宿主：blackboard:ready（握手，此前宿主消息先排队）、blackboard:error
 * （页内脚本报错回报，前 5 条防风暴）、blackboard:height（内容高度）。
 *
 * 机制借鉴 WorkBuddy show_widget：沙箱引导脚本（window.onerror / unhandledrejection
 * 回报宿主）、流式参数的部分 JSON 提取、微小高度增长防抖（抖动环路检测）。
 * 纯字符串 / 纯函数，不依赖真实 DOM，可在 node 环境测试。
 */

/** 沙箱文档基础样式：默认纸色变量随主题切换；AI 页面自带样式在其后导入，优先生效。 */
const BOARD_BASE_CSS = [
  ':root { --board-bg: #f7f3ea; --board-ink: #33302a; }',
  "html[data-theme='dark'] { --board-bg: #221f1a; --board-ink: #e7e3d9; }",
  'html { background: var(--board-bg); }',
  'body { margin: 0; background: var(--board-bg); color: var(--board-ink); font-family: system-ui, sans-serif; }',
].join('\n')

/**
 * 沙箱内置运行时：报错/高度回报、update/finalize 双相挂载、theme 同步。
 * finalize 用 DOMParser 解出节点后 importNode 导入——innerHTML 不会执行 <script>，
 * 所以脚本要单独摘出来重新 createElement 再插入才会运行；流式挂载一律跳过脚本。
 */
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
  var baseStyle = document.getElementById('board-base');
  function clear(el){ while (el.firstChild) el.removeChild(el.firstChild); }
  function absorb(from, to, scripts, live){
    var nodes = Array.prototype.slice.call(from.childNodes);
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      if (n.nodeType === 1 && String(n.tagName).toLowerCase() === 'script') {
        if (live) scripts.push(n);
        continue;
      }
      to.appendChild(document.importNode(n, true));
    }
  }
  function mount(html, live){
    try {
      var parsed = new DOMParser().parseFromString(html, 'text/html');
      var scripts = [];
      clear(document.head);
      document.head.appendChild(baseStyle);
      clear(document.body);
      absorb(parsed.head, document.head, scripts, live);
      absorb(parsed.body, document.body, scripts, live);
      for (var i = 0; i < scripts.length; i++) {
        var old = scripts[i], s = document.createElement('script');
        if (old.src) s.src = old.src;
        if (old.type) s.type = old.type;
        if (old.async) s.async = true;
        s.text = old.text;
        document.body.appendChild(s);
      }
      last = -1;
      setTimeout(postHeight, 0);
      setTimeout(postHeight, 60);
    } catch (e) {
      report('script', (e && e.message) || String(e), '');
    }
  }
  function cutUnclosedScript(html){
    var lower = html.toLowerCase();
    var open = lower.lastIndexOf('<script');
    if (open === -1) return html;
    var ch = lower.charAt(open + 7);
    if (ch !== '' && !/[\\s/>]/.test(ch)) return html;
    if (lower.indexOf('<\\/script', open) !== -1) return html;
    return html.slice(0, open);
  }
  window.addEventListener('message', function(e){
    var d = e.data;
    if (!d || typeof d !== 'object') return;
    if (d.type === 'blackboard:update' && typeof d.html === 'string') mount(cutUnclosedScript(d.html), false);
    else if (d.type === 'blackboard:finalize' && typeof d.html === 'string') mount(d.html, true);
    else if (d.type === 'blackboard:theme' && (d.theme === 'dark' || d.theme === 'light')) {
      document.documentElement.setAttribute('data-theme', d.theme);
    }
  });
  try { parent.postMessage({ type: 'blackboard:ready' }, '*'); } catch (_) {}
})();`

/** 沙箱 iframe 的 srcdoc（常量：iframe 只加载一次，后续内容全部走消息协议）。 */
export const SANDBOX_DOC = `<!DOCTYPE html><html lang="zh-CN" data-theme="light"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><style id="board-base">${BOARD_BASE_CSS}</style></head><body><script>${RUNTIME_JS}<\/script></body></html>`

export const BOARD_MIN_HEIGHT = 160
export const BOARD_MAX_HEIGHT = 1000
/** 未收到高度回报时的兜底（与面板 CSS 的初始高度一致） */
export const BOARD_FALLBACK_HEIGHT = 420

export function clampBoardHeight(px: number): number {
  if (!Number.isFinite(px)) return BOARD_FALLBACK_HEIGHT
  return Math.min(Math.max(Math.round(px), BOARD_MIN_HEIGHT), BOARD_MAX_HEIGHT)
}

export interface HeightGuardOptions {
  /** 视为「微小增长」的最大增量（px） */
  maxTinyDelta?: number
  /** 微小增长的连续判定窗口（ms） */
  windowMs?: number
  /** 窗口内连续微小增长达到该次数即判定为抖动环路，拒绝再增长 */
  maxStreak?: number
  now?: () => number
}

export interface HeightGuard {
  push: (px: number) => number
}

/**
 * 高度防抖守卫（机制借鉴 WorkBuddy 的 MAX_TINY_GROWTH_* 常量）：页面自适应高度
 * 与 iframe 高度互相反馈时会出现每次 +1~2px 的抖动环路。短窗口内连续多次微小
 * 增长即拒绝该次增长，直到出现大幅变化或超出窗口时间。push 返回守卫接受后的高度。
 */
export function createHeightGuard(initial = BOARD_FALLBACK_HEIGHT, opts: HeightGuardOptions = {}): HeightGuard {
  const maxTinyDelta = opts.maxTinyDelta ?? 2
  const windowMs = opts.windowMs ?? 300
  const maxStreak = opts.maxStreak ?? 6
  const nowFn = opts.now ?? Date.now
  let current = clampBoardHeight(initial)
  let lastAt = nowFn()
  let streak = 0
  return {
    push(px: number): number {
      const next = clampBoardHeight(px)
      const at = nowFn()
      const tiny = next > current && next - current <= maxTinyDelta && at - lastAt <= windowMs
      streak = tiny ? streak + 1 : 0
      lastAt = at
      if (tiny && streak >= maxStreak) return current
      current = next
      return current
    },
  }
}

export interface PartialBoard {
  title: string
  html: string
}

function unescapeJson(s: string): string | null {
  try {
    const v = JSON.parse(`"${s}"`) as unknown
    return typeof v === 'string' ? v : null
  } catch {
    return null
  }
}

/**
 * 从流式累积的 show_blackboard 参数文本里尽量抠出 {title, html}：
 * 完整 JSON 直接解析；半成品则定位 html 值的起点，扫描到未转义的收尾引号或
 * 直接补引号再解（尾随反斜杠会吃掉补上的引号，先裁再试）。抠不出返回 null。
 */
export function extractPartialBoard(argsText: string): PartialBoard | null {
  if (!argsText || !argsText.includes('"html"')) return null
  try {
    const obj = JSON.parse(argsText) as { title?: unknown; html?: unknown }
    if (obj && typeof obj === 'object' && typeof obj.html === 'string' && obj.html.trim()) {
      return { title: typeof obj.title === 'string' && obj.title ? obj.title : '黑板', html: obj.html }
    }
    return null
  } catch {
    // 流式半成品，走部分解析
  }
  const titleMatch = argsText.match(/"title"\s*:\s*"((?:[^"\\]|\\.)*)/)
  const title = (titleMatch && unescapeJson(titleMatch[1])) || '黑板'
  const startMatch = argsText.match(/"html"\s*:\s*"/)
  if (!startMatch) return null
  const rest = argsText.slice((startMatch.index ?? 0) + startMatch[0].length)
  let end = -1
  for (let i = 0; i < rest.length; i++) {
    if (rest[i] === '\\') { i += 1; continue }
    if (rest[i] === '"') { end = i; break }
  }
  if (end >= 0) {
    const html = unescapeJson(rest.slice(0, end))
    return html && html.trim() ? { title, html } : null
  }
  // 值还没写完：unescapeJson 自行补收尾引号；尾随反斜杠是没写完的转义序列，先裁再试
  const trimmed = rest.replace(/\\+$/, '')
  const html = unescapeJson(trimmed) ?? unescapeJson(rest)
  return html && html.trim() ? { title, html } : null
}

/**
 * 流式挂载前裁尾：末尾未闭合的 <script> 连同其后内容一起裁掉
 * （半截脚本会吞掉后续正文）；闭合脚本块与 <scripted> 之类非标签文本不受影响。
 */
export function trimUnclosedScript(html: string): string {
  const lower = html.toLowerCase()
  const open = lower.lastIndexOf('<script')
  if (open === -1) return html
  const ch = lower.charAt(open + 7)
  if (ch !== '' && !/[\s/>]/.test(ch)) return html
  if (lower.indexOf('</script', open) !== -1) return html
  return html.slice(0, open)
}

/** 宿主 → iframe 的消息（协议见文件头）。 */
export type BoardGuestMessage =
  | { type: 'blackboard:update'; html: string }
  | { type: 'blackboard:finalize'; html: string }
  | { type: 'blackboard:theme'; theme: 'dark' | 'light' }

/** 宿主侧收到的 iframe 消息（握手 / 错误回报 / 高度回报）。 */
export type BoardHostMessage =
  | { type: 'blackboard:ready' }
  | { type: 'blackboard:error'; kind: 'script' | 'promise'; message: string; detail: string }
  | { type: 'blackboard:height'; height: number }

export function parseBoardMessage(data: unknown): BoardHostMessage | null {
  if (!data || typeof data !== 'object') return null
  const d = data as Record<string, unknown>
  if (d.type === 'blackboard:ready') return { type: 'blackboard:ready' }
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
