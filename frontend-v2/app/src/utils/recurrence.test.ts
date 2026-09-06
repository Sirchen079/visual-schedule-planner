import { describe, expect, it } from 'vitest'
import { bydayLabel, categoryLabel, describeRrule, repeatRuleText, untilLabel } from './recurrence'

describe('describeRrule（RRULE 转为中文说明）', () => {
  it('空规则 → 不重复 · 单次日程', () => {
    expect(describeRrule(null)).toBe('不重复 · 单次日程')
    expect(describeRrule('')).toBe('不重复 · 单次日程')
    expect(describeRrule('  ')).toBe('不重复 · 单次日程')
  })

  it('每周一重复，包含结束日期', () => {
    expect(describeRrule('FREQ=WEEKLY;BYDAY=MO;UNTIL=20261108')).toBe('每周一，至 2026 年 11 月 8 日')
  })

  it('每隔一周的周五重复', () => {
    expect(describeRrule('FREQ=WEEKLY;INTERVAL=2;BYDAY=FR;UNTIL=20261011')).toBe(
      '隔周的周五（单双周轮换），至 2026 年 10 月 11 日',
    )
  })

  it('一周多天、多周间隔、无 BYDAY', () => {
    expect(describeRrule('FREQ=WEEKLY;BYDAY=MO,WE;UNTIL=20261206')).toBe('每周一、周三，至 2026 年 12 月 6 日')
    expect(describeRrule('FREQ=WEEKLY;INTERVAL=3;BYDAY=SA')).toBe('每 3 周的周六')
    expect(describeRrule('FREQ=WEEKLY')).toBe('每周')
    expect(describeRrule('FREQ=WEEKLY;INTERVAL=2')).toBe('隔周的一周（单双周轮换）')
  })

  it('按次数重复 / 其他频率', () => {
    expect(describeRrule('FREQ=DAILY;COUNT=5')).toBe('每天，共 5 次')
    expect(describeRrule('FREQ=DAILY;INTERVAL=2;COUNT=10')).toBe('每 2 天，共 10 次')
    expect(describeRrule('FREQ=MONTHLY')).toBe('每月同日')
    expect(describeRrule('FREQ=YEARLY')).toBe('每年同日')
  })

  it('带月内序数的 BYDAY（如 2MO / -1FR）剥掉前缀', () => {
    expect(describeRrule('FREQ=MONTHLY;BYDAY=2MO;COUNT=4')).toBe('每月同日，共 4 次')
    expect(bydayLabel('2MO,-1FR')).toBe('周一、周五')
  })

  it('无法识别的规则原样返回（不编造语义）', () => {
    expect(describeRrule('FREQ=SECONDLY;INTERVAL=30')).toBe('FREQ=SECONDLY;INTERVAL=30')
    expect(describeRrule('NOT-A-RULE')).toBe('NOT-A-RULE')
  })

  it('UNTIL 解析：非法值安全跳过', () => {
    expect(untilLabel('20261108')).toBe('2026 年 11 月 8 日')
    expect(untilLabel('20261399')).toBeNull()
    expect(untilLabel(undefined)).toBeNull()
  })
})

describe('categoryLabel（类别 → 中文，未知原样）', () => {
  it('已知类别映射，未知/空安全回退', () => {
    expect(categoryLabel('course')).toBe('课程')
    expect(categoryLabel('general')).toBe('通用')
    expect(categoryLabel('meeting')).toBe('meeting')
    expect(categoryLabel(null)).toBe('—')
    expect(categoryLabel('')).toBe('—')
  })
})

describe('repeatRuleText（repeat_note 优先，describeRrule 回退）', () => {
  it('repeat_note 非空 → 原样采用（后端教学周次权威，如「每周（第2-13周）」）', () => {
    expect(repeatRuleText('每周（第2-13周）', 'FREQ=WEEKLY;BYDAY=MO')).toBe('每周（第2-13周）')
    expect(repeatRuleText('双周课（第6-12周）', null)).toBe('双周课（第6-12周）')
    expect(repeatRuleText('  双周课（第6-12周）  ', 'FREQ=WEEKLY')).toBe('双周课（第6-12周）') // 去首尾空白
  })

  it('缺失/空白 → 回退手写 describeRrule', () => {
    expect(repeatRuleText(null, 'FREQ=WEEKLY;BYDAY=TU;UNTIL=20261206')).toBe('每周二，至 2026 年 12 月 6 日')
    expect(repeatRuleText(undefined, 'FREQ=WEEKLY;INTERVAL=2;BYDAY=FR')).toBe('隔周的周五（单双周轮换）')
    expect(repeatRuleText('', null)).toBe('不重复 · 单次日程')
    expect(repeatRuleText('   ', 'FREQ=DAILY')).toBe('每天')
    expect(repeatRuleText(null, null)).toBe('不重复 · 单次日程')
  })
})
