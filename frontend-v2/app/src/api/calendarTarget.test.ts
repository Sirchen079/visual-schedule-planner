import { describe, expect, it } from 'vitest'
import { notificationTarget } from './notificationTarget'
import { parseCalendarTarget } from './calendarTarget'

describe('calendar occurrence notification links', () => {
  it('preserves the occurrence date and id, including leap day', () => {
    expect(parseCalendarTarget('/calendar?date=2028-02-29&event=12')).toEqual({ date: '2028-02-29', eventId: 12 })
    expect(notificationTarget('/calendar?date=2026-09-06&event=7')).toBe('/calendar?date=2026-09-06&event=7')
  })
  it.each(['2026-02-29', '2026-04-31', '2026-13-01', '2026-00-01', '0000-01-01'])('rejects an invalid date %s', date => {
    expect(notificationTarget(`/calendar?date=${date}&event=1`)).toBeUndefined()
  })
  it.each(['0', '-1', '1e3', '9007199254740992', '2&next=https://example.com', '2#extra'])('rejects invalid ids or route extensions %s', id => {
    expect(notificationTarget(`/calendar?date=2026-09-06&event=${id}`)).toBeUndefined()
  })
})
