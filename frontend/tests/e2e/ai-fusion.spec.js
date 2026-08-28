import { expect, test } from '@playwright/test'

// AI 深度融合冒烟：秘书自动档卡片（展示 + 撤销）与任务详情内嵌 AI 动作（AI 拆解）

const activeConfig = {
  id: 1,
  name: 'kimi',
  assistant_name: '知时助手',
  persona: '',
  provider: 'claude_messages',
  model: 'kimi-for-coding',
  base_url: '',
  full_url: '',
  proxy_url: '',
  extra_headers: {},
  enabled: true,
  active_skill_id: null,
}

function pad(value) {
  return String(value).padStart(2, '0')
}

function todayKey() {
  const d = new Date()
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
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

// 通用 mock：captured 收集自动档执行次数 / 删除日程条目 / AI 拆解请求供断言
async function mockBackend(page, { tasks = [], settings = {}, autopilot = null } = {}) {
  const captured = { autopilotRuns: 0, deletedEntries: [], breakdowns: [] }
  // 启动提醒与晨报的当日节流预置掉，避免遮挡；自动档节流 key 不预置（本测试要让它弹）
  await page.addInitScript((key) => {
    localStorage.setItem('startup_reminder_last_date', key)
    localStorage.setItem('zs-briefing-shown', key)
  }, todayKey())

  await page.route(/\/tasks(?:$|\/|\?)/, async (route) => {
    const request = route.request()
    if (request.method() === 'GET') return json(route, tasks)
    return json(route, {})
  })
  await page.route(/\/settings(?:$|\?)/, async (route) => json(route, settings))
  await page.route('**/ai/configs**', async (route) => json(route, [activeConfig]))
  await page.route('**/ai/skills**', async (route) => json(route, []))
  await page.route('**/ai/conversations**', async (route) => json(route, []))
  await page.route('**/reminders/due**', async (route) =>
    json(route, { upcoming: [], overdue: [], triggered: [] })
  )
  await page.route(/\/notifications(?:$|\?)/, async (route) => json(route, []))
  await page.route('**/notifications/unread-count**', async (route) => json(route, { unread: 0 }))
  await page.route('**/timer/current**', async (route) => json(route, null))
  await page.route('**/ai/autopilot/run**', async (route) => {
    captured.autopilotRuns += 1
    return json(route, autopilot || { ran: false, reason: '未启用 AI 配置', actions: [], message: '' })
  })
  await page.route('**/ai/actions/breakdown-subtasks**', async (route) => {
    captured.breakdowns.push(route.request().postDataJSON())
    return json(route, {
      ok: true,
      task_id: captured.breakdowns[captured.breakdowns.length - 1]?.task_id,
      subtasks: [
        { id: 901, title: '列出大纲', done: false },
        { id: 902, title: '完成初稿', done: false },
        { id: 903, title: '通读修改', done: false },
      ],
    })
  })
  await page.route('**/schedule/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (request.method() === 'DELETE' && /\/schedule\/entries\/\d+$/.test(url.pathname)) {
      captured.deletedEntries.push(url.pathname)
      await route.fulfill({ status: 204 })
      return
    }
    if (url.pathname === '/schedule/day') {
      return json(route, { date: url.searchParams.get('date'), buckets: {}, summary: {} })
    }
    if (url.pathname === '/schedule/month') {
      return json(route, { year: 2026, month: 7, days: [] })
    }
    return json(route, {})
  })
  return captured
}

const autopilotResult = {
  ran: true,
  cached: false,
  message: '排了 1 件事，拆了 1 件事。',
  actions: [
    {
      kind: 'schedule',
      task_id: 1,
      title: '写季度复盘',
      date: '2026-07-20',
      entry_id: 555,
      note: '明早状态好',
    },
    {
      kind: 'breakdown',
      task_id: 2,
      title: '准备分享会',
      subtasks: ['列大纲', '做幻灯片', '试讲一遍'],
      subtask_ids: [901, 902, 903],
    },
  ],
}

test('autopilot card shows on startup and schedule action can be undone', async ({ page }) => {
  const captured = await mockBackend(page, {
    tasks: [makeTask(1, '写季度复盘'), makeTask(2, '准备分享会')],
    settings: { feature_autopilot_enabled: 'true', feature_inline_ai_enabled: 'true' },
    autopilot: autopilotResult,
  })
  await page.goto('/')

  // 自动档执行一次并弹卡
  await expect.poll(() => captured.autopilotRuns).toBe(1)
  const card = page.getByRole('dialog', { name: '秘书自动档' })
  await expect(card).toBeVisible()
  await expect(card).toContainText('秘书已为你办妥')
  await expect(card).toContainText('排了 1 件事，拆了 1 件事。')
  await expect(card).toContainText('《写季度复盘》→ 7月20日')
  await expect(card).toContainText('《准备分享会》拆成 3 步')

  // 撤销排程项：DELETE 对应日程条目，该行移除
  const rows = card.locator('.action-row')
  await expect(rows).toHaveCount(2)
  await rows.first().getByRole('button', { name: '撤销' }).click()
  await expect.poll(() => captured.deletedEntries).toEqual(['/schedule/entries/555'])
  await expect(rows).toHaveCount(1)
  await expect(card).not.toContainText('《写季度复盘》')

  // 同一天节流：卡片关闭后写入 localStorage
  await card.getByRole('button', { name: '知道了' }).click()
  await expect(card).not.toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('zs-autopilot-shown'))).toBe(todayKey())
})

test('autopilot stays silent when disabled in settings', async ({ page }) => {
  const captured = await mockBackend(page, { settings: { feature_inline_ai_enabled: 'true' } })
  await page.goto('/')
  // 开关未开启：不执行自动档、不弹卡
  await page.waitForTimeout(500)
  expect(captured.autopilotRuns).toBe(0)
  await expect(page.getByRole('dialog', { name: '秘书自动档' })).not.toBeVisible()
})

test('task modal AI breakdown creates subtasks via inline action', async ({ page }) => {
  const captured = await mockBackend(page, {
    tasks: [makeTask(1, '写季度复盘')],
    settings: { feature_inline_ai_enabled: 'true' },
  })
  await page.goto('/')

  // 看板打开任务详情
  await page.locator('.task-card', { hasText: '写季度复盘' }).first().click()
  const modal = page.getByRole('dialog', { name: '编辑任务' })
  await expect(modal).toBeVisible()

  const breakdownBtn = modal.getByRole('button', { name: 'AI 拆解' })
  await expect(breakdownBtn).toBeVisible()
  await expect(breakdownBtn).toBeEnabled()
  await breakdownBtn.click()

  // 调用了拆解端点且子任务即时出现在弹窗里
  await expect.poll(() => captured.breakdowns.length).toBe(1)
  expect(captured.breakdowns[0].task_id).toBe(1)
  await expect(modal).toContainText('列出大纲')
  await expect(modal).toContainText('通读修改')
  await expect(page.locator('.toast')).toContainText('已拆成 3 个子任务')

  // 已有子任务后按钮仍可用（SMART_PLANNING C1：改为增量拆解，后端跳过重复项只补缺）
  await expect(breakdownBtn).toBeEnabled()
  await expect(breakdownBtn).toHaveAttribute('title', '让 AI 补充拆解缺失的环节')

  // 再次点击会再次调用拆解端点（增量补缺）
  await breakdownBtn.click()
  await expect.poll(() => captured.breakdowns.length).toBe(2)
})
