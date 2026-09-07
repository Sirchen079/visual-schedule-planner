import { beforeEach, afterEach, it, expect, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useRunStore } from './run'
import type { UserInputRequest } from '../api/userInput'
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
const question = (): UserInputRequest => ({ id: 9, run_id: 'r1', call_id: 'q1', version: 0, status: 'pending', answer: {},
  questions: [{ id: 'scope', question: '选范围', options: [{ label: '今天', description: '' }], multi_select: false }] })
beforeEach(() => { setActivePinia(createPinia()); const run = useRunStore(); run.reset(1); run.runId = 'r1'; run.phase = 'awaiting_input'; run.questionRequests = [question()] })
afterEach(() => { useRunStore().reset(null); vi.unstubAllGlobals() })

it('respects server readiness even when no local approval cards are visible', async () => {
  const run = useRunStore(), calls: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string) => { calls.push(url); return json({ request: { ...question(), status: 'answered', version: 1 }, ready_to_resume: false }) }))
  await run.answerQuestion(9, { scope: { selected: ['今天'], text: '' } })
  expect(calls).toEqual(['/ai/conversations/1/questions/9/answer'])
  expect(run.questionRequests[0].status).toBe('answered')
})

it('late answers cannot resume or change another conversation', async () => {
  const run = useRunStore()
  let resolve!: (response: Response) => void
  const pending = new Promise<Response>(r => { resolve = r })
  const fetch = vi.fn(() => pending); vi.stubGlobal('fetch', fetch)
  const answer = run.answerQuestion(9, { scope: { selected: ['今天'], text: '' } })
  run.reset(2); run.runId = 'r2'; run.notice = '当前第二个会话'
  resolve(json({ request: { ...question(), status: 'answered' }, ready_to_resume: true }))
  await answer
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(run.conversationId).toBe(2)
  expect(run.notice).toBe('当前第二个会话')
})

it('deduplicates answer clicks and retains a failed question for retry', async () => {
  const run = useRunStore()
  let resolve!: (response: Response) => void
  const fetch = vi.fn(() => new Promise<Response>(r => { resolve = r })); vi.stubGlobal('fetch', fetch)
  const answer = run.answerQuestion(9, { scope: { selected: ['今天'], text: '' } })
  await run.answerQuestion(9, {}, true)
  expect(fetch).toHaveBeenCalledTimes(1)
  resolve(json({ detail: '模拟网络错误' }, 503)); await answer
  expect(run.questionRequests[0].status).toBe('pending')
  expect(run.questionRequests[0].busy).toBe(false)
  expect(run.error?.message).toContain('模拟网络错误')
})
