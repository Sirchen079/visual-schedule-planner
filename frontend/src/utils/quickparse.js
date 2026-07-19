// 自然语言快速创建解析：从「明天下午3点 交周报 !高 #工作」这类输入中
// 提取结构化字段（标题 / 截止日期 / 截止时间 / 优先级 / 标签）。
// 纯函数、不依赖 Vue；now 可注入以便测试。

const CN_NUM = { 零: 0, 一: 1, 二: 2, 两: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9, 十: 10 }
const WEEKDAYS = { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 日: 7, 天: 7 }
const RELATIVE_DAYS = { 今天: 0, 今日: 0, 明天: 1, 后天: 2, 大后天: 3 }
// 数字片段：阿拉伯数字、十/十一/十二、单字中文数字
const NUM = '[0-9]+|十[一二]?|[零一二两三四五六七八九十]'

// 时段词 → 24 小时制换算（入参保证 1-12）
const PERIOD_HOURS = {
  上午: (n) => n % 12,
  早上: (n) => n % 12,
  中午: (n) => (n === 12 ? 12 : n <= 3 ? n + 12 : n),
  下午: (n) => (n === 12 ? 12 : n + 12),
  晚上: (n) => (n === 12 ? 0 : n + 12),
  晚间: (n) => (n === 12 ? 0 : n + 12),
  今晚: (n) => (n === 12 ? 0 : n + 12),
}
const PERIODS = Object.keys(PERIOD_HOURS).join('|')

function toNum(text) {
  if (/^\d+$/.test(text)) return parseInt(text, 10)
  if (text in CN_NUM) return CN_NUM[text]
  if (text.length === 2 && text[0] === '十' && text[1] in CN_NUM) return 10 + CN_NUM[text[1]]
  return NaN
}

function pad(n) {
  return `${n}`.padStart(2, '0')
}

