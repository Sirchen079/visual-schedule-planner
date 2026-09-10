import { afterAll, beforeAll, expect, it } from 'vitest'
import { createServer, type ViteDevServer } from 'vite'
import vue from '@vitejs/plugin-vue'
import { chromium, type Browser } from 'playwright'

let server: ViteDevServer, browser: Browser, origin: string
beforeAll(async () => {
  const root = decodeURIComponent(new URL('../../..', import.meta.url).pathname).replace(/^\/([A-Za-z]:\/)/, '$1')
  server = await createServer({ configFile: false, root, plugins: [vue(), {
    name: 'diagnostics-test',
    resolveId(id) { if (id === '/diagnostics-entry.js') return '\0diagnostics-entry' },
    load(id) { if (id === '\0diagnostics-entry') return "import {createApp} from 'vue'; import Component from '/src/components/settings/DiagnosticExport.vue'; import {installDiagnostics} from '/src/utils/diagnostics.ts'; import '/src/tokens.css'; const app=createApp(Component); installDiagnostics(app); app.mount('#app')" },
    configureServer(vite) {
      vite.middlewares.use((req, res, next) => {
        if ((req as unknown as { url: string }).url !== '/diagnostics-test') return next()
        res.setHeader('Content-Type', 'text/html')
        res.end('<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{padding:16px;background:var(--bg-app);font-family:var(--sans)}#app{max-width:860px;margin:auto}</style></head><body><div id="app"></div><script type="module" src="/diagnostics-entry.js"></script></body></html>')
      })
    },
  }], server: { host: '127.0.0.1', port: 0 } })
  await server.listen()
  const address = server.httpServer!.address()
  origin = `http://127.0.0.1:${typeof address === 'object' && address ? address.port : 0}`
  browser = await chromium.launch({ headless: true })
}, 30000)
afterAll(async () => { await browser?.close(); await server?.close() })

it('downloads one local bundle, labels automatic redaction, and remains usable on mobile', async () => {
  const page = await browser.newPage({ viewport: { width: 375, height: 900 }, acceptDownloads: true })
  page.setDefaultTimeout(5000)
  let requests = 0
  await page.route('**/api/diagnostics/export', async route => {
    requests++
    await route.fulfill({ status: 200, contentType: 'application/zip',
      headers: { 'Content-Disposition': 'attachment; filename="support-test.zip"' }, body: 'PK-local-diagnostic-bundle' })
  })
  await page.goto(origin + '/diagnostics-test')
  expect(await page.getByText('日志将自动脱敏后再导出；个人数据全程保存在本地，本功能不会自动上传。').isVisible()).toBe(true)
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: '导出诊断日志' }).click()
  const file = await download
  expect(file.suggestedFilename()).toBe('support-test.zip')
  expect(await file.failure()).toBeNull()
  expect(await file.path()).toBeTruthy()
  expect(requests).toBe(1)
  expect(await page.getByRole('status').textContent()).toContain('ZIP')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.close()
})

it('shows a retryable export error and never sends error messages or personal paths', async () => {
  const page = await browser.newPage()
  page.setDefaultTimeout(5000)
  const received: Record<string, unknown>[] = []
  await page.route('**/api/diagnostics/export', route => route.fulfill({ status: 503, body: 'PRIVATE-SERVER-ERROR' }))
  await page.route('**/api/diagnostics/frontend', async route => {
    received.push(route.request().postDataJSON())
    await route.fulfill({ status: 204 })
  })
  await page.goto(origin + '/diagnostics-test')
  await page.getByRole('button', { name: '导出诊断日志' }).click()
  expect(await page.getByRole('alert').textContent()).toContain('重试')
  expect(await page.getByRole('button', { name: '导出诊断日志' }).isEnabled()).toBe(true)
  await page.evaluate(() => {
    window.dispatchEvent(new ErrorEvent('error', { error: new TypeError('SECRET-CHAT sk-secret-key'),
      message: 'SECRET-CHAT', filename: 'file:///C:/Users/PrivateName/private.js', lineno: 17, colno: 8 }))
  })
  await expect.poll(() => received.length).toBe(1)
  expect(received[0]).toEqual({ event: 'window_error', error_type: 'TypeError', asset: '', line: 17, column: 8 })
  expect(JSON.stringify(received)).not.toMatch(/SECRET|PrivateName|sk-secret-key|private.js/)
  await page.close()
})
