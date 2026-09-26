import { afterAll, beforeAll, expect, it } from 'vitest'
import { createServer, type ViteDevServer } from 'vite'
import vue from '@vitejs/plugin-vue'
import { chromium, type Browser } from 'playwright'

let server: ViteDevServer, browser: Browser, origin: string
beforeAll(async () => {
  const root = decodeURIComponent(new URL('../../..', import.meta.url).pathname).replace(/^\/([A-Za-z]:\/)/, '$1')
  server = await createServer({ configFile: false, root, cacheDir: `${root}/node_modules/.vite-skill-import-tests`, plugins: [vue(), {
    name: 'skill-import-test',
    resolveId(id) { if (id === '/skill-entry.js') return '\0skill-entry' },
    load(id) { if (id === '\0skill-entry') return "import {createApp,h} from 'vue'; import Component from '/src/components/settings/SkillImport.vue'; import '/src/tokens.css'; window.imports=0; createApp({render:()=>h(Component,{onImported:()=>window.imports++})}).mount('#app')" },
    configureServer(vite) {
      vite.middlewares.use((req, res, next) => {
        if ((req as unknown as { url: string }).url !== '/skill-test') return next()
        res.setHeader('Content-Type', 'text/html')
        res.end('<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{padding:16px;background:var(--bg-app);font-family:var(--sans)}#app{max-width:860px;margin:auto}</style></head><body><div id="app"></div><script type="module" src="/skill-entry.js"></script></body></html>')
      })
    },
  }], server: { host: '127.0.0.1', port: 0 } })
  await server.listen()
  const address = server.httpServer!.address()
  origin = `http://127.0.0.1:${typeof address === 'object' && address ? address.port : 0}`
  browser = await chromium.launch({ headless: true })
}, 30000)
afterAll(async () => { await browser?.close(); await server?.close() })

it('uploads a skill pack, requires choosing a candidate and preserves the selected path', async () => {
  const page = await browser.newPage({ viewport: { width: 390, height: 900 } })
  page.setDefaultTimeout(6000)
  const uploads: string[] = []
  await page.route('**/ai/skills/import/upload', async route => {
    uploads.push(route.request().postData() || '')
    await route.fulfill({ json: uploads.length === 1
      ? { status: 'select_skill', candidates: [{ name: 'report', path: 'repo/report/SKILL.md', description: 'Weekly reporting', error: '' }, { name: 'plan', path: 'repo/plan/SKILL.md', description: 'Planning', error: '' }], warnings: [] }
      : { status: 'imported', skill_id: 7, name: 'report', enabled: true, candidates: [], warnings: [] } })
  })
  await page.goto(origin + '/skill-test')
  await page.locator('summary').click()
  await page.locator('input[type=file]').first().evaluate(element => {
    const transfer = new DataTransfer()
    transfer.items.add(new File(['test-package'], 'skills.zip', { type: 'application/zip' }))
    ;(element as HTMLInputElement).files = transfer.files
    element.dispatchEvent(new Event('change', { bubbles: true }))
  })
  await page.getByRole('combobox').selectOption('repo/report/SKILL.md')
  await page.getByRole('button', { name: '导入所选技能' }).click()
  await expect.poll(() => page.getByRole('status').textContent()).toContain('已导入：report')
  expect(uploads[1]).toContain('repo/report/SKILL.md')
  expect(uploads[1]).toContain('filename="skills.zip"')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.close()
})

it('keeps GitHub source after a conflict and retries with an explicit new name', async () => {
  const page = await browser.newPage()
  const requests: Record<string, unknown>[] = []
  await page.route('**/ai/skills/import/github', async route => {
    requests.push(route.request().postDataJSON())
    await route.fulfill(requests.length === 1
      ? { status: 409, json: { detail: '已有同名技能，请填写新名称后导入' } }
      : { json: { status: 'imported', skill_id: 8, name: 'my-report', enabled: true, candidates: [], warnings: [] } })
  })
  await page.goto(origin + '/skill-test')
  await page.locator('summary').click()
  await page.getByLabel('GitHub 链接').fill('https://github.com/acme/report')
  await page.getByRole('button', { name: '从 GitHub 导入' }).click()
  await expect.poll(() => page.getByRole('alert').textContent()).toContain('同名')
  await page.getByLabel('另存名称', { exact: false }).fill('my-report')
  await page.getByRole('button', { name: '重试导入' }).click()
  await expect.poll(() => page.getByRole('status').textContent()).toContain('my-report')
  expect(requests[1]).toMatchObject({ url: 'https://github.com/acme/report', name: 'my-report' })
  await page.close()
})
