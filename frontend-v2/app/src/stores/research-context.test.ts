import { afterEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useRunStore } from './run'

afterEach(() => vi.unstubAllGlobals())
it('carries the selected learning project for one request and omits it after leaving the project', async () => {
  setActivePinia(createPinia())
  const bodies: Record<string, unknown>[] = []
  vi.stubGlobal('fetch', vi.fn(async (_url: unknown, init: RequestInit) => {
    bodies.push(JSON.parse(String(init.body)))
    return new Response('event: done\ndata: {"v":1,"type":"done","run_id":"r"}\n\n', { headers: { 'Content-Type': 'text/event-stream' } })
  }))
  const run = useRunStore()
  await run.sendMessage('这个项目明天开始', { researchProjectId: 7 })
  expect(bodies[0].research_project_id).toBe(7)
  await run.sendMessage('记一下今天的支出')
  expect(bodies[1]).not.toHaveProperty('research_project_id')
})
