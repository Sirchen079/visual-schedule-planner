import { afterAll, beforeAll, expect, it } from 'vitest'
import { createServer, type ViteDevServer } from 'vite'
import vue from '@vitejs/plugin-vue'
import { chromium, type Browser, type Page } from 'playwright'

let server: ViteDevServer, browser: Browser, origin: string
beforeAll(async () => {
  const root = decodeURIComponent(new URL('../../..', import.meta.url).pathname).replace(/^\/([A-Za-z]:\/)/, '$1')
  server = await createServer({ configFile: false, root, cacheDir: `${root}/node_modules/.vite-chat-mode-tests`, plugins: [vue(), {
    name: 'chat-mode-fixture', resolveId(id) { if (id === '/mode-entry.js') return '\0mode-entry' },
    load(id) {
      if (id !== '\0mode-entry') return
      return `import {createApp} from 'vue';import {createPinia,setActivePinia} from 'pinia';
        import Input from '/src/components/chat/ChatInput.vue';import {useConversationStore} from '/src/stores/conversation';import '/src/tokens.css';
        const pinia=createPinia();setActivePinia(pinia);const conv=useConversationStore();
        window.sent=[];window.conv=conv;
        conv.sendMessage=async(message,opts)=>{window.sent.push({message,...opts});conv.draftText='';};
        if(new URLSearchParams(window.location.search).get('bridge')==='1'){window.zhishiDesktop={selectDirectory:async()=>window.__picked};}
        createApp(Input).use(pinia).mount('#app');`
    },
    configureServer(vite) { vite.middlewares.use((req, res, next) => {
      if (((req as unknown as { url: string }).url ?? '').split('?')[0] !== '/mode-test') return next() // 剥查询串：?bridge=1 等参数要能进测试页
      res.setHeader('Content-Type', 'text/html')
      res.end('<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0;background:var(--bg-app);color:var(--ink);font-family:var(--sans)}</style></head><body><div id="app"></div><script type="module" src="/mode-entry.js"></script></body></html>')
    }) },
  }], server: { host: '127.0.0.1', port: 0 } })
  await server.listen()
  const address = server.httpServer!.address()
  origin = `http://127.0.0.1:${typeof address === 'object' && address ? address.port : 0}`
  browser = await chromium.launch({ headless: true })
}, 30000)
afterAll(async () => { await browser?.close(); await server?.close() })

it('keeps brainstorming across replies, leaves Plan one-shot, and excludes simultaneous modes', async () => {
  const page = await browser.newPage({ viewport: { width: 360, height: 640 } })
  try {
    await page.goto(`${origin}/mode-test`)
    const brain = page.getByRole('button', { name: '头脑风暴', exact: true })
    const plan = page.getByRole('button', { name: '计划', exact: true })
    const send = async (text: string) => {
      await page.locator('textarea').fill(text)
      await page.getByRole('button', { name: '发送（Enter）', exact: true }).click()
    }
    await brain.click()
    await send('我想换工作')
    await send('主要想调整工作时间')
    expect(await brain.getAttribute('aria-pressed')).toBe('true')
    await plan.click()
    expect(await brain.getAttribute('aria-pressed')).toBe('false')
    await send('给我一个执行计划')
    expect(await plan.getAttribute('data-on')).toBe(null)
    await send('正常对话')
    const sent = await page.evaluate(() => (window as any).sent)
    expect(sent.map((item: any) => [item.planMode, item.brainstormMode])).toEqual([
      [false, true], [false, true], [true, false], [false, false],
    ])
    await plan.click()
    await brain.click()
    expect(await plan.getAttribute('data-on')).toBe(null)
    await page.setViewportSize({ width: 280, height: 500 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    for (const button of [brain, plan, page.getByRole('button', { name: '发送（Enter）', exact: true })]) {
      const box = await button.boundingBox()
      expect(box!.x).toBeGreaterThanOrEqual(0)
      expect(box!.x + box!.width).toBeLessThanOrEqual(280)
    }
  } finally { await page.close() }
}, 20000)

/** 文件夹端点兜底（无真后端）：Node 侧维护一份文件夹数组，GET/POST/DELETE 全部落到这里。 */
async function stubFoldersRoute(page: Page): Promise<void> {
  const folders: Array<{ id: number; label: string; root_path: string; created_at: string }> = []
  let nextId = 1
  // 正则而非 '**/ai/conversations/*/folders*'：Playwright 的 * 不跨 /，匹配不到 DELETE 子路径 folders/{id}
  await page.route(/\/ai\/conversations\/\d+\/folders(\/\d+)?$/, route => {
    const req = route.request()
    const match = /\/ai\/conversations\/\d+\/folders(?:\/(\d+))?$/.exec(new URL(req.url()).pathname)
    if (!match) return void route.fulfill({ status: 404 })
    if (req.method() === 'GET') return void route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(folders) })
    if (req.method() === 'POST') {
      const rootPath = (JSON.parse(req.postData() ?? '{}') as { root_path?: string }).root_path ?? ''
      const row = { id: nextId++, label: rootPath.split(/[\\/]/).filter(Boolean).pop() ?? 'folder', root_path: rootPath, created_at: '2026-09-29T00:00:00' }
      folders.push(row)
      return void route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(row) })
    }
    if (req.method() === 'DELETE') {
      const index = folders.findIndex(f => f.id === Number(match[1]))
      if (index !== -1) folders.splice(index, 1)
      return void route.fulfill({ status: 204 })
    }
    return void route.fulfill({ status: 405 })
  })
}

it('folder attach: button only with desktop bridge, pick → chip, chip × → detach', async () => {
  const page = await browser.newPage({ viewport: { width: 360, height: 640 } })
  try {
    await page.goto(`${origin}/mode-test`)
    expect(await page.locator('button[title*="附加文件夹"]').count()).toBe(0) // 无桥：不渲染

    await stubFoldersRoute(page)
    await page.goto(`${origin}/mode-test?bridge=1`)
    await page.evaluate(() => {
      const w = window as any
      w.conv.activeId = 7
      w.conv.folders = []
      w.__picked = 'E:/demo'
    })
    const folderButton = page.locator('button[title="附加文件夹（知时可读取其中文件）"]')
    expect(await folderButton.count()).toBe(1)
    expect(await folderButton.isDisabled()).toBe(false)
    await folderButton.click()
    const chip = page.locator('.chip', { hasText: 'demo' })
    await chip.waitFor({ state: 'visible', timeout: 5000 }) // POST 兜底受理 → chip 出现

    await chip.locator('.chip-x').click()
    await chip.waitFor({ state: 'detached', timeout: 5000 }) // DELETE 兜底受理 → chip 消失
  } finally { await page.close() }
}, 20000)

it('folder attach: disabled without an active conversation and shows the first-message hint', async () => {
  const page = await browser.newPage({ viewport: { width: 360, height: 640 } })
  try {
    await page.goto(`${origin}/mode-test?bridge=1`)
    await page.evaluate(() => { (window as any).conv.activeId = null })
    const button = page.locator('button[title="发送第一条消息后可附加文件夹"]')
    await button.waitFor({ state: 'visible', timeout: 5000 })
    expect(await button.isDisabled()).toBe(true)
  } finally { await page.close() }
}, 20000)
