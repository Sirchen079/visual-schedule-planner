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
  it.each([
    '$E=mc^2$', String.raw`\(\frac{1}{2}\)`,
    '$$\nx^2+y^2=z^2\n$$', String.raw`\[\int_0^1 x\,dx=\frac12\]`,
    '```math\nx^2\n```',
  ])('renders common math delimiters: %s', source => {
    const html = renderMarkdown(source)
    expect(html).toContain('class="katex"')
    expect(html).toContain('<math')
    expect(html).not.toContain('katex-error')
  })
  it('renders aligned equations and matrices in display math', () => {
    const html = renderMarkdown(String.raw`\[
\begin{aligned} f(x)&=x^2 \\ f'(x)&=2x \end{aligned}
\qquad \begin{pmatrix}1&2\\3&4\end{pmatrix}
\]`)
    expect(html).toContain('katex-display')
    expect(html).toContain('<mtable')
    expect(html).not.toContain('katex-error')
  })
  it('keeps code, escaped delimiters and currency literal', () => {
    for (const source of ['`$x$`', '```latex\n\\[x^2\\]\n```', String.raw`\$x$`, '预算 $5，另一个 $10']) {
      expect(renderMarkdown(source)).not.toContain('class="katex"')
    }
  })
  it('tolerates streamed partial formulas and keeps malformed input readable', () => {
    const source = String.raw`结果：\(\frac{1}{2}\)。

$$
\sum_{i=1}^n i=\frac{n(n+1)}{2}
$$`
    for (let i = 1; i <= source.length; i++) expect(() => renderMarkdown(source.slice(0, i))).not.toThrow()
    expect(renderMarkdown(source)).not.toContain('katex-error')
    expect(renderMarkdown(String.raw`$\frac{1}$`)).toContain('katex-error')
    expect(renderMarkdown(String.raw`$\unknownCommand{value}$`)).toContain('\\unknownCommand')
  })
  it('blocks formula URLs and HTML commands, and escapes invalid math', () => {
    const html = renderMarkdown(String.raw`$\href{javascript:alert(1)}{click}$

$\includegraphics{https://example.org/tracking.png}$

$\htmlStyle{background:url(https://example.org/track)}{x}$

$\unknown{<img src=x onerror=alert(1)>}$`)
    expect(html).not.toMatch(/<(?:a|img|script)\b/)
    expect(html).not.toContain('style="background:')
    expect(html).toContain('&lt;img')
  })
  it('bounds recursive macros and does not carry definitions into another message', () => {
    expect(renderMarkdown(String.raw`$\def\loop{\loop}\loop$`)).toContain('katex-error')
    expect(renderMarkdown(String.raw`$\gdef\custom{42}\custom$`)).not.toContain('katex-error')
    expect(renderMarkdown(String.raw`$\custom$`)).toContain('<mtext>\\custom</mtext>')
  })
})
