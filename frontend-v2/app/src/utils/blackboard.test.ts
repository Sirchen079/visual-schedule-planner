import { describe, expect, it } from 'vitest'
import { BOARD_MAX_HEIGHT, BOARD_MIN_HEIGHT, buildBoardDoc, clampBoardHeight, parseBoardMessage } from './blackboard'

describe('黑板 iframe 运行时', () => {
  it('完整文档在 <head> 后注入引导脚本（先于页面自身脚本执行）', () => {
    const doc = buildBoardDoc('<!DOCTYPE html><html><head><meta charset="utf-8"><title>t</title></head><body><h1>页</h1></body></html>')
    expect(doc).toContain('<script>')
    expect(doc).toContain('blackboard:error')
    expect(doc.indexOf('blackboard:error')).toBeLessThan(doc.indexOf('<title>'))
    // 不重复包裹文档骨架
    expect(doc.match(/<!DOCTYPE/gi)).toHaveLength(1)
  })
  it('无 <head> 的完整文档注入到 <html> 后', () => {
    const doc = buildBoardDoc('<html><body>x</body></html>')
    expect(doc).toContain('<html><script>')
  })
  it('片段包成完整文档且脚本先执行', () => {
    const doc = buildBoardDoc('<div style="position:absolute">示意</div>')
    expect(doc.startsWith('<!DOCTYPE html>')).toBe(true)
    expect(doc).toContain('<div style="position:absolute">示意</div>')
    expect(doc.indexOf('blackboard:error')).toBeLessThan(doc.indexOf('<div'))
  })
  it('高度钳制在上下限内，非法值回退兜底', () => {
    expect(clampBoardHeight(80)).toBe(BOARD_MIN_HEIGHT)
    expect(clampBoardHeight(5000)).toBe(BOARD_MAX_HEIGHT)
    expect(clampBoardHeight(377.6)).toBe(378)
    expect(clampBoardHeight(Number.NaN)).toBe(420)
  })
  it('解析宿主消息：错误、高度、无关消息', () => {
    expect(parseBoardMessage({ type: 'blackboard:error', kind: 'promise', message: 'boom', detail: 'stack' }))
      .toEqual({ type: 'blackboard:error', kind: 'promise', message: 'boom', detail: 'stack' })
    expect(parseBoardMessage({ type: 'blackboard:error', kind: 'weird', message: 'x' }))
      .toEqual({ type: 'blackboard:error', kind: 'script', message: 'x', detail: '' })
    expect(parseBoardMessage({ type: 'blackboard:height', height: 300.4 }))
      .toEqual({ type: 'blackboard:height', height: 300.4 })
    expect(parseBoardMessage({ type: 'other' })).toBeNull()
    expect(parseBoardMessage('noise')).toBeNull()
    expect(parseBoardMessage({ type: 'blackboard:error', message: '' })).toBeNull()
  })
})
