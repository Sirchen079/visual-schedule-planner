import { expect, test } from '@playwright/test'

const pages = [
  { tab: 0, root: '.board', name: 'board' },
  { tab: 1, root: '.overview', name: 'overview' },
  { tab: 2, root: '.calendar-action-center', name: 'calendar' },
  { tab: 3, root: '.timeline', name: 'timeline' },
  { tab: 4, root: '.library', name: 'library' },
  { tab: 6, root: '.trash', name: 'trash' },
]

function task(id, title, overrides = {}) {
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
    tags: [],
    files: [],
    subtasks: [],
    created_at: '2026-06-29T09:00:00',
    updated_at: '2026-06-29T09:00:00',
    ...overrides,
  }
}

const tasks = [
  task(1, '全局视觉体验重构', {
    priority: '高',
    progress: 35,
    due_date: '2026-06-29T18:00:00',
    tags: [{ id: 1, name: '视觉', color: '#3b98c6' }],
  }),
  task(2, '图标尺寸体系整理', {
    status: '进行中',
    priority: '中',
    progress: 60,
    start_date: '2026-06-28T09:00:00',
    end_date: '2026-07-01T18:00:00',
  }),
  task(3, '资料库视觉密度优化', {
    status: '完成',
    priority: '低',
    progress: 100,
    due_date: '2026-06-27T18:00:00',
  }),
]

const files = [
  {
    id: 1,
    original_name: 'visual-reference.pdf',
    mime_type: 'application/pdf',
    size: 2048,
    source_url: null,
    resource_type: 'pdf',
    notes: '',
    created_at: '2026-06-28T09:00:00',
  },
]

async function json(route, body) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json; charset=utf-8',
    body: JSON.stringify(body),
  })
}

async function mockBackend(page) {
  await page.route(/\/tasks\/trash(?:$|\?)/, (route) => json(route, [tasks[0]]))
  await page.route(/\/tasks\/tags(?:$|\?)/, (route) => json(route, []))
  await page.route(/\/tasks(?:$|\?)/, (route) => json(route, tasks))
  await page.route(/\/files\/trash(?:$|\?)/, (route) =>
    json(route, [{ ...files[0], deleted_at: '2026-06-28T09:00:00' }])
  )
  await page.route(/\/files(?:$|\?)/, (route) => json(route, files))
  await page.route('**/reminders/due**', (route) => json(route, { upcoming: [], overdue: [] }))
  await page.route('**/ai/configs**', (route) => json(route, []))
  await page.route('**/ai/skills**', (route) => json(route, []))
  await page.route('**/schedule/day**', (route) =>
    json(route, {
      date: '2026-06-29',
      // 计数保持为 0:避免启动提醒弹窗遮挡顶栏,干扰纯视觉壳检查
      summary: {
        total: 0,
        must_do: 0,
        planned: 0,
        in_progress_today: 0,
        upcoming_pressure: 0,
        unscheduled: 0,
      },
      buckets: {
        must_do: [],
        planned: [],
        in_progress_today: [],
        upcoming_pressure: [],
        unscheduled: [],
      },
    })
  )
  await page.route('**/schedule/month**', (route) =>
    json(route, {
      year: 2026,
      month: 6,
      days: [
        {
          date: '2026-06-29',
          due_count: 1,
          planned_count: 0,
          in_progress_count: 0,
          overdue_count: 0,
          total_count: 1,
        },
      ],
    })
  )
}

test.describe('workspace visual density', () => {
  test('primary pages use the workspace visual shell on desktop', async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 950 })
    await mockBackend(page)
    await page.goto('/')

    for (const item of pages) {
      await page.locator('.tabs .tab').nth(item.tab).click()
      const root = page.locator(item.root)
      await expect(root).toBeVisible()
      await expect(root).toHaveClass(/workspace-page/)
      const box = await root.boundingBox()
      expect(box.width, `${item.name} should use wide desktop space`).toBeGreaterThanOrEqual(1320)
    }
  })

  test('primary pages remain reachable on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await mockBackend(page)
    await page.goto('/')

    for (const item of pages) {
      await page.locator('.tabs .tab').nth(item.tab).click()
      await expect(page.locator(item.root)).toBeVisible()
    }
  })
})
