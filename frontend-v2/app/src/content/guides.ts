import apiGuide from '../../../../docs/ai-api-guide.md?raw'
import usageGuide from '../../../../docs/getting-started.md?raw'

export type GuidePage = 'usage' | 'api'
export interface GuideSection { title: string; content: string }

function sections(raw: string): GuideSection[] {
  const text = raw.replace(/\r\n/g, '\n').replace(/^# .+\n/, '')
    .replace(/\[返回首页\]\([^\n]+\)\s*/, '').trim()
  return text.split(/\n(?=## )/).map(part => {
    const heading = part.match(/^## (.+)\n/)
    return { title: heading?.[1] ?? '从这里开始', content: heading ? part.slice(heading[0].length).trim() : part }
  })
}

// Both the in-app guide and the source documentation use the same text.
export const GUIDES: Record<GuidePage, GuideSection[]> = {
  usage: sections(usageGuide), api: sections(apiGuide),
}

export const TOUR_TITLES = [
  '欢迎使用知时', '先认识三个地方', '一起记下第一件事',
  '做完了，就打一个勾', '想用 AI？这一步可以稍后做',
  '让 AI 帮忙时，看清这三种提示', '准备好了，开始使用吧',
] as const
