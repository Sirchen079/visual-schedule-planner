import { describe, expect, it } from 'vitest'
import { escapeHtml, renderMarkdown } from './md'

describe('escapeHtml', () => {
  it('转义 HTML 特殊字符', () => {
    expect(escapeHtml('<script>alert("x")</script>')).toBe(
      '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;',
    )
  })
})

describe('renderMarkdown', () => {
  it('粗体与行内代码', () => {
    expect(renderMarkdown('找到了：**测试日程**（`event_id=18`）')).toBe(
      '<p>找到了：<strong>测试日程</strong>（<code>event_id=18</code>）</p>',
    )
  })

  it('XSS 注入被转义，不生成活 HTML', () => {
    const out = renderMarkdown('<img src=x onerror=alert(1)> **加粗**')
    expect(out).not.toContain('<img')
    expect(out).toContain('&lt;img')
    expect(out).toContain('<strong>加粗</strong>')
  })

  it('无序列表合并为 ul/li', () => {
    expect(renderMarkdown('- 甲\n- 乙\n\n收尾')).toBe(
      '<ul><li>甲</li><li>乙</li></ul><br><p>收尾</p>',
    )
  })

  it('有序列表（含中文顿号）', () => {
    expect(renderMarkdown('1. 先\n2、后')).toBe('<ol><li>先</li><li>后</li></ol>')
  })

  it('列表结束后回到正文', () => {
    expect(renderMarkdown('- 甲\n正文 **加粗**')).toBe('<ul><li>甲</li></ul><p>正文 <strong>加粗</strong></p>')
  })

  it('不支持的语法保持原样', () => {
    expect(renderMarkdown('# 标题')).toBe('<p># 标题</p>')
  })

  it('GFM 表格（表头 + 分隔行 + 数据行）', () => {
    expect(renderMarkdown('| 步骤 | 结果 |\n|---|---|\n| 1. 创建 | ✅ **成功** |')).toBe(
      '<table><thead><tr><th>步骤</th><th>结果</th></tr></thead><tbody><tr><td>1. 创建</td><td>✅ <strong>成功</strong></td></tr></tbody></table>',
    )
  })

  it('表格块结束后回到正文，普通竖线行不误判', () => {
    expect(renderMarkdown('| a |\n|---|\n| b |\n收尾')).toBe(
      '<table><thead><tr><th>a</th></tr></thead><tbody><tr><td>b</td></tr></tbody></table><p>收尾</p>',
    )
    // 只有一行竖线开头、下一行不是分隔行 → 按普通段落处理
    expect(renderMarkdown('| 不是表 | x |')).toBe('<p>| 不是表 | x |</p>')
  })
})
