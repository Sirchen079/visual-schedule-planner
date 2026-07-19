import { expect, test } from '@playwright/test'

const activeConfig = {
  id: 1,
  name: 'kimi',
  assistant_name: '知时助手',
  persona: '',
  provider: 'claude_messages',
  model: 'kimi-for-coding',
  base_url: '',
  full_url: '',
  proxy_url: 'http://127.0.0.1:7890',
  extra_headers: {},
  enabled: true,
  active_skill_id: null,
}

function isoDate(value) {
  return value.toISOString().slice(0, 10)
}

function pad(value) {
  return String(value).padStart(2, '0')
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
    tags: [],
    files: [],
    subtasks: [],
    ...overrides,
  }
}

function makeDaySchedule(date) {
  const plannedEntry = {
    id: 101,
    task_id: 2,
    date,
    source: 'manual',
    note: 'Design block',
    created_at: '2026-06-29T09:00:00',
    updated_at: '2026-06-29T09:00:00',
  }

  const plannedTask = makeTask(2, 'Sketch icon set', {
    priority: '高',
    progress: 45,
    due_date: `${date}T18:00:00`,
    tags: [{ id: 11, name: '视觉', color: '#3b98c6' }],
    files: [
      {
        id: 301,
        original_name: 'inspiration.pdf',
        size: 2048,
        mime_type: 'application/pdf',
        notes: '',
        source_url: null,
        resource_type: 'file',
      },
    ],
    subtasks: [
      {
        id: 401,
        task_id: 2,
        title: 'Draft outline',
        done: true,
        completed_at: '2026-06-29T10:00:00',
      },
    ],
  })

  return {
    date,
    summary: {
      must_do: 1,
      planned: 1,
      in_progress_today: 1,
      upcoming_pressure: 1,
      unscheduled: 1,
      total: 5,
    },
    buckets: {
      must_do: [
        {
          task: makeTask(1, 'Renew design notes', {
            priority: '高',
            progress: 80,
            due_date: `${date}T18:00:00`,
            tags: [{ id: 10, name: '截止', color: '#d95d6a' }],
          }),
          entry: null,
          reason: 'due',
        },
      ],
      planned: [
        {
          task: plannedTask,
          entry: plannedEntry,
          reason: 'scheduled',
        },
      ],
      in_progress_today: [
        {
          task: makeTask(3, 'Refine interaction flow', {
            status: '进行中',
            progress: 60,
            start_date: '2026-06-28T09:00:00',
            end_date: '2026-06-30T18:00:00',
          }),
          entry: null,
          reason: 'date_range',
        },
      ],
      upcoming_pressure: [
        {
          task: makeTask(4, 'Prepare review', {
            due_date: '2026-07-02T18:00:00',
          }),
          entry: null,
          reason: 'upcoming_due',
        },
      ],
      unscheduled: [
        {
          task: makeTask(5, 'Collect inspiration'),
          entry: null,
          reason: 'unscheduled',
        },
      ],
    },
  }
}

function makeMonthDays(year, month) {
  const daysInMonth = new Date(year, month, 0).getDate()
  const highlightDay = 29
  const days = []
  for (let day = 1; day <= daysInMonth; day += 1) {
    const iso = `${year}-${pad(month)}-${pad(day)}`
    const active = day === highlightDay ? 5 : 0
    days.push({
      date: iso,
      due_count: day === highlightDay ? 1 : 0,
      planned_count: day === highlightDay ? 1 : 0,
      in_progress_count: day === highlightDay ? 1 : 0,
      overdue_count: 0,
      total_count: active,
    })
  }
  return days
}

async function json(route, body, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json; charset=utf-8',
    body: JSON.stringify(body),
  })
}

async function mockBackend(page) {
  // 启动提醒弹窗每天只弹一次（localStorage 节流）；预置今天已弹，避免遮挡视图切换
  await page.addInitScript(() => {
    const d = new Date()
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    localStorage.setItem('startup_reminder_last_date', key)
  })
  await page.route(/\/tasks(?:$|\/|\?)/, async (route) => {
    if (route.request().method() === 'GET') return json(route, [])
    return json(route, {})
  })
  await page.route('**/ai/configs**', async (route) => {
    if (route.request().method() === 'GET') return json(route, [activeConfig])
    return json(route, activeConfig)
  })
  await page.route('**/ai/skills**', async (route) => json(route, []))
  await page.route('**/schedule/**', async (route) => {
    const url = new URL(route.request().url())
    const { pathname, searchParams } = url
    if (pathname === '/schedule/day' && route.request().method() === 'GET') {
      return json(route, makeDaySchedule(searchParams.get('date') || isoDate(new Date())))
    }
    if (pathname === '/schedule/month' && route.request().method() === 'GET') {
      const year = Number(searchParams.get('year') || new Date().getFullYear())
      const month = Number(searchParams.get('month') || new Date().getMonth() + 1)
      return json(route, {
        year,
        month,
        days: makeMonthDays(year, month),
      })
    }
    if (pathname === '/schedule/entries') {
      return json(route, {
        id: 999,
        task_id: 2,
        date: searchParams.get('date') || isoDate(new Date()),
        source: 'manual',
        note: '',
        created_at: '2026-06-29T09:00:00',
        updated_at: '2026-06-29T09:00:00',
      })
    }
    return json(route, {})
  })
}

async function openCalendar(page) {
  await page.locator('.tabs .tab').nth(2).click()
  await expect(page.locator('.calendar-action-center')).toBeVisible()
}

test('calendar defaults to day action view and can switch to month plan', async ({ page }) => {
  await mockBackend(page)
  await page.goto('/')

  await openCalendar(page)

  await expect(page.locator('.calendar-action-center')).toBeVisible()
  await expect(page.locator('.day-layout[data-view-mode="day"]')).toBeVisible()
  await expect(page.locator('.day-bucket')).toHaveCount(5)
  await expect(page.getByText('来源 manual')).toBeVisible()
  await expect(page.getByText('子任务 1/1')).toBeVisible()
  await expect(page.getByText('资料 1')).toBeVisible()

  await page.getByRole('tab', { name: '月计划' }).click()
  await expect(page.locator('.month-layout[data-view-mode="month"]')).toBeVisible()
  await expect(page.locator('.month-plan-grid')).toBeVisible()
  await expect(page.locator('.selected-day-preview')).toBeVisible()
  await expect(page.locator('.selected-day-preview .preview-bucket')).toHaveCount(4)
  await expect(page.locator('.month-cell.selected')).toBeVisible()
})

test('calendar planning prompts open the assistant composer', async ({ page }) => {
  await mockBackend(page)
  await page.goto('/')

  await openCalendar(page)
  await page.locator('.assistant-plan-button').first().click()

  await expect(page.locator('.assistant-shell')).toBeVisible()
  await expect(page.locator('.assistant-shell .composer textarea')).toHaveValue(/请帮我安排/)
})

test('calendar remains usable on a narrow viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockBackend(page)
  await page.goto('/')

  await openCalendar(page)

  await expect(page.locator('.calendar-action-center')).toBeVisible()
  await expect(page.locator('.day-bucket')).toHaveCount(5)
  await expect(page.locator('.assistant-plan-button').first()).toBeVisible()

  await page.getByRole('tab', { name: '月计划' }).click()
  await expect(page.locator('.month-plan-grid')).toBeVisible()
  await expect(page.locator('.selected-day-preview')).toBeVisible()
})
