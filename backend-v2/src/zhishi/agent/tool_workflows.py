"""Small task-oriented routes, filtered against the current enabled toolset."""
from __future__ import annotations

ROUTES = (
    ('拆分任务', ('子任务', '拆分', 'subtask'), (), (
        ('list_tasks', '定位已有父任务；已有 task_id 时跳过'), ('get_task', '查看已有子任务'),
        ('create_subtasks', '批量传入结构化条目，整批保存并跳过同名已有子任务'),
        ('get_task', '核对真实子任务，不把文字清单当作已创建'))),
    ('学习研究计划', ('学习计划', '研究计划', '学习方案', '研究项目', 'research project', 'study plan'), (), (
        ('list_research_projects', '检查已有项目，继续已有目标时复用 project_id'),
        ('create_research_project', '有明确新目标时创建项目'),
        ('research_project_sources', '程序检索并收集项目资料，不手工拼多次网页调用'),
        ('get_research_project', '读取资料、约束和当前版本'),
        ('preview_research_plan', '生成可检查的计划草稿，保留真实出处'),
        ('apply_research_plan', '确认后整批落实草稿，不逐条重新创建任务'))),
    ('整理收件箱', ('收件箱', '提取事项', '整理附件', 'inbox'), (), (
        ('read_material', '读取附件正文和原始证据'), ('propose_inbox_items', '提取为候选事项；不明确的日期金额先询问'),
        ('get_inbox_item', '读取候选最新版本'), ('apply_inbox_item', '用户确认后落实候选，不另外创建重复事项'),
        ('get_inbox_item', '核对已关联的实际记录'))),
    ('导入课表', ('课表', '课程表', 'timetable'), ('导入', '整理', 'import'), (
        ('list_files', '定位附件 file_id；已知 ID 时跳过'), ('read_material', '读取原始课程、周次与节次'),
        ('import_timetable', '确认学期起始周一后批量导入；程序计算日期、重复规则、去重和冲突'))),
    ('修改日程', ('日程', '会议', '预约', '行程', 'event', 'meeting'), ('修改', '改', '移动', '调整', 'update', 'move'), (
        ('list_day_schedule', '按原日期定位 event_id；多条同名先询问'),
        ('get_event', '读取完整原值；重复日程修改作用于整个系列'),
        ('update_event', '仅提交用户要求改变的字段，等待审批结果'),
        ('get_event', '核对保存后的时间与提醒'))),
    ('安排一天', ('排期', '排程', '安排任务', '安排一天', '计划一天', 'plan day', 'schedule tasks'), (), (
        ('get_current_time', '确认当前本机日期'), ('resolve_local_date', '将相对日期转为 ISO 日期'),
        ('plan_day', '程序计算空闲时段与容量，返回完整 next_call'),
        ('apply_day_plan', '确认后直接使用 next_call 参数，整批校验并保存'),
        ('list_day_schedule', '核对最终日程'))),
    ('创建提醒或任务', ('提醒', '待办', '任务', 'remind', 'todo', 'task'), ('创建', '添加', '提醒', '新建', 'create', 'add', 'remind'), (
        ('get_current_time', '读取本机当前时间'), ('resolve_local_date', '把用户相对日期转为 ISO 日期'),
        ('create_task', '待办提醒同时传 due_date、due_time、remind_offsets=[0]'),
        ('get_task', '核对真实创建结果；固定会议日程应使用 create_event'))),
    ('创建日程', ('日程', '会议', '预约', '行程', 'event', 'meeting'), ('创建', '添加', '新增', '安排', '新建', 'create', 'add', 'schedule'), (
        ('get_current_time', '读取本机时间'), ('resolve_local_date', '解析用户日期'),
        ('list_day_schedule', '核对当天已有安排'), ('create_event', '固定事项直接创建日程，可同时设置提醒'),
        ('get_event', '核对创建结果'))),
    ('修改任务', ('任务', '待办', 'todo', 'task'), ('修改', '更新', '改', '完成', 'update', 'complete'), (
        ('list_tasks', '用 query 定位真实 task_id'), ('get_task', '读取截止、重复、提醒和当前状态'),
        ('update_task', '仅传修改字段；清空时间使用 clear_due_date/clear_due_time'),
        ('get_task', '核对保存结果'))),
    ('记账', ('记账', '支出', '收入', '花了', '账本', 'expense', 'income', 'ledger'), ('记账', '记录', '花了', '入账', 'record', 'spent'), (
        ('list_transactions', '需要核对已有收支时查询；账户使用用户给定名称，不编造'),
        ('record_transaction', '按真实交易填写金额和日期；重试复用幂等键'),
        ('get_transaction', '使用返回的 entry_id 核对，不重复记录合计与明细'))),
    ('账单处理', ('账单', '缴费', 'bill'), ('付款', '支付', '缴费', '已交', 'pay', 'paid'), (
        ('list_bills', '找到目标账单'), ('get_bill', '读取账单与待处理期次'),
        ('get_bill_occurrence', '取得期次最新版本'), ('confirm_bill_payment', '用户实际已付款才记入支出，保留原版本与金额'),
        ('get_bill', '核对支付结果和下一期'))),
    ('联网检索', ('联网', '网上', '查资料', '网页', '网址', 'web', 'search online'), (), (
        ('web_search', '直接传 query，不必选择或研究搜索供应商'),
        ('web_fetch', '读取结果中的真实 URL，按正文回答并保留来源'))),
    ('读取资料', ('文档', '资料', '文件', '附件', 'pdf', 'document', 'material'), (), (
        ('list_files', '定位 file_id；已有附件 ID 时跳过'),
        ('read_material', '直接读取正文与表格；按 next_call 翻页'),
        ('search_materials', '需要具体信息时按关键词定位，保留出处'))),
    ('习惯打卡', ('打卡', '习惯', 'habit'), (), (
        ('list_habits', '找到 habit_id 和当前次数'), ('check_in_habit', '一次实际打卡加1；重试不会重复增加'),
        ('list_habits', '核对打卡次数'))),
)


def route_for(query: str, available: set[str]) -> dict | None:
    text = query.casefold()
    for title, subjects, actions, steps in ROUTES:
        if not any(word in text for word in subjects) or actions and not any(word in text for word in actions):
            continue
        present = [{'tool':tool, 'purpose':purpose} for tool, purpose in steps if tool in available]
        if not present:
            continue
        missing = list(dict.fromkeys(tool for tool, _ in steps if tool not in available))
        return {'name':title, 'steps':present, 'unavailable_tools':missing,
                'note':'只执行用户要求的步骤，查询请求不执行写入。跳过已完成的读取；ID、日期和 next_call 用实际返回值。缺失工具不可执行，不绕过审批或功能开关。'}
    return None
