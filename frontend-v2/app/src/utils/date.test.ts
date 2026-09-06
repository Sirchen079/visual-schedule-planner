import { describe, expect, it } from 'vitest'
import {
  addDays,
  addMonths,
  blockPercent,
  cnNumber,
  firstOfMonth,
  hmToMinutes,
  hourLines,
  isoWeekNumber,
  minutesToHm,
  mondayOf,
  monthGrid,
  monthGridBounds,
  nowPercent,
  parseIsoDate,
  toIsoDate,
  weekDates,
} from './date'

describe('date utils', () => {
  it('toIsoDate / parseIsoDate 本地时区往返', () => {
    const d = new Date(2026, 8, 7, 10, 0) // 2026-09-07 本地
    const iso = toIsoDate(d)
    expect(iso).toBe('2026-09-07')
    const back = parseIsoDate(iso)
    expect(back.getFullYear()).toBe(2026)
    expect(back.getMonth()).toBe(8)
    expect(back.getDate()).toBe(7)
  })

  it('mondayOf：周一不变，周日退回', () => {
    expect(mondayOf('2026-09-07')).toBe('2026-09-07') // 周一
    expect(mondayOf('2026-09-09')).toBe('2026-09-07') // 周三
    expect(mondayOf('2026-09-13')).toBe('2026-09-07') // 周日
    expect(mondayOf('2026-09-04')).toBe('2026-08-31') // 周五
  })

  it('addDays / weekDates', () => {
    expect(addDays('2026-08-31', 7)).toBe('2026-09-07')
    expect(addDays('2026-09-01', -1)).toBe('2026-08-31')
    expect(weekDates('2026-09-07')).toEqual([
      '2026-09-07',
      '2026-09-08',
      '2026-09-09',
      '2026-09-10',
      '2026-09-11',
      '2026-09-12',
      '2026-09-13',
    ])
  })

  it('isoWeekNumber：开学第一周是第 37 周（与基准稿一致）', () => {
    expect(isoWeekNumber('2026-09-07')).toBe(37)
    expect(isoWeekNumber('2026-09-13')).toBe(37)
    expect(isoWeekNumber('2026-09-04')).toBe(36)
    expect(isoWeekNumber('2026-01-01')).toBe(1) // 2026-01-01 是周四
  })

  it('hmToMinutes / minutesToHm', () => {
    expect(hmToMinutes('08:55')).toBe(535)
    expect(hmToMinutes('0:00')).toBe(0)
    expect(hmToMinutes('25:00')).toBeNull()
    expect(hmToMinutes('0855')).toBeNull()
    expect(minutesToHm(535)).toBe('08:55')
    expect(minutesToHm(0)).toBe('00:00')
  })

  it('blockPercent：按时间轴范围换算位置与高度', () => {
    // 基准稿：08:55-10:45 → top 7.051% / height 14.103%
    const a = blockPercent('08:55', '10:45')!
    expect(a.top).toBeCloseTo(7.051, 2)
    expect(a.height).toBeCloseTo(14.103, 2)
    expect(a.clamped).toBe(false)
    // 基准稿：16:00-17:40 → top 61.538% / height 12.821%
    const b = blockPercent('16:00', '17:40')!
    expect(b.top).toBeCloseTo(61.538, 2)
    expect(b.height).toBeCloseTo(12.821, 2)
    // 基准稿：14:00-15:40 → top 46.154%
    const c = blockPercent('14:00', '15:40')!
    expect(c.top).toBeCloseTo(46.154, 2)
  })

  it('blockPercent：跨轴边界裁剪、非法输入', () => {
    expect(blockPercent('07:00', '08:30')).toMatchObject({ top: 0, clamped: true })
    expect(blockPercent('20:00', '22:00')!.height).toBeCloseTo(60 / 780 * 100, 3)
    expect(blockPercent('10:00', '10:00')).toBeNull()
    expect(blockPercent('10:00', '09:00')).toBeNull()
    expect(blockPercent('abc', '10:00')).toBeNull()
  })

  it('hourLines：08:00 到 21:00 共 14 条刻线，首尾为 0%/100%', () => {
    const lines = hourLines()
    expect(lines).toHaveLength(14)
    expect(lines[0]).toMatchObject({ hm: '08:00', pct: 0 })
    expect(lines[lines.length - 1]).toMatchObject({ hm: '21:00', pct: 100 })
    expect(lines[1].pct).toBeCloseTo(100 / 13, 6)
  })

  it('nowPercent：轴内返回百分比，轴外返回 null', () => {
    expect(nowPercent(new Date(2026, 8, 7, 8, 0))).toBe(0)
    expect(nowPercent(new Date(2026, 8, 7, 14, 30))).toBeCloseTo((390 / 780) * 100, 6)
    expect(nowPercent(new Date(2026, 8, 7, 7, 59))).toBeNull()
    expect(nowPercent(new Date(2026, 8, 7, 21, 1))).toBeNull()
  })

  it('cnNumber：刊头中文数字', () => {
    expect(cnNumber(0)).toBe('零')
    expect(cnNumber(5)).toBe('五')
    expect(cnNumber(7)).toBe('七')
    expect(cnNumber(12)).toBe('十二')
    expect(cnNumber(20)).toBe('二十')
    expect(cnNumber(99)).toBe('99')
  })
})

describe('月历网格（月视图）', () => {
  it('firstOfMonth / addMonths：跨年与负向平移都落在 1 号', () => {
    expect(firstOfMonth('2026-09-04')).toBe('2026-09-01')
    expect(addMonths('2026-09-15', -1)).toBe('2026-08-01')
    expect(addMonths('2026-09-15', 1)).toBe('2026-10-01')
    expect(addMonths('2026-12-31', 1)).toBe('2027-01-01')
    expect(addMonths('2026-01-20', -1)).toBe('2025-12-01')
    expect(addMonths('2026-10-05', -14)).toBe('2025-08-01')
  })

  it('monthGrid：6×7 恒定网格，周首 = 周一，覆盖整月并前后溢出', () => {
    const grid = monthGrid('2026-09-15')
    expect(grid).toHaveLength(6)
    for (const week of grid) expect(week).toHaveLength(7)
    // 2026-09-01 是周二 → 首格为 08-31（周一）
    expect(grid[0][0]).toBe('2026-08-31')
    expect(grid[0][1]).toBe('2026-09-01')
    // 末格 = 首格 + 41 天
    expect(grid[5][6]).toBe('2026-10-11')
    // 全月 30 天都在网格内
    const flat = grid.flat()
    for (let d = 1; d <= 30; d++) {
      expect(flat).toContain(`2026-09-${String(d).padStart(2, '0')}`)
    }
    // 每列首行都是周一
    for (const week of grid) {
      expect(parseIsoDate(week[0]).getDay()).toBe(1)
    }
  })

  it('monthGridBounds：2026-09 网格取数区间 = 08-31 至 10-11', () => {
    expect(monthGridBounds('2026-09-04')).toEqual({ start: '2026-08-31', end: '2026-10-11' })
    // 2026-02（平年、2/1 是周日 → 首格周一 01-26）
    expect(monthGridBounds('2026-02-10')).toEqual({ start: '2026-01-26', end: '2026-03-08' })
  })
})
