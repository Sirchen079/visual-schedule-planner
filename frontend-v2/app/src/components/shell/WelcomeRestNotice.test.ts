import { afterEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp } from 'vue'
import { createPinia } from 'pinia'
import { renderToString } from '@vue/server-renderer'
import WelcomeRestNotice from './WelcomeRestNotice.vue'
import { useFocusStore } from '../../stores/focus'

async function render(seconds: number, kind = 'focus', hour = 10, dismissed = false) {
  vi.useFakeTimers()
  vi.setSystemTime(new Date(2026, 8, 19, hour, 0, 0))
  vi.stubGlobal('localStorage', { getItem: () => dismissed ? '1' : null })
  const pinia = createPinia()
  const focus = useFocusStore(pinia)
  focus.current = { id: 1, task_id: null, task_title: '', kind,
    started_at: new Date(Date.now() - seconds * 1000).toISOString(), ended_at: null, minutes: 0 }
  focus.now = Date.now()
  return renderToString(createSSRApp(WelcomeRestNotice).use(pinia))
}
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })
describe('顶部问候与休息提醒', () => {
  it('89:59 不提醒，90:00 提醒', async () => {
    expect(await render(5399)).not.toContain('该歇一歇了')
    expect(await render(5400)).toContain('该歇一歇了')
  })
  it('休息计时不触发工作提醒', async () => {
    expect(await render(7200, 'break')).not.toContain('该歇一歇了')
  })
  it('已关闭的专注提醒刷新后不重复显示', async () => {
    expect(await render(7200, 'focus', 10, true)).not.toContain('该歇一歇了')
  })
  it('夜间显示早点休息的问候', async () => {
    expect(await render(0, 'focus', 23)).toContain('夜深了，早点休息吧')
  })
})
