import MarkdownIt from 'markdown-it'

/** CommonMark/GFM rendering shared by live and saved assistant messages. */
const markdown = new MarkdownIt({ html: false, linkify: true, breaks: true, typographer: false })
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

/** Raw HTML remains escaped; incomplete streamed blocks are parsed safely. */
export function renderMarkdown(raw: string): string {
  return markdown.render(raw)
}
