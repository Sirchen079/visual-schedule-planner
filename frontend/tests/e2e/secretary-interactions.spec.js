import { expect, test } from '@playwright/test'

// 第一阶段「秘书线 + 交互基建」冒烟：命令面板快速创建 / 视图跳转 / 日历拖拽改期

function pad(value) {
  return String(value).padStart(2, '0')
}

function isoDate(value) {
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
}

function makeTask(id, title, overrides = {}) {
  return {
    id,
    title,
    notes: '',
    status: '待办',
    priority: '中',
    progress: 0,
    start_date: null,
    end_date: null,
    due_date: null,
    due_time: null,
    remind_offsets: [],
    recur_rule: 'none',
    recur_interval: 1,
    completed_at: null,
    created_at: '2026-07-01T09:00:00',
    updated_at: '2026-07-01T09:00:00',
    deleted_at: null,
    tags: [],
    files: [],
    subtasks: [],
    ...overrides,
  }
}

async function json(route, body, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json; charset=utf-8',
    body: JSON.stringify(body),
  })
}

// 通用 mock：captured 收集 POST/PUT /tasks 的请求体供断言
async function mockBackend(page, { tasks = [] } = {}) {
  const captured = []
  // 启动提醒弹窗每天只弹一次（localStorage 节流）；预置今天已弹，避免遮挡视图切换
  await page.addInitScript(() => {
    const d = new Date()
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    localStorage.setItem('startup_reminder_last_date', key)
  })
  await page.route(/\/tasks(?:$|\/|\?)/, async (route) => {
    const request = route.request()
    if (request.method() === 'GET') return json(route, tasks)
    if (request.method() === 'POST' || request.method() === 'PUT') {
      captured.push({ method: request.method(), url: request.url(), body: request.postDataJSON() })
      return json(route, makeTask(99, captured[captured.length - 1].body?.title || '新任务', captured[captured.length - 1].body || {}))
    }
    return json(route, {})
  })
  await page.route('**/reminders/due**', async (route) =>
    json(route, { upcoming: [], overdue: [], triggered: [] })
  )
  await page.route(/\/settings(?:$|\?)/, async (route) =>
    json(route, { onboarding_done: '1', feature_habits_enabled: 'true', feature_journal_enabled: 'true', feature_goals_enabled: 'true', feature_timer_enabled: 'true' })
  )
  await page.route('**/ai/configs**', async (route) => json(route, []))
  await page.route('**/ai/skills**', async (route) => json(route, []))
  await page.route('**/ai/conversations**', async (route) => json(route, []))
  await page.route('**/schedule/**', async (route) => {
    const url = new URL(route.request().url())
    const { pathname, searchParams } = url
    if (pathname === '/schedule/month') {
      const year = Number(searchParams.get('year'))
      const month = Number(searchParams.get('month'))
      const daysInMonth = new Date(year, month, 0).getDate()
      const days = []
      for (let day = 1; day <= daysInMonth; day += 1) {
        days.push({
          date: `${year}-${pad(month)}-${pad(day)}`,
          due_count: tasks.filter((t) => (t.due_date || '').startsWith(`${year}-${pad(month)}-${pad(day)}`)).length,
          planned_count: 0,
          in_progress_count: 0,
          overdue_count: 0,
          total_count: 0,
        })
      }
      return json(route, { year, month, days })
    }
    return json(route, { buckets: {}, summary: {} })
  })
  return captured
}

test('command palette quick-creates task with natural language parsing', async ({ page }) => {
  const captured = await mockBackend(page, { tasks: [makeTask(1, '买牛奶')] })
  await page.goto('/')

  await page.keyboard.press('Control+k')
  const palette = page.locator('.palette')
  await expect(palette).toBeVisible()

  await page.keyboard.type('新建 明天下午3点写周报 #工作 !高')
  const createItem = palette.locator('.cmd-item', { hasText: '写周报' }).first()
  await expect(createItem).toBeVisible()
  await createItem.click()

  await expect(palette).not.toBeVisible()
  await expect.poll(() => captured.length).toBe(1)
  const body = captured[0].body
  expect(body.title).toBe('写周报')
  expect(body.priority).toBe('高')
  expect(body.due_time).toBe('15:00')
  expect(body.tags).toContain('工作')
  const tomorrow = new Date()
  tomorrow.setDate(tomorrow.getDate() + 1)
  expect(body.due_date).toContain(isoDate(tomorrow))
})

test('command palette switches views', async ({ page }) => {
  await mockBackend(page)
  await page.goto('/')

  await page.keyboard.press('Control+k')
  await page.keyboard.type('日历')
  const item = page.locator('.palette .cmd-item', { hasText: '日历' }).first()
  await expect(item).toBeVisible()
  await item.click()

  await expect(page.locator('.palette')).not.toBeVisible()
  await expect(page.locator('.calendar-action-center')).toBeVisible()
})

