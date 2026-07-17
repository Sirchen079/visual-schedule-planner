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

const longReply = [
  '我是知时助手，你的个人日程与资料管理参谋。核心能力如下：',
  '',
  '【任务管理】',
  '- 查看、创建、修改、归档任务',
  '- 规划任务时间线，设定优先级、起止时间、截止时间与阶段目标',
  '- 梳理任务间的依赖关系，识别瓶颈与风险',
  '',
  '【资料整理】',
  '- 创建、更新笔记与文件',
  '- 将资料关联到具体任务，或从任务中解绑',
  '- 沉淀关键信息，方便后续检索',
  '',
  '【规划参谋】',
  '- 把模糊需求拆成可执行步骤',
  '- 信息不足时，基于已知条件做保守安排并说明假设',
  '- 存在多种做法时，提供少量备选方案及利弊分析',
  '',
  '【安全边界】',
  '- 删除、清空、批量覆盖等高风险操作必须经你确认后才会执行',
  '- 对已有资料的覆盖需要明确展示影响范围',
  '- 长消息也必须完整显示，不能被聊天气泡截断',
].join('\n')

async function json(route, body, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json; charset=utf-8',
    body: JSON.stringify(body),
  })
}

async function mockBackend(page, { chatStatus = 200, chatBody } = {}) {
  await page.route('**/tasks', async (route) => {
    if (route.request().method() === 'GET') return json(route, [])
    return json(route, {})
  })
  await page.route('**/tasks/tags', async (route) => json(route, []))
  await page.route('**/reminders/due**', async (route) => json(route, { upcoming: [], overdue: [] }))
  await page.route('**/ai/configs', async (route) => {
    if (route.request().method() === 'GET') return json(route, [activeConfig])
    return json(route, activeConfig)
  })
  await page.route('**/ai/skills', async (route) => json(route, []))
  await page.route('**/ai/chat', async (route) => {
    if (chatStatus >= 400) return json(route, chatBody, chatStatus)
    return json(route, chatBody || {
      conversation_id: 'e2e-conversation',
      reply: longReply,
      tool_results: [],
      pending_actions: [],
    })
  })
}

function pendingActionChatBody() {
  return {
    conversation_id: 'e2e-conversation',
    reply: '这个操作需要确认。',
    tool_results: [],
    pending_actions: [
      {
        id: 42,
        conversation_id: 1,
        action_type: 'bulk_delete_tasks',
        summary: '模型摘要可能不完整',
        preview: [
          '操作: 批量将 2 个任务移入回收站',
          '任务: #1 真实任务一',
          '任务: #2 真实任务二',
        ],
        status: 'pending',
        expires_at: '2026-06-27T23:59:59',
        created_at: '2026-06-27T22:00:00',
      },
    ],
  }
}

test('desktop floating chat keeps long assistant replies readable and scrollable', async ({ page }) => {
  await mockBackend(page)
  await page.goto('/')

  await page.getByRole('button', { name: /知时助手/ }).click()

  const shell = page.locator('.assistant-shell')
  await expect(shell).toHaveAttribute('role', 'region')
  await expect(shell).not.toHaveAttribute('aria-modal')

  await page.getByPlaceholder(/帮我把本周论文阅读/).fill('说明你的能力')
  await page.getByRole('button', { name: '发送' }).click()

  const assistantMessage = page.locator('.message.assistant').last()
  await expect(assistantMessage).toContainText('安全边界')
  await expect(assistantMessage).toContainText('长消息也必须完整显示')

  const bubble = await assistantMessage.evaluate((el) => {
    const box = el.getBoundingClientRect()
    const content = el.querySelector('.message-content').getBoundingClientRect()
    return {
      bubbleHeight: box.height,
      contentBottom: content.bottom,
      boxBottom: box.bottom,
    }
  })
  expect(bubble.bubbleHeight).toBeGreaterThan(260)
  expect(bubble.contentBottom).toBeLessThanOrEqual(bubble.boxBottom + 2)

  const scroller = await page.locator('.messages').evaluate((el) => ({
    clientHeight: el.clientHeight,
    scrollHeight: el.scrollHeight,
    overflowY: getComputedStyle(el).overflowY,
  }))
  expect(scroller.overflowY).toBe('scroll')
  expect(scroller.scrollHeight).toBeGreaterThan(scroller.clientHeight)
})

