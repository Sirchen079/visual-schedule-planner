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
