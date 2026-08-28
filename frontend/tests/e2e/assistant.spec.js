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

// SSE 帧格式与 consumeSseStream（frontend/src/api/ai.js:293）对齐：
// 每帧 "event: <名>\ndata: <json>\n\n"。mockChatStream 把一组 [event, data] 序列编为 SSE body。
function sseBody(events) {
  return events.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join('')
}

// 主流是 SSE 流式（streamAiChat → POST /ai/chat/stream）。mock 该端点返回事件序列。
// events 形如 [['meta', {...}], ['text_delta', {delta:'...'}], ['done', {...}]]。
async function mockChatStream(page, events, { status = 400, errorBody } = {}) {
  await page.route('**/ai/chat/stream', async (route) => {
    if (status >= 400) {
      return route.fulfill({
        status,
        contentType: 'application/json; charset=utf-8',
        body: JSON.stringify(errorBody ?? {}),
      })
    }
    return route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
      body: sseBody(events),
    })
  })
}

async function mockBackend(page, { chatStatus = 200, chatBody, streamEvents, errorBody } = {}) {
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
  await page.route('**/settings', async (route) => json(route, { onboarding_done: '1', agent_autonomy: 'standard' }))
  // 阶段 D1：grants 端点 mock（默认空列表）
  const grants = []
  await page.route('**/ai/grants', async (route) => {
    if (route.request().method() === 'GET') return json(route, grants)
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON()
      grants.push({ id: grants.length + 1, tool_name: body.tool_name, arg_pattern: body.arg_pattern || '', created_at: '2026-07-24T10:00:00' })
      return json(route, grants[grants.length - 1], 201)
    }
    return json(route, {})
  })
  page._e2eGrants = grants
  // 兼容旧非流式端点（应用发送走 stream 路径，但保留以防个别分支）
  await page.route('**/ai/chat', async (route) => {
    if (chatStatus >= 400) return json(route, chatBody, chatStatus)
    return json(route, chatBody || {
      conversation_id: 'e2e-conversation',
      reply: longReply,
      tool_results: [],
      pending_actions: [],
    })
  })
  // 默认流式序列：meta → 长文本增量 → done。各用例可覆盖。
  // 错误路径（chatStatus>=400）：流端点返回 errorBody，streamEvents 保持 undefined 不发事件序列。
  if (streamEvents === undefined && chatStatus < 400) {
    streamEvents = [
      ['meta', { conversation_id: 'e2e-conversation', assistant_name: '知时助手', run_id: 'e2e-run', resumed: false }],
      ['text_delta', { step: 1, delta: longReply }],
      ['done', {
        reply: longReply,
        tool_results: [],
        pending_actions: [],
        reached_limit: false,
        cancelled: false,
        usage: { prompt_tokens: 10, completion_tokens: 20, total_tokens: 30, calls: 1 },
        elapsed_ms: 123,
        reasoning: '',
      }],
    ]
  }
  // 流端点必须始终被 mock：错误态返回 errorBody JSON；正常态返回 SSE 事件序列。
  await mockChatStream(page, streamEvents || [], { status: chatStatus, errorBody })
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

  await page.getByRole('button', { name: /知时(助手|代理)/ }).click()

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

  await page.getByRole('button', { name: /知时(助手|代理)/ }).click()
  await page.getByRole('tab', { name: '设置' }).click()

  // 设置区为手风琴分组:摘要行全部可见,默认展开「模型配置」
  await expect(page.getByText('模型配置', { exact: true })).toBeVisible()
  await expect(page.getByText('人设', { exact: true })).toBeVisible()
  await expect(page.getByText('Skill 规则', { exact: true })).toBeVisible()
  // Provider 下拉：用相邻 span 文本定位 select（label 非显式关联，getByLabel 会误匹配思维链复选框）
  const providerSelect = page.locator('label:has(span:has-text("Provider")) select').first()
  await expect(providerSelect).toHaveValue('claude_messages')
  // HTTP Proxy 在折叠的「高级选项」组内,展开后可见
  await page.getByText('高级选项', { exact: true }).click()
  await expect(page.getByLabel('HTTP Proxy')).toHaveValue('http://127.0.0.1:7890')
})