test('calendar month view drag reschedules a due task', async ({ page }) => {
  const now = new Date()
  const ym = `${now.getFullYear()}-${pad(now.getMonth() + 1)}`
  const source = makeTask(7, '拖拽改期任务', { due_date: `${ym}-10T18:00:00` })
  const captured = await mockBackend(page, { tasks: [source] })
  await page.goto('/')

  await page.locator('.tabs .tab').nth(2).click()
  await expect(page.locator('.calendar-action-center')).toBeVisible()
  await page.getByRole('tab', { name: '月计划' }).click()

  const chip = page.locator('.cell-task', { hasText: '拖拽改期任务' })
  await expect(chip).toBeVisible()
  const targetCell = page.locator('.month-cell:not(.muted):has(.cell-date:text-is("15"))').first()
  await expect(targetCell).toBeVisible()

  const putRequest = page.waitForRequest(
    (req) => req.method() === 'PUT' && /\/tasks\/7$/.test(req.url())
  )
  await chip.dragTo(targetCell)
  const req = await putRequest
  expect(req.postDataJSON().due_date).toContain(`${ym}-15`)
})

test('timeline bar drag shifts start and end dates', async ({ page }) => {
  const now = new Date()
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 2, 9, 0, 0)
  const end = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 4, 18, 0, 0)
  const task = makeTask(8, '时间轴拖拽任务', {
    start_date: isoDate(start) + 'T09:00:00',
    end_date: isoDate(end) + 'T18:00:00',
  })
  await mockBackend(page, { tasks: [task] })
  await page.goto('/')

  await page.locator('.tabs .tab').nth(3).click()
  const bar = page.locator('.track .bar').first()
  await expect(bar).toBeVisible()
  const track = page.locator('.track').first()

  const putRequest = page.waitForRequest(
    (req) => req.method() === 'PUT' && /\/tasks\/8$/.test(req.url())
  )
  const box = await bar.boundingBox()
  const trackBox = await track.boundingBox()
  // 向右拖约半个轨道宽（保证换算 ≥1 天；<4px 视为点击，drag 内按 pxPerDay 取整）
  const dx = Math.max(Math.round(trackBox.width / 2), 80)
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 + dx, box.y + box.height / 2, { steps: 10 })
  await page.mouse.up()

  const req = await putRequest
  const body = req.postDataJSON()
  expect(body.start_date).toBeTruthy()
  expect(body.end_date).toBeTruthy()
  const deltaDays = Math.round((new Date(body.start_date) - start) / 86400000)
  expect(deltaDays).toBeGreaterThanOrEqual(1)
})

test('capture view quick-creates task in standalone window mode', async ({ page }) => {
  const captured = await mockBackend(page)
  await page.goto('/?view=capture')

  const input = page.locator('.capture-input')
  await expect(input).toBeVisible()
  await input.fill('明天早上9点站会 #工作')
  await input.press('Enter')

  await expect.poll(() => captured.length).toBe(1)
  const body = captured[0].body
  expect(body.title).toBe('站会')
  expect(body.due_time).toBe('09:00')
  expect(body.tags).toContain('工作')
  const tomorrow = new Date()
  tomorrow.setDate(tomorrow.getDate() + 1)
  expect(body.due_date).toContain(isoDate(tomorrow))
  // 成功后输入框清空，可连续捕获
  await expect(input).toHaveValue('')
})

test('notification center lists history and supports mark-all-read', async ({ page }) => {
  await mockBackend(page)
  const note = {
    id: 1,
    task_id: 1,
    kind: 'reminder',
    title: '半小时后开会',
    body: '截止 07-18 22:30 · 提前 60 分钟',
    remind_at: '2026-07-18T21:30:00',
    created_at: '2026-07-18T21:30:00',
    read_at: null,
  }
  let readAllCalled = false
  await page.route(/\/notifications(?:$|\?)/, async (route) => json(route, [note]))
  await page.route('**/notifications/unread-count**', async (route) => json(route, { unread: 1 }))
  await page.route('**/notifications/read-all**', async (route) => {
    readAllCalled = true
    return json(route, { marked: 1 })
  })
  await page.goto('/')

  // 铃铛有未读角标，打开提醒面板切到「通知」页
  const bell = page.locator('.bell-btn')
  await expect(bell).toHaveClass(/has/)
  await bell.click()
  await page.getByRole('tab', { name: '通知' }).click()
  await expect(page.getByText('半小时后开会')).toBeVisible()
  await expect(page.getByText(/提前 60 分钟/)).toBeVisible()

  await page.getByRole('button', { name: '全部已读' }).click()
  await expect.poll(() => readAllCalled).toBe(true)
})
