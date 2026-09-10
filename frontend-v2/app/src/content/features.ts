export interface FeatureLesson {
  id: string
  name: string
  path: string | null
  article: string
  purpose: string
  example: string
  steps: string[]
  targets: string[]
}

// Keep these lessons in the same order as the sidebar, after the chat entry.
export const FEATURE_LESSONS: FeatureLesson[] = [
  {
    id: 'chat', name: '对话', path: null, article: '对话：用一句话交代事情',
    purpose: '在对话区告诉 AI 要做什么，也可以上传附件。宽窗口左侧常驻对话区，窄窗口点左侧“对话”打开。',
    example: '例如：把这份通知整理成待办，先让我核对。',
    steps: ['在“设置 → AI 模型”添加并启用配置。', '在底部输入框写下要求；点回形针选择附件，点向上箭头发送。', '收到问题卡时填写答案并提交；收到审批卡时查看操作内容，选择同意或拒绝。', '到看板、日历或账本查看保存结果。新话题点顶部“＋”新建会话，历史会话从列表找回。'],
    targets: ['.chat .inputzone', '.chat textarea', '.chat-head'],
  },
  {
    id: 'research', name: '学习与研究', path: '/research', article: '学习与研究：把目标变成分步计划',
    purpose: '把学习资料、步骤、时间安排和进度放在一个项目里。',
    example: '例如：两周学习基础摄影，每天投入半小时，并保留参考材料。',
    steps: ['点“新建项目”，填写主题、预期成果、开始日期和每天可用时间，保存项目。', '在“项目资料”上传材料、添加链接或从资料库选择。配置联网服务后还可检索资料。', '点“手动拟定步骤”，或让 AI 根据资料制定计划。点“预览时间安排”，检查后点“确认落实计划”。', '在“实际进度”记录完成情况和遇到的问题，按进度调整内容或重新预览排期。'],
    targets: ['.research-view .project-form', '.research-view > header button'],
  },
  {
    id: 'today', name: '今日', path: '/', article: '今日：先看今天怎么过',
    purpose: '查看今天的安排、下一项事情、时间冲突和空闲时段。',
    example: '每天开始时先看这里，确认下一项安排和今天是否有时间重叠。',
    steps: ['看“现在时刻”和下一项安排，确认开始时间与地点。', '查看冲突提示和“今日空闲”，空闲时段按已录入的安排计算。', '右侧按时间列出今天的安排。其他日期去日历查看，未排时间的待办去看板找。', '准备专心做一件事时，打开右下角的专注计时，记录投入时间。'],
    targets: ['.today-view .now-panel'],
  },
  {
    id: 'inbox', name: '收件箱', path: '/inbox', article: '收件箱：先核对，再落实',
    purpose: '把通知、收据或想法整理成待办、日程和收支草稿，在这里核对并保存。',
    example: '例如：收到一份会议通知，先确认日期、地点，再加入日历。',
    steps: ['在对话中上传材料，请 AI 整理到收件箱；也可以点“手动整理”。', '选择“待办 / 日程 / 收支”，填写内容和原文依据，点“保存候选”。', '在“待确认”中点“核对 / 编辑”，补齐待澄清的信息，再点“确认落实”写入看板、日历或账本。', '在“已落实”中点链接查看记录。不需要的候选可点“忽略”，以后还能修正并重新整理。'],
    targets: ['.inbox-view .editor', '.inbox-view > header button'],
  },
  {
    id: 'calendar', name: '日历', path: '/calendar', article: '日历：查看和修改具体时间安排',
    purpose: '按日、周、月查看时间安排，编辑日程或导出日历文件。',
    example: '例如：明天 15:00–16:00 开会，改到 16:00 开始。',
    steps: ['点“日 / 周 / 月”切换视图，左右箭头翻页，“今天 / 本周 / 本月”回到当前日期。', '点已有日程块查看并编辑，保存修改。重复日程的修改会作用于整个系列。', '新增日程可直接告诉 AI，或在收件箱手动整理为“日程”后确认落实。', '点右上角“导出日历”保存 ICS 文件，再导入手机日历。时间改动后需要重新导出。'],
    targets: ['[data-tour="calendar-controls"]'],
  },
  {
    id: 'board', name: '看板', path: '/board', article: '看板：管理要做的事情',
    purpose: '记录待办、查看截止日期和优先级，把大任务拆成子任务。',
    example: '例如：取快递、整理材料，或把一个大任务拆成几个小步骤。',
    steps: ['点“新建任务”，填标题，按需设置截止日期和优先级，点“创建”。保存后会出现任务卡片。', '点“按状态 / 按日期”切换分组，查看进行中、已完成或逾期等任务。', '做完后点任务前面的圆圈，误点可再点一次取消。子任务可以分别勾选。', '需要排期时，告诉 AI 任务名称和可用时间。删除的任务可到左侧回收站恢复。'],
    targets: ['.board-view .creator', '[data-tour="new-task"]'],
  },
  {
    id: 'timeline', name: '时间轴', path: '/timeline', article: '时间轴：提前看任务截止和负载',
    purpose: '按日期查看未来 14 天的任务截止时间和排期，找出任务集中的日子。',
    example: '例如：本周有三件事同一天截止，先调整顺序或分几天完成。',
    steps: ['从上到下查看日期：“截止”标记表示任务到期，具体时段表示已排期。', '右侧的预计分钟数来自任务时长估算，可用来判断当天任务量。', '列表为空时，到看板设置任务截止日期，或让 AI 安排任务时间。', '任务太集中时，告诉 AI 要调整的任务和日期。会议等独立日程到日历查看。'],
    targets: ['.tl-view .tl-head'],
  },
  {
    id: 'habits', name: '习惯', path: '/habits', article: '习惯：记录反复做的事',
    purpose: '为散步、运动等每天或每周重复的事情打卡，查看次数和连续记录。',
    example: '例如：每天散步一次、每周运动三次。',
    steps: ['点“新建习惯”，填写名称，选择每日或每周，设置目标次数后点“创建”。', '完成一次后，在习惯卡片上点“打卡”。', '误点可点击“今日已打卡”撤销。把鼠标停在近 14 天的小方块上，可查看当天次数。', '需要固定时间提醒时，另设日程或提醒。'],
    targets: ['.habits-view .creator', '[data-tour="habits-create"]'],
  },
  {
    id: 'journal', name: '日记', path: '/journal', article: '日记：留下当天的记录',
    purpose: '按日期写日记、选择心情，随时回看过去的记录。',
    example: '例如：记录今天完成了什么、遇到什么问题、明天想改进什么。',
    steps: ['在顶部选择要写的日期。', '在内容框写日记，按需选择心情。', '点“保存这一页”，“未保存”提示消失后就保存好了。切换日期或栏目之前记得保存。', '点击历史列表中的日期，回看或继续编辑那一天的日记。'],
    targets: ['.journal-view .jv-editor', '[aria-label="选择日记日期"]'],
  },
  {
    id: 'ledger', name: '账本', path: '/ledger', article: '账本：记收支，也管待付账单',
    purpose: '记录收支、查看月度汇总，设置待付款的周期账单和到期提醒。',
    example: '例如：记一笔交通支出，并提醒下个月缴费。',
    steps: ['点“记一笔”，选收入或支出，填写日期、金额、币种、分类和账户，点“保存账目”。', '按月份、币种、账户或关键词筛选，查看明细和分类汇总。不同币种分别计算。', '固定开支点“添加账单”。付款后点“确认已支付”记账，已有账目可直接关联。', '误删账目时，勾选账本页面内的“回收站”，找到记录后恢复。'],
    targets: ['.ledger-view .entry-form', '.ledger-view .intro button'],
  },
  {
    id: 'goals', name: '目标', path: '/goals', article: '目标：用数字衡量长期成果',
    purpose: '为长期目标设置可量化的关键结果，记录完成进度。',
    example: '例如：整理家庭照片，以“完成 5 个相册”作为关键结果。',
    steps: ['点“新建目标”，填标题，按需填开始日期和备注，点“创建”。', '点目标卡上的“＋ 关键结果”，填写名称、目标值和单位，点“添加”。', '有进展时修改当前进度，离开输入框后会保存，进度条随之更新。', '阶段结束后可归档目标。需要学习步骤、资料和排期时，可新建学习与研究项目。'],
    targets: ['.goals-view .creator', '[data-tour="goals-create"]'],
  },
  {
    id: 'library', name: '资料库', path: '/library', article: '资料库：保存、查找和阅读材料',
    purpose: '保存文件和网页资料，按名称或正文查找内容，阅读并补充备注。',
    example: '例如：把说明书、会议材料放进来，之后查找其中某段内容。',
    steps: ['点“上传资料”选择文件，上传完成后会出现在列表中。对话附件也保存在这里。', '顶部搜索框可找文件名；查找某句话时使用正文检索，按提示建立或刷新索引。', '打开材料阅读分段正文。内容缺失时查看解析状态和错误提示。', '要提取任务或制定计划，把材料交给 AI 并说明要求。误删文件可到左侧回收站恢复。'],
    targets: ['[data-tour="library-upload"]'],
  },
  {
    id: 'reports', name: '日报周报', path: '/reports', article: '日报周报：回顾一段时间',
    purpose: '查看晨报、日报和周报，回顾一段时间的安排与完成情况。',
    example: '例如：周末回顾这一周做了什么、哪些事情还没完成。',
    steps: ['点“全部 / 晨报 / 日报 / 周报”筛选，选择一份报告阅读。', '生成新报告前添加并启用 AI 配置，再点“生成日报”或“生成周报”。', '查看报告日期，对照这一时段保存的任务和记录。', '删除报告时会弹出确认提示，删除后无法恢复。'],
    targets: ['.reports-view .rv-filters'],
  },
  {
    id: 'trash', name: '回收站', path: '/trash', article: '回收站：找回误删的任务和资料',
    purpose: '找回误删的任务和资料，或彻底删除已不需要的内容。',
    example: '例如：误删一条待办，找到它后点“恢复”。',
    steps: ['查看“任务”和“资料”列表，刚删除的条目可点“刷新”获取。', '找到要取回的记录，点“恢复”。', '返回看板或资料库查看原记录，列表未更新时重新进入或刷新。', '确定不再需要的内容可以“彻底删除”，此操作无法恢复。'],
    targets: ['.trash-view .tvv-head'],
  },
  {
    id: 'settings', name: '设置', path: '/settings', article: '设置：按需要调整软件',
    purpose: '调整外观、悬浮窗和通知，配置 AI 及其他服务。',
    example: '想显示悬浮窗找“悬浮窗与通知”；想接入模型找“AI 模型”。',
    steps: ['“悬浮窗与通知”中设置桌面小窗、通知和更新；“外观与 AI 助手”中设置主题、权限和工作时间。', '在“AI 模型”添加并启用模型，在“联网与视觉”配置搜索、网页和图片服务。', '“技能”管理 AI 使用的规则与知识，“外部工具”连接 MCP 服务，“授权”查看和撤回永久授权。', '在“自动跟进”设置持续检查和自动安排。模型配置的详细步骤见 AI 接入教程。'],
    targets: ['.settings-nav'],
  },
]

export const FEATURE_START = 5
export const TOUR_END = FEATURE_START + FEATURE_LESSONS.length
export function featureForArticle(title: string) { return FEATURE_LESSONS.find(feature => feature.article === title) }
