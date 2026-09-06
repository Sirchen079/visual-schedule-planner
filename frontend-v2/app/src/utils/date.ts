/**
 * 本地日期及日历时间轴工具。使用本地年月日计算，避免 UTC 转换造成日期偏移。
 */

/** 一天的时间轴范围（分钟）：08:00 起到 21:00 止。 */
export const AXIS_START_MIN = 8 * 60
export const AXIS_END_MIN = 21 * 60
export const AXIS_MINUTES = AXIS_END_MIN - AXIS_START_MIN // 780

export function toIsoDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export function parseIsoDate(iso: string): Date {
  // new Date('2026-09-07') 在部分实现里按 UTC 解析，这里手动拆，保证本地时区语义
  const [y, m, d] = iso.split('-').map((x) => Number(x))
  return new Date(y, (m ?? 1) - 1, d ?? 1)
}

export function addDays(iso: string, days: number): string {
  const d = parseIsoDate(iso)
  d.setDate(d.getDate() + days)
  return toIsoDate(d)
}

/** 所在周的周一（ISO 语义：周一为一周之首）。 */
export function mondayOf(iso: string): string {
  const d = parseIsoDate(iso)
  const wd = d.getDay() === 0 ? 7 : d.getDay() // 周日 → 7
  return addDays(iso, 1 - wd)
}

/** 从周一 ISO 日期起连续 7 天（含周六周日）。 */
export function weekDates(mondayIso: string): string[] {
  return Array.from({ length: 7 }, (_, i) => addDays(mondayIso, i))
}

/** 所在月份的 1 号（ISO）。 */
export function firstOfMonth(iso: string): string {
  return `${iso.slice(0, 4)}-${iso.slice(5, 7)}-01`
}

/** 平移 n 个月并落回 1 号（月历导航用；n 可为负）。 */
export function addMonths(iso: string, n: number): string {
  const y = Number(iso.slice(0, 4))
  const m = Number(iso.slice(5, 7))
  const total = y * 12 + (m - 1) + n
  const ny = Math.floor(total / 12)
  const nm = (((total % 12) + 12) % 12) + 1
  return `${ny}-${String(nm).padStart(2, '0')}-01`
}

/** 月历网格恒为 6 周 × 7 天（周首 = 周一，与周视图一致），高度稳定不跳动。 */
export const GRID_WEEKS = 6

/**
 * 月历网格：以 iso 所在月为准，返回 6×7 的 ISO 日期阵（首格 = 1 号所在周的周一，
 * 末格固定首格 + 41 天），前后溢出日供月历灰显。
 */
export function monthGrid(iso: string): string[][] {
  const start = mondayOf(firstOfMonth(iso))
  return Array.from({ length: GRID_WEEKS }, (_, w) =>
    Array.from({ length: 7 }, (_, d) => addDays(start, w * 7 + d)),
  )
}

/** 网格首/末日期（月视图一次 expand 取数的区间）。 */
export function monthGridBounds(iso: string): { start: string; end: string } {
  const grid = monthGrid(iso)
  return { start: grid[0][0], end: grid[GRID_WEEKS - 1][6] }
}

/** ISO 周数（与基准稿 dateline「第 37 周」一致）。 */
export function isoWeekNumber(iso: string): number {
  const d = parseIsoDate(iso)
  const target = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  // ISO 周：周四所在周为第一周 —— 挪到本周周四再数
  target.setDate(target.getDate() + 4 - (target.getDay() === 0 ? 7 : target.getDay()))
  const yearStart = new Date(target.getFullYear(), 0, 1)
  return Math.ceil(((target.getTime() - yearStart.getTime()) / 86400000 + 1) / 7)
}

/** 'HH:MM' → 当日分钟数；非法输入返回 null。 */
export function hmToMinutes(hm: string): number | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(hm.trim())
  if (!m) return null
  const h = Number(m[1])
  const min = Number(m[2])
  if (h > 24 || min > 59) return null
  return h * 60 + min
}

export function minutesToHm(min: number): string {
  const m = ((min % 1440) + 1440) % 1440
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
}

/** 小时刻线（含 08:00 与 21:00）在轴上的百分比位置。 */
export function hourLines(): Array<{ hm: string; pct: number }> {
  const lines: Array<{ hm: string; pct: number }> = []
  for (let min = AXIS_START_MIN; min <= AXIS_END_MIN; min += 60) {
    lines.push({ hm: minutesToHm(min), pct: ((min - AXIS_START_MIN) / AXIS_MINUTES) * 100 })
  }
  return lines
}

export interface BlockPercent {
  top: number
  height: number
  /** 起止超出时间轴（被裁剪）时为 true，调用方可给降级提示 */
  clamped: boolean
}

/**
 * 事件块定位（百分比，恰好复现基准稿数值）：
 * 08:55–10:45 → top 7.051% / height 14.103%；16:00–17:40 → top 61.538% / height 12.821%。
 * 起止裁剪到轴内；高度不足时给最小可见高度（≈ 半小时刻线的 1/3）。
 */
export function blockPercent(startHm: string, endHm: string): BlockPercent | null {
  const s = hmToMinutes(startHm)
  const e = hmToMinutes(endHm)
  if (s === null || e === null || e <= s) return null
  const clamped = s < AXIS_START_MIN || e > AXIS_END_MIN
  const cs = Math.min(Math.max(s, AXIS_START_MIN), AXIS_END_MIN)
  const ce = Math.min(Math.max(e, AXIS_START_MIN), AXIS_END_MIN)
  const top = ((cs - AXIS_START_MIN) / AXIS_MINUTES) * 100
  const height = ((ce - cs) / AXIS_MINUTES) * 100
  return { top, height: Math.max(height, 100 / AXIS_MINUTES / 3), clamped }
}

/** 现在时刻在轴上的百分比；超出轴（凌晨/深夜）返回 null。 */
export function nowPercent(date: Date): number | null {
  const min = date.getHours() * 60 + date.getMinutes() + date.getSeconds() / 60
  if (min < AXIS_START_MIN || min > AXIS_END_MIN) return null
  return ((min - AXIS_START_MIN) / AXIS_MINUTES) * 100
}

const CN_DIGITS = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十']

/** 0–20 → 中文小写数字（刊头排版用，超出范围回退阿拉伯数字）。 */
export function cnNumber(n: number): string {
  if (!Number.isInteger(n) || n < 0 || n > 20) return String(n)
  if (n <= 10) return CN_DIGITS[n]
  if (n < 20) return `十${CN_DIGITS[n - 10]}`
  return '二十'
}
