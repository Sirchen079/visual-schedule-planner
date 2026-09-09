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
        import {createRouter,createMemoryHistory,RouterView,RouterLink} from 'vue-router';
        import Board from '/src/views/BoardView.vue';import Help from '/src/components/help/HelpCenter.vue';import {useHelpStore} from '/src/stores/help';import '/src/tokens.css';
        const pinia=createPinia();setActivePinia(pinia);const help=useHelpStore();
        const router=createRouter({history:createMemoryHistory(),routes:[{path:'/board',component:Board},{path:'/:pathMatch(.*)*',component:{render:()=>null}}]});
        window.probe={help,router};
        createApp({render:()=>h('main',[h('button',{id:'open-guide',onClick:()=>help.openGuide()},'使用教程'),
          h('button',{id:'open-tour',onClick:()=>help.startTour()},'新手指引'),h(RouterLink,{to:'/calendar','data-tour':'nav-calendar'},()=> '日历'),h(RouterLink,{to:'/settings','data-tour':'nav-settings'},()=> '设置'),h('div',{id:'head-actions',style:'display:flex;justify-content:flex-end;margin-top:50px'}),h(RouterView),h(Help)])}).use(pinia).use(router).mount('#app');
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

it('covers every feature with searchable instructions and preserves the learning step', async () => {
  const { page, writes } = await fixture(false, 760)
  try {
    await page.locator('#open-guide').click()
    const guide = page.getByRole('dialog', { name: '使用教程', exact: true })
    const tour = page.getByRole('dialog', { name: '新手指引', exact: true })
    await guide.getByLabel('搜索教程').fill('付款')
    await guide.getByRole('button', { name: '账本：记收支，也管待付账单' }).click()
    await guide.getByRole('heading', { name: '账本：记收支，也管待付账单' }).waitFor()
    await guide.getByRole('button', { name: '打开实际页面' }).click()
    const options = await tour.getByLabel('学习目录').locator('option').allTextContents()
    expect(options).toHaveLength(17) // prompt + task exercise + 15 feature entries
    for (let index = 0; index < 15; index++) {
      await tour.getByLabel('学习目录').selectOption(String(5 + index))
      await tour.getByRole('button', { name: '打开栏目，跟着学' }).click()
      expect(await tour.locator('.lesson-steps li').count()).toBe(4)
      const title = await tour.getByRole('heading').innerText()
      await tour.getByRole('button', { name: '完整操作教程', exact: true }).click()
      expect(await guide.locator('.guide-prose').innerText()).toContain('操作后怎么核对')
      expect(await guide.getByRole('heading').innerText()).toContain(title.split(' · ')[0])
      await guide.getByRole('button', { name: '返回新手指引' }).click()
      expect(await tour.getByRole('heading').innerText()).toBe(title)
      await tour.getByRole('button', { name: '收起提示，按步骤操作' }).click()
      expect(await tour.count()).toBe(0)
      await page.locator('.resume-lesson').click()
      expect(await tour.getByRole('heading').innerText()).toBe(title)
      await tour.getByRole('button', { name: '看过了' }).click()
    }
    await tour.getByRole('heading', { name: '随时回来，按需要继续学' }).waitFor()
    expect(await tour.innerText()).toContain('已看过 15 / 15 个栏目')
    expect(writes).toHaveLength(0)
  } finally { await page.close() }
}, 30000)

async function fixture(fresh = true, width = 1100) {
  const page = await browser.newPage({ viewport: { width, height: 820 } })
  page.setDefaultTimeout(10000)
  let state = fresh ? 'pending' : 'existing'
  const writes: unknown[] = []
  await page.route('**/api/settings/onboarding', async route => {
    if (route.request().method() === 'POST') state = route.request().postDataJSON().outcome
    await route.fulfill({ json: { status: state, has_history: !fresh, show_automatically: state === 'pending' } })
  })
  const records: unknown[] = []
  await page.route('**/api/tasks', async route => {
    if (route.request().method() === 'GET') { await route.fulfill({ json: records }); return }
    writes.push(route.request().postDataJSON())
    const record = { id: writes.length, ...route.request().postDataJSON(), status: 'todo', subtasks: [], due_time: null }
    records.push(record)
    await route.fulfill({ status: 201, json: record })
  })
  await page.goto(`${origin}/help-test`)
  return { page, writes }
}

