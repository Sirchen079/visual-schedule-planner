import { afterAll, beforeAll, expect, it } from 'vitest'
import { createServer, type ViteDevServer } from 'vite'
import vue from '@vitejs/plugin-vue'
import { chromium, type Browser } from 'playwright'

let server: ViteDevServer, browser: Browser, origin: string
const request = { id: 9, run_id: 'r1', call_id: 'q1', status: 'pending', version: 0, answer: {}, questions: [
  { id: 'scope', question: '这次安排哪些时间？', options: [{ label: '今天', description: '只安排今天的空闲时间' }, { label: '本周', description: '查看本周日程后安排' }], multi_select: false },
  { id: 'focus', question: '希望优先考虑什么？', options: [{ label: '学习', description: '' }, { label: '休息', description: '' }], multi_select: true },
] }
const markdown = '# 安排建议\n\n**重要事项**与普通正文。\n\n> 先核对时间，再决定安排。\n\n1. 第一项\n   - 子项目\n2. 第二项\n\n- [x] 已核对日程\n- [ ] 等待选择\n\n| 事项 | 时间 |\n| --- | --- |\n| 阅读 | 09:00 |\n\n```python\nprint("<safe>")\n```\n\n[发布说明](https://example.org/releases)\n\n<script>window.XSS=true</script>'
beforeAll(async () => {
  const root = decodeURIComponent(new URL('../../..', import.meta.url).pathname).replace(/^\/([A-Za-z]:\/)/, '$1')
  server = await createServer({ configFile: false, root, cacheDir: `${root}/node_modules/.vite-toolchain-tests`, plugins: [vue(), {
    name: 'toolchain-ui-fixture', resolveId(id) { if (id === '/toolchain-entry.js') return '\0toolchain-entry' },
    load(id) {
      if (id !== '\0toolchain-entry') return
      return `import {createApp,h} from 'vue'; import {createPinia,setActivePinia} from 'pinia';
        import Thread from '/src/components/chat/ChatThread.vue'; import Update from '/src/components/shell/AppUpdate.vue';
        import {useConversationStore} from '/src/stores/conversation'; import {useRunStore} from '/src/stores/run';
        import {useUpdatesStore} from '/src/stores/updates'; import '/src/tokens.css';
        const pinia=createPinia();setActivePinia(pinia);const conv=useConversationStore(),run=useRunStore(),updates=useUpdatesStore();
        conv.initialized=true;conv.activeId=1;run.reset(1);run.runId='r1';run.phase='awaiting_input';
        run.questionRequests=[${JSON.stringify(request)}];
        conv.messages=[{id:1,role:'assistant',created_at:'2026-09-07T10:00:00',display:{text:${JSON.stringify(markdown)},questions:[${JSON.stringify(request)}]}}];
        window.probe={conv,run,updates};
        createApp({render:()=>h('main',[h(Thread),h(Update,{inline:true}),h(Update)])}).use(pinia).mount('#app');
        if(window.zhishiUpdates) updates.initialize();`
    },
    configureServer(vite) { vite.middlewares.use((req, res, next) => {
      if ((req as unknown as { url: string }).url !== '/toolchain-test') return next()
      res.setHeader('Content-Type', 'text/html')
      res.end('<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0;padding:16px;background:var(--bg-app);font-family:var(--sans)}#app{max-width:570px;margin:auto}</style></head><body><div id="app"></div><script type="module" src="/toolchain-entry.js"></script></body></html>')
    }) },
  }], server: { host: '127.0.0.1', port: 0 } })
  await server.listen()
  const address = server.httpServer!.address()
  origin = `http://127.0.0.1:${typeof address === 'object' && address ? address.port : 0}`
  browser = await chromium.launch({ headless: true })
}, 30000)
afterAll(async () => { await browser?.close(); await server?.close() })

