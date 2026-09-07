import { afterAll, beforeAll, expect, it } from 'vitest'
import { createServer, type ViteDevServer } from 'vite'
import vue from '@vitejs/plugin-vue'
import { chromium, type Browser } from 'playwright'

let server: ViteDevServer, browser: Browser, origin: string
beforeAll(async () => {
  const root = decodeURIComponent(new URL('../../..', import.meta.url).pathname).replace(/^\/([A-Za-z]:\/)/, '$1')
  server = await createServer({ configFile: false, root, cacheDir: `${root}/node_modules/.vite-help-tests`, plugins: [vue(), {
    name: 'help-ui-fixture', resolveId(id) { if (id === '/help-entry.js') return '\0help-entry' },
    load(id) {
      if (id !== '\0help-entry') return
      return `import {createApp,h} from 'vue';import {createPinia,setActivePinia} from 'pinia';
        import {createRouter,createMemoryHistory} from 'vue-router';
        import Help from '/src/components/help/HelpCenter.vue';import {useHelpStore} from '/src/stores/help';import '/src/tokens.css';
        const pinia=createPinia();setActivePinia(pinia);const help=useHelpStore();
        const router=createRouter({history:createMemoryHistory(),routes:[{path:'/:pathMatch(.*)*',component:{render:()=>null}}]});
        window.probe={help,router};
        createApp({render:()=>h('main',[h('button',{id:'open-guide',onClick:()=>help.openGuide()},'使用教程'),
          h('button',{id:'open-tour',onClick:()=>help.startTour()},'新手指引'),h(Help)])}).use(pinia).use(router).mount('#app');
        help.initialize();`
    },
    configureServer(vite) { vite.middlewares.use((req, res, next) => {
      if ((req as unknown as { url: string }).url !== '/help-test') return next()
      res.setHeader('Content-Type', 'text/html')
      res.end('<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0;padding:16px;background:var(--bg-app);color:var(--ink);font-family:var(--sans)}</style></head><body><div id="app"></div><script type="module" src="/help-entry.js"></script></body></html>')
    }) },
  }], server: { host: '127.0.0.1', port: 0 } })
  await server.listen()
  const address = server.httpServer!.address()
  origin = `http://127.0.0.1:${typeof address === 'object' && address ? address.port : 0}`
  browser = await chromium.launch({ headless: true })
}, 30000)
afterAll(async () => { await browser?.close(); await server?.close() })

async function fixture(fresh = true, width = 1100) {
  const page = await browser.newPage({ viewport: { width, height: 820 } })
  page.setDefaultTimeout(10000)
  let state = fresh ? 'pending' : 'existing'
  const writes: unknown[] = []
  await page.route('**/api/settings/onboarding', async route => {
    if (route.request().method() === 'POST') state = route.request().postDataJSON().outcome
    await route.fulfill({ json: { status: state, has_history: !fresh, show_automatically: state === 'pending' } })
  })
  await page.route('**/api/tasks', async route => {
    writes.push(route.request().postDataJSON())
    await route.fulfill({ status: 201, json: { id: 1, title: (writes[0] as { title: string }).title } })
  })
  await page.goto(`${origin}/help-test`)
  return { page, writes }
}

it('walks through a real first task, returns from API help, and persists completion', async () => {
  const { page, writes } = await fixture()
  try {
    const tour = page.getByRole('dialog', { name: '新手指引', exact: true })
    await tour.getByRole('heading', { name: '欢迎使用知时' }).waitFor()
    expect(writes).toHaveLength(0)
    await tour.getByRole('button', { name: '开始，一步步来' }).click()
    await tour.getByRole('button', { name: '下一步' }).click()
    expect(await tour.getByRole('button', { name: '② 保存这条待办' }).isDisabled()).toBe(true)
    await tour.getByLabel('① 点这里，输入待办名称').fill('第一次练习的真实待办')
    await tour.getByRole('button', { name: '② 保存这条待办' }).click()
    await tour.getByText('保存成功！关闭指引后，在“看板”里就能找到它。', { exact: true }).waitFor()
    expect(writes).toEqual([{ title: '第一次练习的真实待办' }])
    await tour.getByRole('button', { name: '下一步' }).click()
    await tour.getByRole('button', { name: '下一步' }).click()
    await tour.getByRole('button', { name: '已有资料，教我怎么填写' }).click()
    const guide = page.getByRole('dialog', { name: '使用教程', exact: true })
    await guide.getByRole('heading', { name: '一步步配置' }).waitFor()
    await guide.getByRole('button', { name: '返回新手指引' }).click()
    await tour.getByRole('heading', { name: '想用 AI？这一步可以稍后做' }).waitFor()
    await tour.getByRole('button', { name: '下一步' }).click()
    await tour.getByRole('button', { name: '下一步' }).click()
    await tour.getByRole('button', { name: '开始使用，打开看板' }).click()
    await page.waitForFunction(() => (window as any).probe.router.currentRoute.value.path === '/board')
    await page.reload()
    await page.waitForFunction(() => (window as any).probe.help.initialized)
    expect(await page.getByRole('dialog').count()).toBe(0)
  } finally { await page.close() }
}, 30000)

it('skipping works on a small screen, preserves focus, and can be replayed manually', async () => {
  const { page, writes } = await fixture(true, 375)
  try {
    const tour = page.getByRole('dialog', { name: '新手指引', exact: true })
    await tour.waitFor()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const rect = await tour.boundingBox()
    expect(rect!.width).toBeLessThanOrEqual(375)
    await tour.getByRole('button', { name: '暂时跳过' }).click()
    await page.reload(); await page.waitForFunction(() => (window as any).probe.help.initialized)
    expect(await page.getByRole('dialog').count()).toBe(0)
    await page.locator('#open-tour').click()
    await tour.waitFor()
    for (let index = 0; index < 8; index++) await page.keyboard.press('Tab')
    expect(await tour.evaluate(element => element.contains(document.activeElement))).toBe(true)
    await page.keyboard.press('Escape')
    expect(await page.locator('#open-tour').evaluate(element => element === document.activeElement)).toBe(true)
    expect(writes).toHaveLength(0)
  } finally { await page.close() }
})

it('upgrades remain quiet and all bundled API chapters can be read offline', async () => {
  const { page } = await fixture(false, 760)
  try {
    await page.waitForFunction(() => (window as any).probe.help.initialized)
    expect(await page.getByRole('dialog').count()).toBe(0)
    await page.context().setOffline(true)
    await page.locator('#open-guide').click()
    const guide = page.getByRole('dialog', { name: '使用教程', exact: true })
    await guide.getByRole('tab', { name: 'AI 接入', exact: true }).click()
    await guide.getByRole('button', { name: '一步步配置' }).click()
    await guide.getByRole('heading', { name: '一步步配置' }).waitFor()
    expect(await guide.locator('.guide-prose').innerText()).toContain('获取模型列表')
    await guide.getByRole('button', { name: '三种接口格式怎么选' }).click()
    expect(await guide.locator('table').innerText()).toContain('Anthropic')
    expect(await guide.locator('a').first().getAttribute('target')).toBe('_blank')
    await guide.getByRole('button', { name: '打开 AI 模型设置' }).click()
    await page.waitForFunction(() => (window as any).probe.router.currentRoute.value.query.section === 'configs')
  } finally { await page.close() }
})