function toISODate(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function parseISODate(value) {
  const [y, m, d] = String(value).split('-').map(Number)
  return new Date(y, (m || 1) - 1, d || 1)
}

function addDays(base, n) {
  const d = new Date(base.getFullYear(), base.getMonth(), base.getDate())
  d.setDate(d.getDate() + n)
  return d
}

// 周X → 最近的未来该日（今天就是周 X 时取下周）；forceNextWeek 对应「下周X」
function resolveWeekday(today, target, forceNextWeek) {
  const w = today.getDay() === 0 ? 7 : today.getDay()
  const delta = forceNextWeek ? 7 - w + target : target > w ? target - w : target - w + 7
  return addDays(today, delta)
}

export function parseQuickInput(text, now = new Date()) {
  const original = (text || '').trim()
  const parsed = { title: original, due_date: null, due_time: null, priority: null, tags: [] }
  if (!original) return parsed

  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  let rest = original

  // take：用正则首个命中片段设置字段并把它从标题中剥离；
  // handler 返回 false 表示片段无效、不消费（保留在标题里）。
  function take(re, handler) {
    let ok = false
    rest = rest.replace(re, (match, ...groups) => {
      if (!handler(...groups)) return match
      ok = true
      return ' '
    })
    return ok
  }

  // 优先级：!高 / !中 / !低（兼容全角！），多处出现时取第一个
  rest = rest.replace(/[!！](高|中|低)/g, (match, p) => {
    if (!parsed.priority) parsed.priority = p
    return ' '
  })

  // 标签：#标签（可多个，标签名不含空格）
  rest = rest.replace(/#([^\s#]+)/g, (match, tag) => {
    parsed.tags.push(tag)
    return ' '
  })

  // 时间：HH:MM（兼容全角冒号与时段词前缀，如 下午3:30 → 15:30）
  take(new RegExp(`(${PERIODS})?(\\d{1,2})\\s*[：:]\\s*([0-5]\\d)`), (period, hText, mText) => {
    if (parsed.due_time) return false
    let h = parseInt(hText, 10)
    if (period) {
      if (!(h >= 1 && h <= 12)) return false
      h = PERIOD_HOURS[period](h)
    } else if (h > 23) {
      return false
    }
    parsed.due_time = `${pad(h)}:${mText}`
    return true
  })

  // 时间：上午/早上/中午/下午/晚上/晚间/今晚 N点（可带 半 / N分）；
  // 裸「3点」「15点」无时段语境时不猜，保持原样
  take(new RegExp(`(${PERIODS})(${NUM})点(半|(\\d{1,2})分?)?`), (period, nText, half, mText) => {
    if (parsed.due_time) return false
    const n = toNum(nText)
    if (!(n >= 1 && n <= 12)) return false
    const minute = half === '半' ? 30 : mText ? parseInt(mText, 10) : 0
    if (minute > 59) return false
    parsed.due_time = `${pad(PERIOD_HOURS[period](n))}:${pad(minute)}`
    return true
  })

  // 日期：下周X / 下星期X / 下礼拜X（明确下周）
  take(new RegExp(`下(?:周|星期|礼拜)([一二三四五六日天])`), (w) => {
    if (parsed.due_date) return false
    parsed.due_date = toISODate(resolveWeekday(today, WEEKDAYS[w], true))
    return true
  })

  // 日期：周X / 星期X / 礼拜X（最近的未来该日，今天是周 X 则取下周）
  take(new RegExp(`(?:周|星期|礼拜)([一二三四五六日天])`), (w) => {
    if (parsed.due_date) return false
    parsed.due_date = toISODate(resolveWeekday(today, WEEKDAYS[w], false))
    return true
  })

  // 日期：M月D日 / M月D号（今年，已过则明年）
  take(/(\d{1,2})月(\d{1,2})[日号]/, (mText, dText) => {
    if (parsed.due_date) return false
    const month = parseInt(mText, 10)
    const day = parseInt(dText, 10)
    if (!(month >= 1 && month <= 12 && day >= 1 && day <= 31)) return false
    let candidate = new Date(today.getFullYear(), month - 1, day)
    if (candidate.getMonth() !== month - 1) return false // 2月30日之类
    if (candidate < today) candidate = new Date(today.getFullYear() + 1, month - 1, day)
    parsed.due_date = toISODate(candidate)
    return true
  })

  // 日期：今天/今日/明天/后天/大后天
  take(/(大后天|后天|明天|今天|今日)/, (word) => {
    if (parsed.due_date) return false
    parsed.due_date = toISODate(addDays(today, RELATIVE_DAYS[word]))
    return true
  })

  // 日期：N天后（如 3天后、三天后）
  take(new RegExp(`(${NUM})天后`), (nText) => {
    if (parsed.due_date) return false
    const n = toNum(nText)
    if (!(n >= 1)) return false
    parsed.due_date = toISODate(addDays(today, n))
    return true
  })

  // 今晚：今天 + 默认 20:00（已有时间时不覆盖）
  take(/今晚/, () => {
    if (!parsed.due_date) parsed.due_date = toISODate(today)
    if (!parsed.due_time) parsed.due_time = '20:00'
    return true
  })

  // 只给了时间没给日期（如「晚上8点」「18:30」）：默认落在今天
  if (parsed.due_time && !parsed.due_date) parsed.due_date = toISODate(today)

  const title = rest.replace(/\s+/g, ' ').trim()
  parsed.title = title || original
  return parsed
}

// 解析结果 → 中文摘要 chips（供快速新建输入时的实时提示）
export function formatQuickHint(parsed, now = new Date()) {
  if (!parsed) return []
  const hints = []
  if (parsed.due_date) {
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const target = parseISODate(parsed.due_date)
    const diffDays = Math.round((target - today) / 86_400_000)
    if (diffDays === 0) hints.push('今天')
    else if (diffDays === 1) hints.push('明天')
    else if (diffDays === 2) hints.push('后天')
    else if (diffDays === 3) hints.push('大后天')
    else if (target.getFullYear() === today.getFullYear()) {
      hints.push(`${target.getMonth() + 1}月${target.getDate()}日`)
    } else {
      hints.push(`${target.getFullYear()}年${target.getMonth() + 1}月${target.getDate()}日`)
    }
  }
  if (parsed.due_time) hints.push(parsed.due_time)
  if (parsed.priority) hints.push(`优先级 ${parsed.priority}`)
  for (const tag of parsed.tags || []) hints.push(`#${tag}`)
  return hints
}