async function fixture() {
  const page = await browser.newPage({ viewport: { width: 375, height: 1000 } })
  page.setDefaultTimeout(10000)
  const writes: any[] = []
  await page.route('**/ai/**', async route => {
    const req = route.request(), body = req.postDataJSON()
    if (new URL(req.url()).pathname.includes('/questions/')) {
      writes.push(body)
      await route.fulfill({ json: { request: { ...request, status: body.skip ? 'skipped' : 'answered', version: 1,
        answer: { answers: Object.entries(body.answers).map(([id, answer]) => ({ id, ...(answer as object) })) } }, ready_to_resume: false } })
    } else await route.fulfill({ json: { ...body, revision: (body?.revision ?? 0) + 1 } })
  })
  return { page, writes }
}

it('shows one pending card, accepts single/multiple/free answers and persists drafts', async () => {
  const { page, writes } = await fixture()
  try {
    await page.goto(`${origin}/toolchain-test`)
    await page.getByRole('button', { name: '提交并继续' }).waitFor()
    expect(await page.locator('.question-card').count()).toBe(1)
    expect(await page.locator('input:checked').count()).toBe(0)
    expect(await page.getByRole('button', { name: '提交并继续' }).isDisabled()).toBe(true)
    await page.getByRole('radio', { name: '今天' }).check()
    await page.getByRole('radio', { name: '本周' }).check()
    await page.getByRole('checkbox', { name: '学习' }).check()
    await page.getByRole('checkbox', { name: '休息' }).check()
    await page.locator('textarea').first().fill('上午安排，保留周末')
    expect(await page.evaluate(() => (window as any).probe.conv.questionDrafts['9'].scope.text)).toBe('上午安排，保留周末')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.getByRole('button', { name: '提交并继续' }).click()
    await page.getByText('已回答', { exact: true }).waitFor()
    expect(writes).toHaveLength(1)
    expect(writes[0].answers).toEqual({ scope: { selected: ['本周'], text: '上午安排，保留周末' }, focus: { selected: ['学习', '休息'], text: '' } })
    expect(await page.locator('.question-card textarea').count()).toBe(0)
  } finally { await page.close() }
}, 15000)

it('renders standard Markdown safely and allows a free-text-only answer', async () => {
  const { page, writes } = await fixture()
  try {
    await page.goto(`${origin}/toolchain-test`)
    await page.locator('h1').waitFor()
    expect(await page.locator('.body table th').count()).toBe(2)
    expect(await page.locator('.body ol ul li').count()).toBe(1)
    expect(await page.locator('pre code').textContent()).toContain('print("<safe>")')
    expect(await page.locator('.body script').count()).toBe(0)
    expect(await page.evaluate(() => (window as any).XSS)).toBeUndefined()
    expect(await page.getByRole('link', { name: '发布说明' }).getAttribute('rel')).toBe('noopener noreferrer')
    await page.locator('textarea').first().fill('只安排周三')
    await page.locator('textarea').last().fill('优先休息')
    const screenshotDir = (globalThis as any).process?.env.ZHISHI_QA_SCREENSHOT_DIR
    if (screenshotDir) await page.screenshot({ path: `${screenshotDir}/toolchain-markdown-question.png`, fullPage: true })
    await page.getByRole('button', { name: '提交并继续' }).click()
    await page.getByText('已回答', { exact: true }).waitFor()
    expect(writes[0].answers.scope.selected).toEqual([])
    expect(writes[0].answers.scope.text).toBe('只安排周三')
  } finally { await page.close() }
}, 15000)

it('skip requires an explicit click and submits no answers', async () => {
  const { page, writes } = await fixture()
  try {
    await page.goto(`${origin}/toolchain-test`)
    await page.getByRole('button', { name: '跳过这组问题' }).click()
    await page.getByText('已跳过', { exact: true }).waitFor()
    expect(writes).toEqual([{ version: 0, answers: {}, skip: true }])
  } finally { await page.close() }
}, 15000)

