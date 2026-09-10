import { afterAll, beforeAll, expect, it } from 'vitest'
import { createServer, type ViteDevServer } from 'vite'
import vue from '@vitejs/plugin-vue'
import { chromium, type Browser } from 'playwright'

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
        createApp(Input).use(pinia).mount('#app');`
    },
    configureServer(vite) { vite.middlewares.use((req, res, next) => {
      if ((req as unknown as { url: string }).url !== '/mode-test') return next()
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
