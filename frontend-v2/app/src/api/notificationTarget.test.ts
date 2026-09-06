import { describe, expect, it } from 'vitest'
import { notificationTarget } from './notificationTarget'

describe('notification targets', () => {
  it('supports task reminders, legacy task ids and research followups', () => {
    expect(notificationTarget('/board?task=12')).toBe('/board?task=12')
    expect(notificationTarget('', 12)).toBe('/board?task=12')
    expect(notificationTarget('/research?project=1&followup=2')).toBe('/research?project=1&followup=2')
  })
  it('rejects external URLs, malformed ids and extra route parameters', () => {
    for (const value of ['//evil.test', 'https://evil.test', '/board?task=0', '/board?task=-2', '/board?task=2&next=x', '/board?task=2#extra']) {
      expect(notificationTarget(value, 1)).toBeUndefined()
    }
    expect(notificationTarget('', -1)).toBeUndefined()
  })
})

it('opens research material updates and rejects invalid project targets', () => {
  expect(notificationTarget('/research?project=12')).toBe('/research?project=12')
  for (const value of ['/research?project=0', '/research?project=2&next=x', '/research?project=2\n', '/research?project=999999999999999999']) {
    expect(notificationTarget(value)).toBeUndefined()
  }
})

it('opens a bill notification and rejects malformed destinations', () => {
  expect(notificationTarget('/ledger?bill=12')).toBe('/ledger?bill=12')
  for (const value of ['/ledger?bill=0', '/ledger?bill=2&next=x', '/ledger?bill=2\n', '/ledger?bill=999999999999999999']) {
    expect(notificationTarget(value)).toBeUndefined()
  }
})
