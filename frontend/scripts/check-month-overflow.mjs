// 阶段 A5 验收脚本：加载日历月视图，注入「单日 6+ 任务 + 多信号」极端密度，
// 断言每个 .month-cell 的 scrollHeight <= clientHeight（不越界），
// 且所有行高一致（消除「周与周行高不齐」）。
// 用法：先起 dev server (npm run dev)，再 node scripts/check-month-overflow.mjs
import { chromium } from '@playwright/test'

const BASE = process.env.TARGET_URL || 'http://localhost:5173'

// 构造一天挂 6+ 条安排、跨 3 周密度不均的月数据
function denseMonthDays(year, month) {
  const daysInMonth = new Date(year, month, 0).getDate()
  const days = []
  for (let day = 1; day <= daysInMonth; day += 1) {
    const iso = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    // 第 5、15、25 天挂满：到期 3、安排 3、推进 2、压力 1 = total 9（极忙格）
    // 其余天 0-2 条（空闲），制造「跨 3 周密度不均」
    let totalCount = 0, due = 0, planned = 0, progress = 0, overdue = 0
    if ([5, 15, 25].includes(day)) {
      due = 3; planned = 3; progress = 2; overdue = 1; totalCount = 9
    } else if (day % 7 === 0) {
      due = 1; totalCount = 1
    }
    days.push({
      date: iso,
      due_count: due,
      planned_count: planned,
      in_progress_count: progress,
      overdue_count: overdue,
      total_count: totalCount,
    })
  }
  return days
}

function denseDaySchedule(date) {
  // 6 条 planned entry，撑爆格子
  const items = Array.from({ length: 6 }, (_, i) => ({
    task: { id: 100 + i, title: `密集任务 ${i + 1}：这条标题很长用来测试裁剪和省略号是否生效`, status: '进行中', due_date: `${date}T23:59:59`, priority: 'high' },
    entry: { id: 200 + i, start_time: '09:00', end_time: '10:00' },
  }))
  return {
    date,
    buckets: { planned: items, overdue: [], due_today: [], in_progress: [], completed: [] },
  }
}

async function main() {
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })

  await page.addInitScript(() => {
    const d = new Date()
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    localStorage.setItem('startup_reminder_last_date', key)
  })

  const json = (route, body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  // 精确根路径 glob（preview 服务器无 /src/ 模块路径，**/x** 形式安全）
  await page.route('**/tasks', async (route) => (route.request().method() === 'GET' ? json(route, []) : json(route, {})))
  await page.route('**/tasks/*', async (route) => json(route, {}))
  await page.route('**/ai/configs', async (route) => json(route, []))
  await page.route('**/ai/configs/*', async (route) => json(route, { id: 1, provider: 'openai', name: 'test', is_active: true }))
  await page.route('**/ai/skills', async (route) => json(route, []))
  await page.route('**/settings', async (route) => json(route, { onboarding_done: '1' }))
  await page.route('**/schedule/day*', async (route) => {
    const u = new URL(route.request().url())
    return json(route, denseDaySchedule(u.searchParams.get('date') || new Date().toISOString().slice(0, 10)))
  })
  await page.route('**/schedule/month*', async (route) => {
    const u = new URL(route.request().url())
    const year = Number(u.searchParams.get('year') || new Date().getFullYear())
    const month = Number(u.searchParams.get('month') || new Date().getMonth() + 1)
    return json(route, { year, month, days: denseMonthDays(year, month) })
  })
  await page.route('**/schedule/entries*', async (route) => json(route, {}))

  await page.goto(BASE, { waitUntil: 'networkidle' })
  await page.locator('.tabs .tab').nth(2).click()
  await page.getByRole('tab', { name: '月计划' }).click()
  await page.waitForSelector('.month-layout[data-view-mode="month"]')
  await page.waitForTimeout(800) // 等日视图补拉 entry

  // 断言 1：每个格子 scrollHeight <= clientHeight + 1（不越界）
  const overflow = await page.$$eval('.month-cell', (cells) =>
    cells.map((c) => ({
      date: c.querySelector('.cell-date')?.textContent?.trim(),
      scrollH: c.scrollHeight,
      clientH: c.clientHeight,
      overflow: c.scrollHeight - c.clientHeight,
    })),
  )
  const violators = overflow.filter((c) => c.overflow > 1)
  console.log('cells:', overflow.length, '| busy-day sample:', overflow.find((c) => Number(c.date) === 5) || overflow.find((c) => Number(c.date) === 15))

  // 断言 2：所有行高一致（同一个月 6 行的 grid 轨道高度应相等）
  const rowHeights = await page.$$eval('.month-cell', (cells) => {
    const rows = new Map()
    for (const c of cells) {
      const rect = c.getBoundingClientRect()
      const rowTop = Math.round(rect.top)
      rows.set(rowTop, rect.height)
    }
    return [...new Set([...rows.values()].map((h) => Math.round(h)))]
  })
  console.log('distinct row heights:', rowHeights)

  await page.screenshot({ path: 'scripts/month-overflow-check.png', fullPage: false })
  console.log('screenshot: scripts/month-overflow-check.png')

  await browser.close()

  if (violators.length) {
    console.error(`FAIL: ${violators.length} 个格子越界`, violators)
    process.exit(1)
  }
  console.log('PASS: 所有格子 scrollHeight <= clientHeight')
}

main().catch((e) => { console.error(e); process.exit(1) })
