// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { createApp } from 'vue'
import { createPinia, getActivePinia, setActivePinia } from 'pinia'
import QueueBar from './QueueBar.vue'
import { useConversationStore } from '../../stores/conversation'
import type { SteerEntry } from '../../stores/conversation'

/** QueueBar 渲染逻辑：空队列不渲染；插话条目带待注入/已注入标签与条件撤回；待发队列逐行删除。 */

type VueApp = ReturnType<typeof createApp>
let app: VueApp | null = null
let host: HTMLElement | null = null

function mountQueueBar(): HTMLElement {
  host = document.createElement('div')
  document.body.appendChild(host)
  // 复用当前激活的 pinia：测试先在 active pinia 里准备 store，再挂载组件
  app = createApp(QueueBar).use(getActivePinia()!)
  app.mount(host)
  return host
}

afterEach(() => {
  app?.unmount()
  app = null
  host?.remove()
  host = null
  document.body.innerHTML = ''
})

describe('QueueBar', () => {
  it('队列为空时不渲染', () => {
    setActivePinia(createPinia())
    const root = mountQueueBar()
    expect(root.querySelector('.queue-bar')).toBeNull()
  })

  it('逐行预览待发消息（换行压平）并可单条删除', async () => {
    setActivePinia(createPinia())
    const conv = useConversationStore()
    conv.activeId = 1
    conv.enqueueMessage('第一句\n带换行')
    conv.enqueueMessage('第二句')
    const root = mountQueueBar()

    const bar = root.querySelector('.queue-bar')
    expect(bar).not.toBeNull()
    expect(bar!.textContent).toContain('待发送 · 2')
    expect(root.querySelectorAll('.queue-item')).toHaveLength(2)
    // 单行预览：换行压成空格
    expect(root.querySelector('.queue-text')!.textContent).toBe('第一句 带换行')

    // 删除第二条
    const second = root.querySelectorAll<HTMLButtonElement>('.queue-x')[1]!
    second.click()
    await Promise.resolve()
    expect(conv.queuedMessages).toEqual(['第一句\n带换行'])

    // 全部删完后整个条不再渲染
    root.querySelector<HTMLButtonElement>('.queue-x')!.click()
    await Promise.resolve()
    expect(conv.queuedMessages).toEqual([])
    expect(root.querySelector('.queue-bar')).toBeNull()
  })

  it('插话条目：待注入/已注入标签；仅 POST 尚未返回的条目可撤回', async () => {
    setActivePinia(createPinia())
    const conv = useConversationStore()
    conv.activeId = 1
    const entries: SteerEntry[] = [
      { token: 't-pending', text: '还在发送中', runId: null, messageId: null }, // POST 在途 → 可撤回
      { token: 't-accepted', text: '已受理待注入', runId: 'r1', messageId: null }, // 已受理 → 不可撤回
      { token: 't-confirmed', text: '已注入落库', runId: 'r1', messageId: 55 }, // 已确认 → 不可撤回
    ]
    conv.steerEntries = entries
    const root = mountQueueBar()

    const bar = root.querySelector('.queue-bar')
    expect(bar).not.toBeNull()
    expect(bar!.textContent).toContain('插话 · 3')
    expect(bar!.textContent).not.toContain('待发送')

    const tags = [...root.querySelectorAll('.steer-tag')]
    expect(tags.map((t) => t.textContent)).toEqual(['待注入', '待注入', '已注入'])
    expect(tags[2]!.hasAttribute('data-confirmed')).toBe(true)

    // 撤回按钮：仅 POST 在途的条目可用
    const buttons = [...root.querySelectorAll<HTMLButtonElement>('.queue-x')]
    expect(buttons.map((b) => b.disabled)).toEqual([false, true, true])

    // 撤回在途条目：从 store 移除
    buttons[0]!.click()
    await Promise.resolve()
    expect(conv.steerEntries.map((e) => e.token)).toEqual(['t-accepted', 't-confirmed'])
  })

  it('插话与待发队列并存时分区展示', () => {
    setActivePinia(createPinia())
    const conv = useConversationStore()
    conv.activeId = 1
    conv.steerEntries = [{ token: 't1', text: '插话', runId: 'r1', messageId: null }]
    conv.enqueueMessage('排队消息')
    const root = mountQueueBar()

    const bar = root.querySelector('.queue-bar')!
    expect(bar.textContent).toContain('插话 · 1')
    expect(bar.textContent).toContain('待发送 · 1')
    expect(root.querySelectorAll('.queue-item')).toHaveLength(2)
  })
})
