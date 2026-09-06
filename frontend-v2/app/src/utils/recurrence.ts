/**
 * 事件元信息的人类可读标注（纯函数，无 Vue 依赖）。
 *
 * RRULE 语义以后端实测为准（E:\知时\data 真实课表 + backend weeks.py）：
 * - 每周课：FREQ=WEEKLY;BYDAY=MO;UNTIL=20261108
 * - 单双周课（week_kind odd/even 生成）：FREQ=WEEKLY;INTERVAL=2;BYDAY=FR;UNTIL=20261011
 *
 * 已知契约缺口（如实记录，不前端模拟）：「单周/双周」的学期周次奇偶需要 semester_start
 * （第 1 教学周周一），后端导入后并未持久化暴露，前端无法把 INTERVAL=2 折算成
 * 「单周/双周」，只能如实描述为「隔周（单双周轮换）」并给出首末落点。
 */

const BYDAY_CN: Record<string, string> = {
  MO: '一',
  TU: '二',
  WE: '三',
  TH: '四',
  FR: '五',
  SA: '六',
  SU: '日',
}

/** BYDAY 列表 → 「周一」「周一、周三」；剥掉月内序数前缀（如 2MO / -1SU）。 */
export function bydayLabel(byday: string | undefined): string {
  if (!byday) return ''
  const parts = byday
    .split(',')
    .map((raw) => {
      const key = raw.trim().replace(/^[+-]?\d+/, '').toUpperCase()
      return BYDAY_CN[key] ? `周${BYDAY_CN[key]}` : ''
    })
    .filter(Boolean)
  return parts.join('、')
}

/** UNTIL=YYYYMMDD → 「2026 年 11 月 8 日」；解析失败返回 null。 */
export function untilLabel(until: string | undefined): string | null {
  const m = /^(\d{4})(\d{2})(\d{2})/.exec((until ?? '').trim())
  if (!m) return null
  const [, y, mo, d] = m
  const month = Number(mo)
  const day = Number(d)
  if (month < 1 || month > 12 || day < 1 || day > 31) return null
  return `${y} 年 ${month} 月 ${day} 日`
}

/**
 * RRULE → 人类可读重复规则描述。
 * - null/空 → 「不重复 · 单次日程」
 * - FREQ=WEEKLY INTERVAL=2 → 「隔周的周五（单双周轮换）」
 * - FREQ=WEEKLY（默认每周一次）→ 「每周一」「每周一、周三」
 * - UNTIL/COUNT 以「，」衔接在句尾；无法识别的规则原样返回（不美化、不编造）。
 */
export function describeRrule(rrule: string | null | undefined): string {
  if (!rrule || !rrule.trim()) return '不重复 · 单次日程'
  const map: Record<string, string> = {}
  for (const part of rrule.split(';')) {
    const i = part.indexOf('=')
    if (i > 0) map[part.slice(0, i).trim().toUpperCase()] = part.slice(i + 1).trim()
  }
  const freq = (map['FREQ'] ?? '').toUpperCase()
  const interval = map['INTERVAL'] ? Number(map['INTERVAL']) : 1
  const days = bydayLabel(map['BYDAY'])

  let head: string
  switch (freq) {
    case 'WEEKLY':
      if (interval === 2) head = `隔周的${days || '一周'}（单双周轮换）`
      else if (interval > 2) head = `每 ${interval} 周的${days || '一周'}`
      else head = days ? `每${days}` : '每周'
      break
    case 'DAILY':
      head = interval > 1 ? `每 ${interval} 天` : '每天'
      break
    case 'MONTHLY':
      head = '每月同日'
      break
    case 'YEARLY':
      head = '每年同日'
      break
    default:
      return rrule.trim() // 未知 FREQ：原样展示，不编造语义
  }

  const tails: string[] = []
  const until = untilLabel(map['UNTIL'])
  if (until) tails.push(`至 ${until}`)
  const count = map['COUNT'] ? Number(map['COUNT']) : null
  if (count !== null && Number.isFinite(count)) tails.push(`共 ${count} 次`)
  return tails.length ? `${head}，${tails.join('，')}` : head
}

/** 类别 → 中文标签；未知类别原样返回。 */
export function categoryLabel(category: string | null | undefined): string {
  if (!category) return '—'
  const map: Record<string, string> = { course: '课程', general: '通用' }
  return map[category] ?? category
}

/**
 * 重复规则文案（M3.5，re #020 事项2）：优先后端透出的人类可读 repeat_note
 * （expand/day 契约新增字段，课表导入按学期周次生成，如「每周（第2-13周）/
 * 双周课（第6-12周）」——前端无法从 RRULE 折算教学周次，见 describeRrule 的
 * 契约缺口记录）；缺失/空白时回退手写 describeRrule(rrule)。纯函数便于单测。
 */
export function repeatRuleText(
  repeatNote: string | null | undefined,
  rrule: string | null | undefined,
): string {
  const note = repeatNote?.trim()
  if (note) return note
  return describeRrule(rrule)
}
