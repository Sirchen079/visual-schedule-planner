// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { createApp } from 'vue'
import { createPinia, getActivePinia, setActivePinia } from 'pinia'
import QueueBar from './QueueBar.vue'
import { useConversationStore } from '../../stores/conversation'

/** QueueBar 渲染逻辑：空队列不渲染；有条目时逐行预览并可单条删除。 */

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
})