test('settings remain reachable from the floating assistant', async ({ page }) => {
  await mockBackend(page)
  await page.goto('/')

  await page.getByRole('button', { name: /知时助手/ }).click()
  await page.getByRole('tab', { name: '设置' }).click()

  // 设置区为手风琴分组:摘要行全部可见,默认展开「模型配置」
  await expect(page.getByText('模型配置', { exact: true })).toBeVisible()
  await expect(page.getByText('人设', { exact: true })).toBeVisible()
  await expect(page.getByText('Skill 规则', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Provider')).toHaveValue('claude_messages')
  // HTTP Proxy 在折叠的「高级选项」组内,展开后可见
  await page.getByText('高级选项', { exact: true }).click()
  await expect(page.getByLabel('HTTP Proxy')).toHaveValue('http://127.0.0.1:7890')
})

test('desktop floating assistant can be dragged and stays in view', async ({ page }) => {
  await mockBackend(page)
  await page.goto('/')

  await page.getByRole('button', { name: /知时助手/ }).click()

  const shell = page.locator('.assistant-shell')
  const dragHandle = page.locator('.head-copy')
  const before = await shell.boundingBox()
  expect(before).not.toBeNull()
  const handleBox = await dragHandle.boundingBox()
  expect(handleBox).not.toBeNull()

  await page.mouse.move(handleBox.x + 20, handleBox.y + handleBox.height / 2)
  await page.mouse.down()
  await page.mouse.move(before.x - 1000, before.y - 1000, { steps: 5 })
  await page.mouse.up()

  const afterClamp = await shell.boundingBox()
  expect(afterClamp.x).toBeGreaterThanOrEqual(11)
  expect(afterClamp.y).toBeGreaterThanOrEqual(11)

  const clampedHandleBox = await dragHandle.boundingBox()
  expect(clampedHandleBox).not.toBeNull()
  await page.mouse.move(clampedHandleBox.x + 20, clampedHandleBox.y + clampedHandleBox.height / 2)
  await page.mouse.down()
  await page.mouse.move(240, 180, { steps: 5 })
  await page.mouse.up()

  const afterMove = await shell.boundingBox()
  expect(afterMove.x).not.toBeCloseTo(before.x, 0)
  expect(afterMove.y).not.toBeCloseTo(before.y, 0)
})

test('failed chat send restores input and redacts provider error details', async ({ page }) => {
  await mockBackend(page, {
    chatStatus: 500,
    chatBody: {
      detail: 'Authorization: Bearer sk-12345678901234567890 token=supersecretsecret provider failed',
    },
  })
  await page.goto('/')

  await page.getByRole('button', { name: /知时助手/ }).click()
  const input = page.getByPlaceholder(/帮我把本周论文阅读/)
  await input.fill('这条消息应该失败后恢复')
  await page.getByRole('button', { name: '发送' }).click()

  await expect(input).toHaveValue('这条消息应该失败后恢复')
  const alert = page.getByRole('alert')
  await expect(alert).toContainText('已隐藏')
  await expect(alert).not.toContainText('sk-12345678901234567890')
  await expect(alert).not.toContainText('supersecretsecret')
})

test('dangerous action cards show server generated preview lines', async ({ page }) => {
  await mockBackend(page, { chatBody: pendingActionChatBody() })
  await page.goto('/')

  await page.getByRole('button', { name: /知时助手/ }).click()
  await page.getByPlaceholder(/帮我把本周论文阅读/).fill('删除两个任务')
  await page.getByRole('button', { name: '发送' }).click()

  await expect(page.getByText('模型摘要可能不完整')).toBeVisible()
  await expect(page.getByText('操作: 批量将 2 个任务移入回收站')).toBeVisible()
  await expect(page.getByText('任务: #1 真实任务一')).toBeVisible()
  await expect(page.getByRole('button', { name: '第一次确认' })).toBeVisible()
})

test('mobile opens the assistant in fullscreen mode with settings available', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockBackend(page)
  await page.goto('/')

  await page.getByRole('button', { name: /知时助手/ }).click()

  const shell = page.locator('.assistant-shell')
  await expect(shell).toHaveClass(/fullscreen/)
  await expect(shell).toHaveAttribute('role', 'dialog')
  await expect(shell).toHaveAttribute('aria-modal', 'true')
  await expect(page.getByRole('button', { name: '退出全屏' })).toBeVisible()

  await page.getByRole('tab', { name: '设置' }).click()
  await expect(page.getByText('模型配置', { exact: true })).toBeVisible()
})
