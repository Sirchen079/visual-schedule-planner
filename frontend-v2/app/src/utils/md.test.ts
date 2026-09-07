import { describe, expect, it } from 'vitest'
import { escapeHtml, renderMarkdown } from './md'

describe('assistant Markdown', () => {
  it('renders headings, emphasis, quotes and paragraphs', () => {
    const html = renderMarkdown('# 标题\n\n**重点**与*强调*、~~删除~~。\n\n> 引用\n\n---')
    for (const tag of ['h1', 'strong', 'em', 's', 'blockquote', 'hr']) expect(html).toContain(`<${tag}`)
  })
  it('keeps fenced code literal, including incomplete streaming fences', () => {
    const code = '```js\nconst a = "**bold** <script>";\n'
    expect(renderMarkdown(code)).toContain('<pre><code class="language-js">')
    expect(renderMarkdown(code + '```')).toContain('**bold** &lt;script&gt;')
    expect(renderMarkdown(code)).not.toContain('<strong>')
    expect(renderMarkdown('`**literal**`')).toContain('<code>**literal**</code>')
  })
  it('renders nested lists, task lists and numbered list starts', () => {
    const html = renderMarkdown('3. 第三项\n   - 子项\n   - [x] 已完成\n   - [ ] 待完成')
    expect(html).toContain('<ol start="3">')
    expect(html).toContain('<ul>')
    expect(html).toContain('☑ 已完成')
    expect(html).toContain('☐ 待完成')
    expect(renderMarkdown('2026.09')).not.toContain('<ol')
  })
  it('supports tables without outer pipes and escaped pipe content', () => {
    const html = renderMarkdown('字段 | 值\n--- | ---\nA | a\\|b')
    expect(html).toContain('<table>')
    expect(html).toContain('<th>字段</th>')
    expect(html).toContain('<td>a|b</td>')
  })
  it('renders links with safe external window attributes', () => {
    const html = renderMarkdown('[来源](https://example.com/page?a=1&b=2) https://example.org')
    expect(html).toContain('href="https://example.com/page?a=1&amp;b=2"')
    expect(html).toContain('rel="noopener noreferrer"')
    expect(html).toContain('target="_blank"')
    expect(html).toContain('href="https://example.org"')
  })
  it.each(['javascript:alert(1)', 'data:text/html,evil', 'file:///C:/test', 'vbscript:evil', 'javascript&#58;evil'])('rejects active or local URLs: %s', href => {
    expect(renderMarkdown(`[打开](${href})`)).not.toContain('<a ')
  })
  it('escapes raw HTML, SVG and handler attributes', () => {
    const html = renderMarkdown('<img src=x onerror=alert(1)>\n\n<svg onload=alert(1)> **文字**')
    expect(html).not.toMatch(/<(?:img|svg|script)\b/i)
    expect(html).toContain('&lt;img')
    expect(html).toContain('<strong>文字</strong>')
    expect(escapeHtml('<script>"&')).toBe('&lt;script&gt;&quot;&amp;')
  })
  it('does not fetch image links on render', () => {
    const html = renderMarkdown('![图片说明](https://example.com/image.png)')
    expect(html).not.toContain('<img')
    expect(html).toContain('>图片说明</a>')
  })
})
