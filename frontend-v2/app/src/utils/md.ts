import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import type { Config } from 'dompurify'
import { katex } from '@mdit/plugin-katex'
import { footnote } from '@mdit/plugin-footnote'
import { mark } from '@mdit/plugin-mark'
import { sub } from '@mdit/plugin-sub'
import { sup } from '@mdit/plugin-sup'
import { alert } from '@mdit/plugin-alert'
import cjkFriendly from 'markdown-it-cjk-friendly'
import 'katex/dist/katex.min.css'
import './math.css'
import './md-plugins.css'

/** CommonMark/GFM rendering shared by live and saved assistant messages. */
const markdown = new MarkdownIt({ html: true, linkify: true, breaks: true, typographer: false })
markdown.use(cjkFriendly)
markdown.use(footnote)
markdown.use(mark)
markdown.use(sub)
markdown.use(sup)
markdown.use(alert)
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
 * CommonMark 的 HTML 块规则会吞下「开标签行」直到空行之间的全部内容；
 * AI 输出经常直接用 <div> 包裹 Markdown 段落。这里在"整行只有块级开/闭标签"的
 * 行后/行前补空行，让标签内外的 Markdown 都正常解析。围栏代码块内的行不动。
 */
const SPLIT_TAG = 'div|p|section|article|aside|header|footer|main|nav|center|details|summary|figure|figcaption|blockquote|fieldset|form|table|thead|tbody|tfoot|tr|td|th|ul|ol|li|dl|dt|dd|h[1-6]'
const OPEN_TAG_LINE = new RegExp(`^ {0,3}(<(?:${SPLIT_TAG})(?:\\s[^<>]*)?>)[ \\t]*$`, 'i')
const CLOSE_TAG_LINE = new RegExp(`^ {0,3}(</(?:${SPLIT_TAG})>)[ \\t]*$`, 'i')
const FENCE_LINE = /^ {0,3}(`{3,}|~{3,})/

function markdownInsideHtml(raw: string): string {
  const lines = raw.split('\n')
  let fence: string | null = null
  for (let i = 0; i < lines.length; i++) {
    const fenceMatch = FENCE_LINE.exec(lines[i])
    if (fence !== null) {
      if (fenceMatch !== null && fenceMatch[1][0] === fence[0] && fenceMatch[1].length >= fence.length) fence = null
      continue
    }
    if (fenceMatch !== null) {
      fence = fenceMatch[1]
      continue
    }
    if (OPEN_TAG_LINE.test(lines[i])) {
      lines.splice(i + 1, 0, '', '')
      i += 2
    } else if (CLOSE_TAG_LINE.test(lines[i])) {
      lines.splice(i, 0, '', '')
      i += 2
    }
  }
  return lines.join('\n')
}

/**
 * AI 回复允许内嵌 HTML（html: true），整段输出仍经 DOMPurify 消毒，维持两条既有安全策略：
 * - 渲染消息不发起远程请求：禁 img/style/svg/iframe/form 等标签，style 属性里剥掉
 *   url()/image-set()/expression()（KaTeX 的 strut/valign 等纯几何样式不受影响）；
 * - id/name 属性加 user-content- 前缀，避免与界面锚点冲突；target 放行（外链新窗口）。
 * 事件处理属性（on*）、javascript: 等协议由 DOMPurify 默认规则拦截。
 * 独立的"黑板"页面走专门的沙箱 iframe，不经过这条消息流通道。
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

/** Incomplete streamed HTML/公式/围栏都被安全解析；消毒失败时退回纯文本转义。 */
export function renderMarkdown(raw: string): string {
  const html = markdown.render(markdownInsideHtml(raw))
  try {
    return DOMPurify.sanitize(html, SANITIZE_CONFIG)
  } catch {
    return `<p>${escapeHtml(raw)}</p>`
  }
}
