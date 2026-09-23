import { describe, expect, it } from 'vitest'
import {
  BOARD_MAX_HEIGHT, BOARD_MIN_HEIGHT, BOARD_FALLBACK_HEIGHT, SANDBOX_DOC,
  clampBoardHeight, createHeightGuard, extractPartialBoard, parseBoardMessage,
  trimUnclosedScript,
} from './blackboard'

describe('黑板持久沙箱文档', () => {
  it('协议齐全：update/finalize/theme 下行 + ready/error/height 上行 + 主题属性', () => {
    for (const marker of [
      'blackboard:update', 'blackboard:finalize', 'blackboard:theme',
      'blackboard:ready', 'blackboard:error', 'blackboard:height', 'data-theme',
    ]) {
      expect(SANDBOX_DOC).toContain(marker)
    }
  })
  it('内嵌运行时无裸 </script>（不会截断沙箱文档自身），挂载走 DOMParser', () => {
    const body = SANDBOX_DOC.slice(SANDBOX_DOC.indexOf('<script>') + 8, SANDBOX_DOC.lastIndexOf('<\/script>'))
    expect(body.length).toBeGreaterThan(500)
    expect(body).not.toContain('</script')
    expect(body).toContain('DOMParser')
    expect(body).toContain('importNode')
  })
  it('深浅色两套纸色变量都在基础样式里', () => {
    expect(SANDBOX_DOC).toContain('--board-bg')
    expect(SANDBOX_DOC).toContain("data-theme='dark'")
    expect(SANDBOX_DOC).toContain('data-theme="light"')
  })
})

describe('黑板高度钳制', () => {
  it('钳制在上下限内，非法值回退兜底', () => {
    expect(clampBoardHeight(80)).toBe(BOARD_MIN_HEIGHT)
    expect(clampBoardHeight(5000)).toBe(BOARD_MAX_HEIGHT)
    expect(clampBoardHeight(377.6)).toBe(378)
    expect(clampBoardHeight(Number.NaN)).toBe(BOARD_FALLBACK_HEIGHT)
  })
})

describe('高度防抖（抖动环路检测）', () => {
  it('短窗口内连续微小增长达到阈值后拒绝，大幅变化重置计数', () => {
    let now = 1000
    const guard = createHeightGuard(420, { now: () => now })
    // +1px 连续 5 次仍在窗口内 → 接受；第 6 次起拒绝
    for (let i = 1; i <= 5; i++) {
      now += 100
      expect(guard.push(420 + i)).toBe(420 + i)
    }
    now += 100
    expect(guard.push(426)).toBe(425) // 第 6 次 +1：判定抖动，拒绝
    now += 100
    expect(guard.push(427)).toBe(425) // 持续拒绝
    now += 100
    expect(guard.push(490)).toBe(490) // 大幅增长：重置并接受
    now += 100
    expect(guard.push(491)).toBe(491) // 重新从 1 计数，接受
  })
  it('超出时间窗口的微小增长不连续计数，正常接受', () => {
    let now = 1000
    const guard = createHeightGuard(420, { now: () => now, windowMs: 300 })
    for (let i = 1; i <= 10; i++) {
      now += 400
      expect(guard.push(420 + i)).toBe(420 + i)
    }
  })
  it('收缩与小幅收缩不受防抖限制', () => {
    let now = 1000
    const guard = createHeightGuard(420, { now: () => now })
    for (let i = 0; i < 10; i++) {
      now += 100
      expect(guard.push(400)).toBe(400)
    }
  })
})

describe('流式参数提取', () => {
  it('完整 JSON 直接解析，缺 title 回退默认', () => {
    const args = JSON.stringify({ title: '日程示意', html: '<h1>hi</h1>' })
    expect(extractPartialBoard(args)).toEqual({ title: '日程示意', html: '<h1>hi</h1>' })
    expect(extractPartialBoard(JSON.stringify({ html: '<p>x</p>' }))).toEqual({ title: '黑板', html: '<p>x</p>' })
  })
  it('半截 html 值也能抠出已到达的部分', () => {
    const args = '{"title": "日程示意", "html": "<div class=\\"card\\"><h1>安排</h1>'
    expect(extractPartialBoard(args)).toEqual({ title: '日程示意', html: '<div class="card"><h1>安排</h1>' })
  })
  it('转义的引号与换行不会截断提取', () => {
    const args = '{"html": "<p>他说：\\"好\\"</p>\\n<div>尾'
    expect(extractPartialBoard(args)).toEqual({ title: '黑板', html: '<p>他说："好"</p>\n<div>尾' })
  })
  it('尾随反斜杠先裁掉再补引号解析', () => {
    const args = '{"html": "<p>a\\'
    expect(extractPartialBoard(args)).toEqual({ title: '黑板', html: '<p>a' })
  })
  it('html 值完整但转义损坏时不硬造', () => {
    expect(extractPartialBoard('{"html": "<p>bad\\q"</p>')).toBeNull()
  })
  it('html 未开始 / 空白内容 / 无关文本返回 null', () => {
    expect(extractPartialBoard('{"title": "only-title"}')).toBeNull()
    expect(extractPartialBoard('{"html": "   "}')).toBeNull()
    expect(extractPartialBoard('')).toBeNull()
    expect(extractPartialBoard('noise')).toBeNull()
  })
})

describe('流式裁尾', () => {
  it('闭合脚本块原样保留', () => {
    const html = '<p>x</p><script>var a=1;</script><p>y</p>'
    expect(trimUnclosedScript(html)).toBe(html)
  })
  it('末尾未闭合脚本连同其后内容一起裁掉', () => {
    expect(trimUnclosedScript('<p>x</p><script>var a="1')).toBe('<p>x</p>')
    expect(trimUnclosedScript('<p>x</p><script src="x.js">partial')).toBe('<p>x</p>')
  })
  it('首个闭合、第二个未闭合 → 裁到第二个开头', () => {
    expect(trimUnclosedScript('<script>a</script><p>y</p><script>b')).toBe('<script>a</script><p>y</p>')
  })
  it('正文里的 <scripted 不是脚本标签', () => {
    const html = '<p>use <scripted> word</p>'
    expect(trimUnclosedScript(html)).toBe(html)
  })
})

describe('宿主消息解析', () => {
  it('握手、错误、高度、无关消息', () => {
    expect(parseBoardMessage({ type: 'blackboard:ready' })).toEqual({ type: 'blackboard:ready' })
    expect(parseBoardMessage({ type: 'blackboard:error', kind: 'promise', message: 'boom', detail: 'stack' }))
      .toEqual({ type: 'blackboard:error', kind: 'promise', message: 'boom', detail: 'stack' })
    expect(parseBoardMessage({ type: 'blackboard:error', kind: 'weird', message: 'x' }))
      .toEqual({ type: 'blackboard:error', kind: 'script', message: 'x', detail: '' })
    expect(parseBoardMessage({ type: 'blackboard:height', height: 300.4 }))
      .toEqual({ type: 'blackboard:height', height: 300.4 })
    expect(parseBoardMessage({ type: 'other' })).toBeNull()
    expect(parseBoardMessage('noise')).toBeNull()
    expect(parseBoardMessage({ type: 'blackboard:error', message: '' })).toBeNull()
    expect(parseBoardMessage({ type: 'blackboard:height', height: 'x' })).toBeNull()
  })
})
