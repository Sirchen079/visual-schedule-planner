// 悬浮窗（?view=assistant）展开后复用程序内助手样式的回归测试。
// 验证 F1~F3 改动：展开尺寸与设计值对齐、float-mode 瘦身补丁已拆除（回落基础样式）、
// 全屏按钮隐藏。mock 后端后断言计算样式，确保与程序内展开态肉眼一致。
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
  proxy_url: '',
  extra_headers: {},
  enabled: true,
  active_skill_id: null,
}

async function json(route, body, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json; charset=utf-8',
    body: JSON.stringify(body),
  })
}

// 悬浮窗仅渲染 AssistantFloat -> AssistantView，需 mock 助手初始化依赖的端点。
async function mockBackend(page) {
  await page.route('**/tasks', (route) =>
    route.request().method() === 'GET' ? json(route, []) : json(route, {}),
  )
  await page.route('**/tasks/tags', (route) => json(route, []))
  await page.route('**/reminders/due**', (route) => json(route, { upcoming: [], overdue: [] }))
  await page.route('**/ai/configs', (route) =>
    route.request().method() === 'GET' ? json(route, [activeConfig]) : json(route, activeConfig),
  )
  await page.route('**/ai/skills', (route) => json(route, []))
  await page.route('**/settings', (route) =>
    json(route, { onboarding_done: '1', agent_autonomy: 'standard' }),
  )
  await page.route('**/ai/grants', (route) => json(route, []))
  // 流式端点占位：本用例不发送消息，仅验证布局。
  await page.route('**/ai/chat/stream', (route) =>
    route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
      body: '',
    }),
  )
  await page.route('**/ai/chat', (route) =>
    json(route, { conversation_id: 'e2e-float', reply: '', tool_results: [], pending_actions: [] }),
  )
}

test('float window expands to in-app assistant layout: full-screen hidden, title 18px, icon visible', async ({
  page,
}) => {
  await mockBackend(page)
  // ?view=assistant -> App.vue 渲染 <AssistantFloat>（按钮态 60×60）
  await page.goto('/?view=assistant')

  // 点击悬浮球展开 -> AssistantView(float-mode) 显示
  await page.getByRole('button', { name: '知时助手' }).click()

  const shell = page.locator('.assistant-shell.float-mode')
  await expect(shell).toBeVisible()

  // F3：全屏按钮已隐藏（悬浮窗为独立 OS 窗口，无需窗口内全屏）
  await expect(shell.locator('.fullscreen-action')).not.toBeVisible()

  // F3：标题字号回落到基础 :not(.fullscreen) 的 18px（瘦身补丁原为 15px，已拆除）
  const h2 = shell.locator('.assistant-head h2')
  await expect(h2).toHaveCSS('font-size', '18px')

  // F3：标题图标恢复可见（瘦身补丁原 display:none，已拆除）
  await expect(shell.locator('.assistant-head .page-title .art-icon')).toBeVisible()

  // F1：shell 填满视口（position:absolute; inset:0）--展开尺寸由窗口保证
  const box = await shell.boundingBox()
  const vp = page.viewportSize()
  expect(box).not.toBeNull()
  expect(Math.round(box.width)).toBe(vp.width)
  expect(Math.round(box.height)).toBe(vp.height)
})
