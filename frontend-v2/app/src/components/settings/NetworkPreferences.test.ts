import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { createServer, type ViteDevServer } from 'vite'
import vue from '@vitejs/plugin-vue'
import { chromium, type Browser, type Page } from 'playwright'

// An isolated component page with every API intercepted: no real credentials,
// service calls, settings writes, application navigation or production build.
let server: ViteDevServer, browser: Browser, origin: string
beforeAll(async () => {
  const root = decodeURIComponent(new URL('../../..', import.meta.url).pathname).replace(/^\/([A-Za-z]:\/)/, '$1')
  server = await createServer({ configFile: false, root, plugins: [vue(), {
    name: 'network-preferences-test-entry',
    resolveId(id) { if (id === '/network-test-entry.js') return '\0network-test-entry' },
    load(id) { if (id === '\0network-test-entry') return "import {createApp} from 'vue'; import Component from '/src/components/settings/NetworkPreferences.vue'; import '/src/tokens.css'; createApp(Component).mount('#app')" },
    configureServer(vite) {
      vite.middlewares.use((req, res, next) => {
        if ((req as unknown as { url: string }).url !== '/network-test') return next()
        res.setHeader('Content-Type', 'text/html')
        res.end('<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{margin:0;padding:16px;background:var(--bg-app);font-family:var(--sans)}#app{max-width:900px;margin:auto}</style></head><body><div id="app"></div><script type="module" src="/network-test-entry.js"></script></body></html>')
      })
    },
  }], server: { host: '127.0.0.1', port: 0 } })
  await server.listen()
  const address = server.httpServer!.address()
  origin = `http://127.0.0.1:${typeof address === 'object' && address ? address.port : 0}`
  browser = await chromium.launch({ headless: true })
}, 30000)
afterAll(async () => { await browser?.close(); await server?.close() })

async function fixture(fail = false) {
  const page = await browser.newPage({ viewport: { width: 375, height: 900 } })
  page.on('pageerror', e => console.error('component page:', e.message))
  page.setDefaultTimeout(4000)
  const writes: { path: string; body: any }[] = []
  const web = { config: { search_provider: 'builtin', fetch_provider: 'builtin', tavily_search_depth: 'basic', tavily_extract_depth: 'basic', mcp_search: null, mcp_fetch: null }, tavily_has_api_key: true }
  const vision = { enabled: false, server_id: null, tool_name: '', arguments: { image: '{{image_data_url}}', prompt: '{{prompt}}' } }
  await page.route('**/ai/**', async route => {
    const req = route.request(), path = new URL(req.url()).pathname
    if (fail) { await route.fulfill({ status: 503, json: { detail: '测试服务暂不可用' } }); return }
    if (req.method() !== 'GET') writes.push({ path, body: req.postDataJSON() })
    let data: unknown = {}
    if (path === '/ai/web-services') data = req.method() === 'PUT' ? { ...web, config: req.postDataJSON() } : web
    if (path === '/ai/vision') data = req.method() === 'PUT' ? req.postDataJSON() : vision
    if (path.endsWith('/credentials/tavily')) data = { tavily_has_api_key: req.method() !== 'DELETE' }
    if (path === '/ai/mcp/servers') data = [
      { id: 1, name: '视觉与网页工具', transport: 'http', enabled: true, trusted: false, auto_approve_readonly: true },
      { id: 2, name: '未信任本地服务', transport: 'stdio', enabled: true, trusted: false, auto_approve_readonly: true },
    ]
    if (path.endsWith('/tools')) data = [{ name: 'inspect', description: '识别图片内容', read_only: true, input_schema: { required: ['image', 'prompt'] } }, { name: 'write', description: '', read_only: false }]
    await route.fulfill({ json: data })
  })
  await page.goto(`${origin}/network-test`)
  await page.locator('#network-preferences-root').waitFor()
  return { page, writes }
}
async function hasText(page: Page, text: string) { await page.getByText(text, { exact: true }).waitFor() }

describe('NetworkPreferences interactions', () => {
  it('saves builtin defaults independently, preserves blank credentials and fits narrow screens', async () => {
    const { page, writes } = await fixture()
    try {
      await page.locator('#network-web-save').click()
      await hasText(page, '搜索与网页读取设置已保存')
      expect(writes[0].body).toMatchObject({ search_provider: 'builtin', fetch_provider: 'builtin' })
      await page.getByRole('button', { name: '保存密钥', exact: true }).click()
      await hasText(page, '已保留现有密钥')
      expect(writes).toHaveLength(1)
      expect(await page.locator('#network-tavily-key').inputValue()).toBe('')
      expect(await page.locator('#network-tavily-key').getAttribute('type')).toBe('password')
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    } finally { await page.close() }
  })
  it('requires readonly tools and valid image templates, then saves explicit vision consent', async () => {
    const { page, writes } = await fixture()
    try {
      await page.locator('#network-vision-enabled').check()
      await page.locator('#network-vision-server').selectOption('1')
      await page.locator('#network-vision-tool option[value="inspect"]').waitFor({ state: 'attached' })
      expect(await page.locator('#network-vision-server option[value="2"]').getAttribute('disabled')).not.toBeNull()
      expect(await page.locator('#network-vision-tool option[value="write"]').getAttribute('disabled')).not.toBeNull()
      await page.locator('#network-vision-tool').selectOption('inspect')
      await page.locator('section').filter({ has: page.locator('#network-vision-title') }).locator('summary').first().click()
      await page.locator('#network-vision-arguments').fill('{broken')
      await page.locator('#network-vision-save').click()
      await hasText(page, '视觉参数须为有效 JSON，请检查引号和逗号')
      expect(writes).toHaveLength(0)
      await page.locator('#network-vision-arguments').fill('{"image":"{{image_data_url}}","prompt":"{{prompt}}"}')
      await page.locator('#network-vision-save').click()
      await hasText(page, '视觉补充已启用；后续符合条件的图片会发送至所选服务')
      expect(writes[0]).toMatchObject({ path: '/ai/vision', body: { enabled: true, server_id: 1, tool_name: 'inspect' } })
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    } finally { await page.close() }
  })
  it('contains new endpoint failures inside the component with retry controls', async () => {
    const { page } = await fixture(true)
    try {
      await page.getByRole('button', { name: '重新读取', exact: true }).first().waitFor()
      expect(await page.getByRole('button', { name: '重新读取', exact: true }).count()).toBe(2)
      expect(await page.locator('#network-web-save').count()).toBe(0)
    } finally { await page.close() }
  })
})
