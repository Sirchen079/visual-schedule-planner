import { describe, expect, it } from 'vitest'
import { attachmentKindLabel } from './ai'

/** 附件解析类型文案：后端 detect_media/parse 的 kind，Markdown 管道升级后新增 pptx。 */
describe('attachmentKindLabel（附件解析类型映射）', () => {
  it('已知类型映射：含新增的 pptx', () => {
    expect(attachmentKindLabel('pptx')).toBe('PPT')
    expect(attachmentKindLabel('pdf')).toBe('PDF')
    expect(attachmentKindLabel('docx')).toBe('Word')
    expect(attachmentKindLabel('xlsx')).toBe('Excel')
    expect(attachmentKindLabel('csv')).toBe('CSV')
    expect(attachmentKindLabel('text')).toBe('文本')
    expect(attachmentKindLabel('image')).toBe('图片')
    expect(attachmentKindLabel('audio')).toBe('音频')
    expect(attachmentKindLabel('video')).toBe('视频')
    expect(attachmentKindLabel('failed')).toBe('解析失败')
  })

  it('未知类型保留原值', () => {
    expect(attachmentKindLabel('weird')).toBe('weird')
  })
})
