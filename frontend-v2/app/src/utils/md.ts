import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import type { Config } from 'dompurify'
import { katex } from '@mdit/plugin-katex'
import 'katex/dist/katex.min.css'
import './math.css'

/** CommonMark/GFM rendering shared by live and saved assistant messages. */
const markdown = new MarkdownIt({ html: true, linkify: true, breaks: true, typographer: false })
markdown.use(katex, {
  delimiters: 'all', mathFence: true, throwOnError: false,
  trust: false, maxSize: 20, maxExpand: 1000,
  logger: () => 'ignore' as const,
  transformer: (html: string, display: boolean) => display ? html : `<span class="math-inline">${html}</span>`,
})
export const escapeHtml = markdown.utils.escapeHtml

const defaultValidateLink = markdown.validateLink.bind(markdown)
markdown.validateLink = (url: string) => defaultValidateLink(url)
  && /^(?:https?:\/\/|mailto:|#|\/(?!\/))/i.test(url)

const defaultLinkOpen = markdown.renderer.rules.link_open
markdown.renderer.rules.link_open = (tokens, index, options, env, self) => {
  const href = String(tokens[index].attrGet('href') ?? '')
  if (/^(?:https?:\/\/|mailto:)/i.test(href)) {
    tokens[index].attrSet('target', '_blank')
    tokens[index].attrSet('rel', 'noopener noreferrer')
  }
  return defaultLinkOpen?.(tokens, index, options, env, self) ?? self.renderToken(tokens, index, options)
}

// Referenced images stay available as links without fetching external content
// merely because a message is being rendered.
markdown.renderer.rules.image = (tokens, index) => {
  const token = tokens[index]
  const href = String(token.attrGet('src') ?? '')
  const label = escapeHtml(token.content || '查看图片')
  return markdown.validateLink(href)
    ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${label}</a>`
    : label
}

markdown.core.ruler.after('inline', 'task_checkmarks', state => {
  for (let i = 2; i < state.tokens.length; i++) {
    const token = state.tokens[i]
    if (token.type !== 'inline' || state.tokens[i - 2].type !== 'list_item_open') continue
    const first = token.children?.[0]
    if (first?.type !== 'text' || !/^\[[ xX]\]\s/.test(first.content)) continue
    first.content = first.content.replace(/^\[([ xX])\]\s/, (_, checked: string) => checked === ' ' ? '☐ ' : '☑ ')
    state.tokens[i - 2].attrJoin('class', 'task-list-item')
  }
})

/**
 * AI 回复允许内嵌 HTML（html: true），整段输出仍经 DOMPurify 消毒，维持两条既有安全策略：
 * - 渲染消息不发起远程请求：禁 img/style/svg/iframe/form 等标签，style 属性里剥掉
 *   url()/image-set()/expression()（KaTeX 的 strut/valign 等纯几何样式不受影响）；
 * - id/name 属性加 user-content- 前缀，避免与界面锚点冲突；target 放行（外链新窗口）。
 * 事件处理属性（on*）、javascript: 等协议由 DOMPurify 默认规则拦截。
 */
const SANITIZE_CONFIG: Config = {
  FORBID_TAGS: ['img', 'style', 'svg', 'iframe', 'frame', 'frameset', 'object', 'embed',
    'applet', 'audio', 'video', 'source', 'track', 'form', 'input', 'button', 'select',
    'option', 'textarea', 'link', 'meta', 'base', 'noscript', 'template', 'dialog'],
  FORBID_ATTR: ['srcset', 'background', 'ping', 'srcdoc'],
  ADD_ATTR: ['target'],
  SANITIZE_NAMED_PROPS: true,
}

const REMOTE_CSS = /url\s*\(|image-set\s*\(|expression\s*\(/i
DOMPurify.addHook('uponSanitizeAttribute', (_node, data) => {
  if (data.attrName === 'style' && REMOTE_CSS.test(data.attrValue)) data.keepAttr = false
})
DOMPurify.addHook('afterSanitizeAttributes', node => {
  if (node.tagName === 'A' && node.getAttribute('target') === '_blank') {
    node.setAttribute('rel', 'noopener noreferrer')
  }
})

/** Incomplete streamed HTML/公式都被安全解析；消毒失败时退回纯文本转义。 */
export function renderMarkdown(raw: string): string {
  const html = markdown.render(raw)
  try {
    return DOMPurify.sanitize(html, SANITIZE_CONFIG)
  } catch {
    return `<p>${escapeHtml(raw)}</p>`
  }
}
