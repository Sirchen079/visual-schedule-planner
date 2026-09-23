/**
 * 工具友好名：内部工具名 → 中文短语，用于工具卡片标题与状态条的阶段提示
 * （机制借鉴 WorkBuddy 的 phase.tool_executing 按工具出标签）。未知工具回退原名。
 */

/** 动宾短语：多数场景直接拼「正在 + 短语」得到阶段提示。 */
const NAMES: Record<string, string> = {
  // 核心工具
  search_tools: '查找工具',
  execute_tool: '执行工具',
  ask_user: '向你提问',
  update_work_plan: '更新执行计划',
  read_tool_result: '读取大结果',
  show_blackboard: '黑板',
  task: '派出子代理',
  // 任务
  create_task: '创建任务',
  update_task: '更新任务',
  delete_task: '删除任务',
  bulk_delete_tasks: '批量删除任务',
  get_task: '查询任务',
  list_tasks: '查询任务列表',
  create_subtasks: '拆解子任务',
  update_subtask: '更新子任务',
  delete_subtask: '删除子任务',
  assign_task_to_day: '安排任务日期',
  reschedule_overdue: '重排逾期任务',
  // 日程
  create_event: '创建日程',
  update_event: '更新日程',
  delete_event: '删除日程',
  get_event: '查询日程',
  list_day_schedule: '查看今日日程',
  list_month_schedule: '查看月历',
  check_conflicts: '检查日程冲突',
  find_free_slots: '查找空闲时段',
  get_range_load: '查看日程负载',
  plan_day: '规划一天',
  propose_plan: '起草日计划',
  apply_day_plan: '应用日计划',
  resolve_local_date: '解析日期',
  import_timetable: '导入课表',
  import_document: '导入文档',
  import_web_resources: '收藏网页资料',
  get_current_time: '获取当前时间',
  // 习惯 / 目标 / 日记 / 计时
  check_in_habit: '习惯打卡',
  list_habits: '查询习惯',
  update_habit: '更新习惯',
  delete_habit: '删除习惯',
  list_goals: '查询目标',
  update_goal: '更新目标',
  delete_goal: '删除目标',
  update_kr_progress: '更新关键结果',
  write_journal: '写日记',
  list_journal_entries: '查询日记',
  list_notifications: '查看通知',
  start_timer: '开始计时',
  stop_timer: '停止计时',
  // 文件 / 其他
  list_files: '查看文件',
  bulk_delete_files: '批量删除文件',
  empty_trash: '清空回收站',
  web_search: '联网搜索',
  web_fetch: '抓取网页',
}

/** 拼不出「正在 + 短语」的特例单独给阶段提示。 */
const ACTION_OVERRIDES: Record<string, string> = {
  show_blackboard: '正在绘制黑板',
  ask_user: '正在向你提问',
  web_search: '正在联网搜索',
  web_fetch: '正在抓取网页',
  task: '正在派出子代理',
  get_current_time: '正在获取当前时间',
}

/** 工具友好名：已知工具给中文短语；MCP 工具给去掉来源前缀的短名；未知回退原名。 */
export function toolDisplayName(name: string): string {
  if (NAMES[name]) return NAMES[name]
  if (name.startsWith('mcp__')) {
    const parts = name.split('__')
    if (parts.length >= 3) return parts.slice(2).join('__')
  }
  return name
}

/** 流式阶段提示（状态条「执行工具」阶段按工具出标签）。 */
export function toolActionLabel(name: string): string {
  if (ACTION_OVERRIDES[name]) return ACTION_OVERRIDES[name]
  if (NAMES[name]) return `正在${NAMES[name]}`
  return `正在执行 ${toolDisplayName(name)}`
}
