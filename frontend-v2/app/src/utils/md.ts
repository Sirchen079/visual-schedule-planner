/**
 * 最小 markdown 渲染：assistant 正文专用。
 * 先整体 HTML 转义（防 XSS），再恢复白名单语法：
 * **粗体**、`行内代码`、无序/有序列表、GFM 表格、换行。不支持的语法保持原样字符。
 */

const ESCAPES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}

export function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ESCAPES[c] ?? c)
}

function renderInline(s: string): string {
  return s
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
}

/** 输入原始 markdown 文本，输出安全的 HTML 字符串（配合 v-html 使用）。 */
export function renderMarkdown(raw: string): string {
  const lines = escapeHtml(raw).split('\n')
  const out: string[] = []
  let list: 'ul' | 'ol' | null = null

  const closeList = () => {
    if (list) {
      out.push(list === 'ul' ? '</ul>' : '</ol>')
      list = null
    }
  }

  const splitRow = (line: string) =>
    line.replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim())
  // 分隔行：整行由 | - : 与空白构成，且至少含一个 -
  const isTableSep = (line: string) => /^\|[\s:|-]+\|?$/.test(line) && line.includes('-')

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]

    // GFM 表格：当前行是表头、下一行是分隔行时才进入表格块
    if (line.trimStart().startsWith('|') && i + 1 < lines.length && isTableSep(lines[i + 1].trim())) {
      closeList()
      const header = splitRow(line.trim())
      const body: string[][] = []
      i += 2
      while (i < lines.length && lines[i].trimStart().startsWith('|')) {
        body.push(splitRow(lines[i].trim()))
        i++
      }
      i-- // 抵消 for 循环的自增
      out.push(
        '<table><thead><tr>' +
          header.map((c) => `<th>${renderInline(c)}</th>`).join('') +
          '</tr></thead><tbody>' +
          body.map((r) => '<tr>' + r.map((c) => `<td>${renderInline(c)}</td>`).join('') + '</tr>').join('') +
          '</tbody></table>',
      )
      continue
    }

    const ul = /^[-*]\s+/.test(line)
    // 有序列表标记后要求空白或紧跟 CJK 字符（避免把「2026.09」误判为列表）
    const ol = /^\d+[.、](?:\s+|(?=[\u4e00-\u9fff]))/.test(line)
    if (ul || ol) {
      const kind = ul ? 'ul' : 'ol'
      if (list !== kind) {
        closeList()
        out.push(kind === 'ul' ? '<ul>' : '<ol>')
        list = kind
      }
      out.push(`<li>${renderInline(line.replace(/^[-*]\s+|^\d+[.、]\s*/, ''))}</li>`)
      continue
    }
    closeList()
    if (line.trim() === '') {
      out.push('<br>')
    } else {
      out.push(`<p>${renderInline(line)}</p>`)
    }
  }
  closeList()
  return out.join('')
}
