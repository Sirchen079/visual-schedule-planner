import { afterAll, beforeAll, expect, it } from 'vitest'
import { createServer, type ViteDevServer } from 'vite'
import vue from '@vitejs/plugin-vue'
import { chromium, type Browser, type Page } from 'playwright'

let server: ViteDevServer, browser: Browser, origin: string
beforeAll(async () => {
  const root = decodeURIComponent(new URL('../../..', import.meta.url).pathname).replace(/^\/([A-Za-z]:\/)/, '$1')
  server = await createServer({ configFile: false, root, cacheDir: `${root}/node_modules/.vite-chat-attachment-tests`, plugins: [vue(), {
    name: 'chat-input-test',
    resolveId(id) { if (id === '/input-entry.js') return '\0input-entry' },
    load(id) { if (id === '\0input-entry') return "import {createApp} from 'vue'; import {createPinia} from 'pinia'; import Component from '/src/components/chat/ChatInput.vue'; import {useConversationStore} from '/src/stores/conversation'; import '/src/tokens.css'; const app=createApp(Component); app.use(createPinia()); window.conv=useConversationStore(); app.mount('#app')" },
    configureServer(vite) {
      vite.middlewares.use((req, res, next) => {
        if ((req as unknown as { url: string }).url !== '/input-test') return next()
        res.setHeader('Content-Type', 'text/html')
        res.end('<div id="app"></div><script type="module" src="/input-entry.js"></script>')
      })
    },
  }], server: { host: '127.0.0.1', port: 0 } })
  await server.listen()
  const address = server.httpServer!.address()
  origin = `http://127.0.0.1:${typeof address === 'object' && address ? address.port : 0}`
  browser = await chromium.launch({ headless: true })
}, 30000)
afterAll(async () => { await browser?.close(); await server?.close() })

async function paste(page: Page, names: string[], text = '') {
  return page.locator('textarea').evaluate((el, data) => {
    const transfer = new DataTransfer()
    for (const name of data.names) transfer.items.add(new File(['image bytes'], name, { type: 'image/png' }))
    if (data.text) transfer.setData('text/plain', data.text)
    return el.dispatchEvent(new ClipboardEvent('paste', { clipboardData: transfer, bubbles: true, cancelable: true }))
  }, { names, text })
}

it('pastes image once, shows first-upload progress, preserves mixed text and permits retry', async () => {
  const page = await browser.newPage()
  let uploads = 0, release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  await page.route('**/ai/attachments', async route => {
    uploads++
    expect(route.request().postDataBuffer()?.toString()).toContain('image/png')
    if (uploads === 1) await gate
    await route.fulfill({ json: { file_id: uploads, name: `截图${uploads}.png` } })
  })
  try {
    await page.goto(origin + '/input-test')
    await page.locator('textarea').fill('已有草稿')
    expect(await paste(page, [], '普通文字')).toBe(true)
    expect(await paste(page, ['image.png'], '附带说明')).toBe(false)
    await page.getByRole('status').waitFor()
    expect(await page.locator('textarea').inputValue()).toBe('已有草稿附带说明')
    expect(await page.getByTitle('发送（Enter）').isDisabled()).toBe(true)
    release()
    await page.getByTitle('移除附件 截图1.png').waitFor()
    expect(uploads).toBe(1)
    await paste(page, ['image.png'])
    await page.getByTitle('移除附件 截图2.png').waitFor()
    expect(uploads).toBe(2)
    await page.getByTitle('移除附件 截图1.png').click()
    expect(await page.locator('.chip-x').count()).toBe(1)
    await page.route('**/ai/attachments', route => route.fulfill({ status: 413, json: { detail: '文件太大' } }))
    await paste(page, ['large.png'])
    await page.locator('.microtext').waitFor()
    expect(await page.locator('textarea').inputValue()).toContain('已有草稿')
    expect(await page.locator('.chip-x').count()).toBe(1)
    expect(await page.getByRole('status').count()).toBe(0)
  } finally { release(); await page.close() }
})

it('accepts multiple dropped and selected files, blocks file navigation while busy', async () => {
  const page = await browser.newPage()
  let uploads = 0
  await page.route('**/ai/attachments', route => route.fulfill({ json: { file_id: ++uploads, name: `附件${uploads}` } }))
  try {
    await page.goto(origin + '/input-test')
    await page.locator('textarea').waitFor()
    const drop = () => page.locator('.inputbox').evaluate(el => {
      const transfer = new DataTransfer()
      for (const name of ['a.png', 'b.png']) transfer.items.add(new File(['x'], name, { type: 'image/png' }))
      el.dispatchEvent(new DragEvent('dragover', { dataTransfer: transfer, bubbles: true, cancelable: true }))
      return el.dispatchEvent(new DragEvent('drop', { dataTransfer: transfer, bubbles: true, cancelable: true }))
    })
    expect(await drop()).toBe(false)
    await page.getByTitle('移除附件 附件2').waitFor()
    await page.locator('input[type=file]').evaluate(el => {
      const transfer = new DataTransfer()
      for (const name of ['c.txt', 'd.txt']) transfer.items.add(new File(['text'], name, { type: 'text/plain' }))
      ;(el as HTMLInputElement).files = transfer.files
      el.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await page.getByTitle('移除附件 附件4').waitFor()
    await page.evaluate(() => { (window as any).conv.loading = true })
    expect(await drop()).toBe(false)
    await page.getByText('请等待当前操作结束后再添加附件。').waitFor()
    expect(uploads).toBe(4)
    expect(page.url()).toBe(origin + '/input-test')
  } finally { await page.close() }
})