it('points to actual board controls, saves once and resumes from API help', async () => {
  const { page, writes } = await fixture()
  try {
    const tour = page.getByRole('dialog', { name: '新手指引', exact: true })
    await tour.getByRole('heading', { name: '欢迎使用知时' }).waitFor()
    expect(writes).toHaveLength(0)
    await tour.getByRole('button', { name: '开始，一步步来' }).click()
    await page.getByRole('button', { name: '新建任务', exact: true }).click()
    await tour.getByRole('heading', { name: '写下你要做的事' }).waitFor()
    expect(await tour.getByRole('button', { name: '填好了' }).isDisabled()).toBe(true)
    await page.getByLabel('任务标题', { exact: true }).fill('取快递')
    await tour.getByRole('button', { name: '填好了' }).click()
    await page.getByRole('button', { name: '创建', exact: true }).click()
    await tour.getByRole('heading', { name: '保存成功，在这里能找到它' }).waitFor()
    expect(writes).toEqual([{ title: '取快递', due_date: null, priority: 'medium' }])
    expect(await page.locator('[data-tour-task="1"]').innerText()).toContain('取快递')
    await tour.getByRole('button', { name: '下一步' }).click()
    await tour.getByRole('heading', { name: '对话 · 用来做什么' }).waitFor()
    await tour.getByRole('button', { name: 'AI 接入教程' }).click()
    const guide = page.getByRole('dialog', { name: '使用教程', exact: true })
    await guide.getByRole('heading', { name: '一步步配置' }).waitFor()
    await guide.getByRole('button', { name: '返回新手指引' }).click()
    await tour.getByRole('heading', { name: '对话 · 用来做什么' }).waitFor()
    await tour.getByLabel('学习目录').selectOption({ label: '15. 设置' })
    await tour.getByRole('button', { name: '打开栏目，跟着学' }).click()
    await tour.getByRole('button', { name: '看过了' }).click()
    await tour.getByRole('heading', { name: '随时回来，按需要继续学' }).waitFor()
    await tour.getByRole('button', { name: '开始使用', exact: true }).click()
    await page.reload(); await page.waitForFunction(() => (window as any).probe.help.initialized)
    expect(await page.getByRole('dialog').count()).toBe(0)
  } finally { await page.close() }
}, 30000)

it('keeps the save step on failure and allows exiting without another write', async () => {
  const { page, writes } = await fixture()
  try {
    const tour = page.getByRole('dialog', { name: '新手指引', exact: true })
    await tour.getByRole('button', { name: '开始，一步步来' }).click()
    await page.getByRole('button', { name: '新建任务', exact: true }).click()
    await page.getByLabel('任务标题', { exact: true }).fill('取快递')
    await tour.getByRole('button', { name: '填好了' }).click()
    await page.route('**/api/tasks', async route => route.fulfill({ status: 503, json: { detail: '保存失败，请核对看板' } }))
    await page.getByRole('button', { name: '创建', exact: true }).click()
    await page.getByRole('alert').waitFor()
    expect(await tour.locator('h2').innerText()).toBe('点“创建”，保存到看板')
    await tour.getByRole('button', { name: '先去使用' }).click()
    expect(writes).toHaveLength(0)
    expect(await page.getByLabel('任务标题', { exact: true }).inputValue()).toBe('取快递')
  } finally { await page.close() }
})

it('keeps highlighted inputs clickable after a narrow resize and supports keyboard saving', async () => {
  const { page, writes } = await fixture(true, 375)
  try {
    const tour = page.getByRole('dialog', { name: '新手指引', exact: true })
    await tour.getByRole('button', { name: '开始，一步步来' }).click()
    await page.getByRole('button', { name: '新建任务', exact: true }).click()
    const input = page.getByLabel('任务标题', { exact: true })
    await input.fill('整理材料')
    await page.setViewportSize({ width: 420, height: 620 })
    await input.click()
    await page.keyboard.press('Enter')
    await tour.getByRole('heading', { name: '保存成功，在这里能找到它' }).waitFor()
    expect(writes).toHaveLength(1)
    const rect = await tour.boundingBox()
    expect(rect!.x).toBeGreaterThanOrEqual(0)
    expect(rect!.x + rect!.width).toBeLessThanOrEqual(420)
    expect(rect!.y + rect!.height).toBeLessThanOrEqual(620)
  } finally { await page.close() }
})

it('skipping works on a small screen, preserves focus, and can be replayed manually', async () => {
  const { page, writes } = await fixture(true, 375)
  try {
    const tour = page.getByRole('dialog', { name: '新手指引', exact: true })
    await tour.waitFor()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const rect = await tour.boundingBox()
    expect(rect!.width).toBeLessThanOrEqual(375)
    await tour.getByRole('button', { name: '先去使用' }).click()
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
