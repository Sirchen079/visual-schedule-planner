import { describe, expect, it } from 'vitest'
import { toolActionLabel, toolDisplayName } from './toolDisplay'

describe('工具友好名', () => {
  it('已知工具映射为中文短语', () => {
    expect(toolDisplayName('create_task')).toBe('创建任务')
    expect(toolDisplayName('show_blackboard')).toBe('黑板')
    expect(toolDisplayName('update_work_plan')).toBe('更新执行计划')
    expect(toolDisplayName('list_month_schedule')).toBe('查看月历')
  })
  it('MCP 工具显示去前缀短名，未知工具回退原名', () => {
    expect(toolDisplayName('mcp__feishu__send__msg')).toBe('send__msg')
    expect(toolDisplayName('some_custom_tool')).toBe('some_custom_tool')
  })
  it('阶段提示：动宾短语拼「正在」，特例单独映射，未知回退「正在执行」', () => {
    expect(toolActionLabel('create_task')).toBe('正在创建任务')
    expect(toolActionLabel('update_task')).toBe('正在更新任务')
    expect(toolActionLabel('search_tools')).toBe('正在查找工具')
    expect(toolActionLabel('show_blackboard')).toBe('正在绘制黑板')
    expect(toolActionLabel('ask_user')).toBe('正在向你提问')
    expect(toolActionLabel('task')).toBe('正在派出子代理')
    expect(toolActionLabel('mcp__x__y')).toBe('正在执行 y')
    expect(toolActionLabel('unknown_tool')).toBe('正在执行 unknown_tool')
  })
})
