import { formatQuickHint, parseQuickInput } from '../src/utils/quickparse.js'

// 固定「现在」：2026-06-15（周一）10:30，保证日期断言可复现
const NOW = new Date(2026, 5, 15, 10, 30)

function checkParse(name, input, expected) {
  const actual = parseQuickInput(input, NOW)
  const mismatch = Object.keys(expected).find(
    (key) => JSON.stringify(actual[key]) !== JSON.stringify(expected[key])
  )
  return {
    name: mismatch
      ? `${name} — 字段 ${mismatch} 期望 ${JSON.stringify(expected[mismatch])}，实得 ${JSON.stringify(actual[mismatch])}`
      : name,
    pass: !mismatch,
  }
}

const checks = [
  {
    name: '测试基准日期是周一（否则周 X 相关断言全部不可信）',
    pass: NOW.getDay() === 1,
  },
  checkParse('明天', '明天 交周报', {
    title: '交周报',
    due_date: '2026-06-16',
    due_time: null,
    priority: null,
    tags: [],
  }),
  checkParse('后天', '后天开会', { title: '开会', due_date: '2026-06-17' }),
  checkParse('大后天', '大后天 答辩', { title: '答辩', due_date: '2026-06-18' }),
  checkParse('N天后（阿拉伯数字）', '3天后 健身', { title: '健身', due_date: '2026-06-18' }),
  checkParse('N天后（中文数字）', '三天后 复查', { title: '复查', due_date: '2026-06-18' }),
  checkParse('今天', '今天 站会', { title: '站会', due_date: '2026-06-15' }),
  checkParse('周X（今天就是周 X 取下周）', '周一 例会', { title: '例会', due_date: '2026-06-22' }),
  checkParse('周X（本周未来某日）', '周三 例会', { title: '例会', due_date: '2026-06-17' }),
  checkParse('周X（本周已过取下周）', '周五 复盘', { title: '复盘', due_date: '2026-06-19' }),
  checkParse('星期X 写法', '星期六 爬山', { title: '爬山', due_date: '2026-06-20' }),
  checkParse('下周X（明确下周）', '下周五 交报告', { title: '交报告', due_date: '2026-06-26' }),
  checkParse('M月D日（今年未来）', '7月20日 生日', { title: '生日', due_date: '2026-07-20' }),
  checkParse('M月D号（今年已过取明年）', '1月5号 体检', { title: '体检', due_date: '2027-01-05' }),
  checkParse('下午3点（+12，默认今天）', '下午3点 开会', {
    title: '开会',
    due_date: '2026-06-15',
    due_time: '15:00',
  }),
  checkParse('HH:MM', '18:30 跑步', {
    title: '跑步',
    due_date: '2026-06-15',
    due_time: '18:30',
  }),
  checkParse('晚上8点（+12）', '晚上8点 给妈妈打电话', {
    title: '给妈妈打电话',
    due_date: '2026-06-15',
    due_time: '20:00',
  }),
  checkParse('上午N点', '上午9点 晨会', { title: '晨会', due_time: '09:00' }),
  checkParse('中午12点', '中午12点 吃饭', { title: '吃饭', due_time: '12:00' }),
  checkParse('点半', '晚上8点半 追剧', { title: '追剧', due_time: '20:30' }),
  checkParse('今晚（今天 + 20:00）', '今晚 看电影', {
    title: '看电影',
    due_date: '2026-06-15',
    due_time: '20:00',
  }),
  checkParse('裸 N 点无时段语境不猜', '3点 对齐一下', {
    title: '3点 对齐一下',
    due_date: null,
    due_time: null,
  }),
  checkParse('#标签（多个）', '写方案 #工作 #急', {
    title: '写方案',
    tags: ['工作', '急'],
  }),
  checkParse('!优先级', '修复登录 bug !高', { title: '修复登录 bug', priority: '高' }),
  checkParse('全角！优先级', '浇花 ！低', { title: '浇花', priority: '低' }),
  checkParse('组合输入', '下周五下午3点 交周报 !高 #工作', {
    title: '交周报',
    due_date: '2026-06-26',
    due_time: '15:00',
    priority: '高',
    tags: ['工作'],
  }),
  checkParse('组合输入（时间冒号写法）', '明天 18:30 开会 #团队', {
    title: '开会',
    due_date: '2026-06-16',
    due_time: '18:30',
    tags: ['团队'],
  }),
  checkParse('纯标题无解析', '买个西瓜', {
    title: '买个西瓜',
    due_date: null,
    due_time: null,
    priority: null,
    tags: [],
  }),
  checkParse('剥离后标题正确（语法紧贴标题）', '明天下午3点交周报', {
    title: '交周报',
    due_date: '2026-06-16',
    due_time: '15:00',
  }),
  checkParse('剥离后为空回退原标题', '!高', { title: '!高', priority: '高' }),
  checkParse('空输入', '', {
    title: '',
    due_date: null,
    due_time: null,
    priority: null,
    tags: [],
  }),
  {
    name: 'formatQuickHint 生成中文摘要',
    pass:
      JSON.stringify(
        formatQuickHint(parseQuickInput('明天下午3点 交报告 !高 #工作', NOW), NOW)
      ) === JSON.stringify(['明天', '15:00', '优先级 高', '#工作']),
  },
  {
    name: 'formatQuickHint 空结果返回 []',
    pass: JSON.stringify(formatQuickHint(parseQuickInput('随便写点啥', NOW), NOW)) === '[]',
  },
]

const failures = checks.filter((check) => !check.pass)

if (failures.length) {
  console.error('Quick parse regression check failed:')
  for (const failure of failures) console.error(`- ${failure.name}`)
  process.exit(1)
}

console.log(`Quick parse regression check passed (${checks.length} checks)`)