test('desktop floating assistant can be dragged and stays in view', async ({ page }) => {
  await mockBackend(page)
  await page.goto('/')

  await page.getByRole('button', { name: /知时(助手|代理)/ }).click()

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
  // 流式路径的错误脱敏：streamAiChat 收到 !res.ok 时走 compactErrorMessage（api.js:259），
  // 与非流式同一函数，行为一致——密钥串被替换为「已隐藏」。
  await mockBackend(page, {
    chatStatus: 500,
    errorBody: {
      detail: 'Authorization: Bearer sk-12345678901234567890 token=supersecretsecret provider failed',
    },
  })
  await page.goto('/')

  await page.getByRole('button', { name: /知时(助手|代理)/ }).click()
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
  // 危险操作：流式发 pending_confirmation 事件 + done 帧携带 pending_actions（含 preview）。
  const pendingAction = pendingActionChatBody().pending_actions[0]
  await mockBackend(page, {
    streamEvents: [
      ['meta', { conversation_id: 'e2e-conversation', assistant_name: '知时助手', run_id: 'e2e-run', resumed: false }],
      ['text_delta', { step: 1, delta: '这个操作需要确认。' }],
      ['pending_confirmation', {
        step: 1,
        actions: [{ action_type: 'bulk_delete_tasks', summary: '模型摘要可能不完整' }],
      }],
      ['step_finish', { step: 1 }],
      ['done', {
        reply: '这个操作需要确认。',
        tool_results: [],
        pending_actions: [pendingAction],
        reached_limit: false,
        cancelled: false,
        usage: { prompt_tokens: 10, completion_tokens: 20, total_tokens: 30, calls: 1 },
        elapsed_ms: 123,
        reasoning: '',
      }],
    ],
  })
  await page.goto('/')

  await page.getByRole('button', { name: /知时(助手|代理)/ }).click()
  await page.getByPlaceholder(/帮我把本周论文阅读/).fill('删除两个任务')
  await page.getByRole('button', { name: '发送' }).click()

  await expect(page.getByText('模型摘要可能不完整')).toBeVisible()
  await expect(page.getByText('操作: 批量将 2 个任务移入回收站')).toBeVisible()
  await expect(page.getByText('任务: #1 真实任务一')).toBeVisible()
  await expect(page.getByRole('button', { name: '第一次确认' })).toBeVisible()
})

test('grant toggle on confirm card creates an always-allow rule', async ({ page }) => {
  // 阶段 D1：确认卡片「以后都允许」勾选 → 点首次确认 → 创建 grant，同类操作以后免确认。
  const pendingAction = pendingActionChatBody().pending_actions[0]
  await mockBackend(page, {
    streamEvents: [
      ['meta', { conversation_id: 'e2e-conversation', assistant_name: '知时助手', run_id: 'e2e-run', resumed: false }],
      ['text_delta', { step: 1, delta: '需要确认。' }],
      ['pending_confirmation', { step: 1, actions: [{ action_type: 'bulk_delete_tasks', summary: '模型摘要' }] }],
      ['done', {
        reply: '需要确认。', tool_results: [],
        pending_actions: [pendingAction], reached_limit: false, cancelled: false,
        usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2, calls: 1 }, elapsed_ms: 1, reasoning: '',
      }],
    ],
  })
  await page.goto('/')
  await page.getByRole('button', { name: /知时(助手|代理)/ }).click()
  await page.getByPlaceholder(/帮我把本周论文阅读/).fill('删除任务')
  await page.getByRole('button', { name: '发送' }).click()

  // 勾选「以后都允许」
  const grantToggle = page.locator('.grant-toggle input[type="checkbox"]').first()
  await grantToggle.check()
  await expect(grantToggle).toBeChecked()

  // 点首次确认 → 应触发 grant 创建（POST /ai/grants）
  await page.getByRole('button', { name: '第一次确认' }).click()
  await expect.poll(() => page._e2eGrants.length).toBe(1)
  expect(page._e2eGrants[0].tool_name).toBe('bulk_delete_tasks')
})

test('mobile opens the assistant in fullscreen mode with settings available', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockBackend(page)
  await page.goto('/')

  await page.getByRole('button', { name: /知时(助手|代理)/ }).click()

  const shell = page.locator('.assistant-shell')
  await expect(shell).toHaveClass(/fullscreen/)
  await expect(shell).toHaveAttribute('role', 'dialog')
  await expect(shell).toHaveAttribute('aria-modal', 'true')
  await expect(page.getByRole('button', { name: '退出全屏' })).toBeVisible()

  await page.getByRole('tab', { name: '设置' }).click()
  await expect(page.getByText('模型配置', { exact: true })).toBeVisible()
})

test('empty chat hides config guide card when an enabled model config exists', async ({ page }) => {
  // 回归：已配置并启用模型时，空对话不应显示「需要先配置模型才能开始对话」引导卡。
  // 此前 AssistantChat 依赖 App.vue 注入的 ai-available（仅主窗口 onMounted 读一次），
  // 悬浮窗路径下该注入恒为 false，导致已配置模型仍误显示引导卡。
  await mockBackend(page)
  await page.goto('/')

  await page.getByRole('button', { name: /知时(助手|代理)/ }).click()

  // 空对话应显示正常引导文案，而非配置引导卡
  await expect(page.getByText('从一个想法开始')).toBeVisible()
  await expect(page.getByText('需要先配置模型才能开始对话')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '去配置' })).toHaveCount(0)
})

test('empty chat shows config guide card when no enabled model config exists', async ({ page }) => {
  // 反向用例：无已启用配置时，空对话应显示配置引导卡并提供「去配置」入口。
  await mockBackend(page)
  // 覆盖 /ai/configs：返回一个未启用的配置
  await page.route('**/ai/configs', async (route) => {
    if (route.request().method() === 'GET') {
      return json(route, [{ ...activeConfig, enabled: false }])
    }
    return json(route, { ...activeConfig, enabled: false })
  })
  await page.goto('/')

  await page.getByRole('button', { name: /知时(助手|代理)/ }).click()

  await expect(page.getByText('需要先配置模型才能开始对话')).toBeVisible()
  await expect(page.getByRole('button', { name: '去配置' })).toBeVisible()
  await expect(page.getByText('从一个想法开始')).toHaveCount(0)
})