it('update UI shows download progress and saves workspace before acknowledging restart', async () => {
  const { page } = await fixture()
  try {
    await page.addInitScript(() => {
      let changed: any, prepare: any
      let state: any = { status: 'available', version: '2.16.0', currentVersion: '2.15.0', percent: 0, error: '', checkedAt: null, releasesUrl: 'https://example.org/releases' }
      const bridge: any = { state: async () => state, onChanged: (cb: any) => { changed = cb }, onPrepare: (cb: any) => { prepare = cb },
        check: async () => {}, openReleases: async () => {}, install: async () => {},
        downloadAndInstall: async () => { state = { ...state, status: 'downloading', percent: 45 }; changed(state) } }
      ;(window as any).zhishiUpdates = bridge
      ;(window as any).updateProbe = { prepare: () => prepare(), set: (patch: any) => { state = { ...state, ...patch }; changed(state) } }
    })
    await page.goto(`${origin}/toolchain-test`)
    await page.locator('.update-inline').getByRole('button', { name: '下载并安装' }).click()
    await page.locator('progress').first().waitFor()
    expect(await page.locator('progress').first().getAttribute('value')).toBe('45')
    await page.evaluate(async () => {
      ;(window as any).probe.conv.draftText = '安装前保留此草稿'
      ;(window as any).updateProbe.set({ status: 'preparing' })
      await (window as any).updateProbe.prepare()
    })
    expect(await page.locator('.update-lock').count()).toBe(1)
    expect(await page.evaluate(() => (window as any).probe.conv.drafts['1'].text)).toBe('安装前保留此草稿')
    expect(await page.evaluate(() => (window as any).probe.conv.workspaceDirty)).toBe(false)
  } finally { await page.close() }
}, 15000)

it('renders user, saved and streamed formulas with local fonts in a narrow chat', async () => {
  const { page } = await fixture()
  const failures: string[] = []
  page.on('pageerror', error => failures.push(error.message))
  try {
    await page.goto(`${origin}/toolchain-test`)
    await page.locator('h1').waitFor()
    const content = String.raw`# 公式与排版

**勾股定理**：$a^2+b^2=c^2$。

\[
\begin{aligned} E &= mc^2 \\ f'(x) &= 2x \end{aligned}
\]

| 写法 | 用途 |
| --- | --- |
| $\frac{1}{2}$ | 行内公式 |

\[
\underbrace{a+a+a+a+a+a+a+a+a+a+a+a+a+a+a+a+a+a+a+a+a+a+a+a+a+a+a+a+a+a}_{30\text{ 项}}=30a
\]`
    await page.evaluate(({content}) => {
      const {conv,run} = (window as any).probe
      run.reset(1);run.phase='streaming';run.runId='math-live'
      conv.messages=[
        {id:10,role:'user',created_at:'2026-09-09T10:00:00',display:{text:String.raw`**问题**：解释 \(x^2\)。`}},
        {id:11,role:'assistant',created_at:'2026-09-09T10:01:00',display:{text:content}},
      ]
      run.segments=[{kind:'text',seq:1,content:String.raw`继续：\(\frac{1}`}]
    }, {content})
    await page.locator('.msg-user .katex').waitFor()
    expect(await page.locator('.msg-user strong').innerText()).toBe('问题')
    expect(await page.locator('.msg-ai .katex-display').count()).toBe(2)
    await page.evaluate(() => { (window as any).probe.run.segments[0].content=String.raw`继续：\(\frac{1}{2}\)。` })
    await page.locator('.msg-ai').last().locator('.katex').waitFor()
    await page.evaluate(() => document.fonts.ready)
    expect(await page.evaluate(() => document.fonts.check('16px KaTeX_Main'))).toBe(true)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    expect(await page.locator('.katex-block').last().evaluate(el => el.scrollWidth > el.clientWidth)).toBe(true)
    expect(await page.locator('.body script,.body img').count()).toBe(0)
    expect(failures).toEqual([])
    const screenshotDir = (globalThis as any).process?.env.ZHISHI_QA_SCREENSHOT_DIR
    if (screenshotDir) {
      await page.screenshot({path:`${screenshotDir}/chat-formulas-dark-v219.png`,fullPage:true})
      await page.evaluate(() => document.documentElement.dataset.theme='light')
      await page.screenshot({path:`${screenshotDir}/chat-formulas-light-v219.png`,fullPage:true})
    }
  } finally { await page.close() }
}, 15000)
