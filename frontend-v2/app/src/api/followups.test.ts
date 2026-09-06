import { describe, expect, it } from 'vitest'
import { followupTarget } from './followups'

describe('followup notification navigation', () => {
  it('accepts only the internal project and followup route', () => {
    expect(followupTarget('/research?project=12&followup=34')).toBe('/research?project=12&followup=34')
    for (const value of [null, undefined, '', 'https://example.org', '//example.org', 'javascript:alert(1)', '/research?project=0&followup=2', '/research?project=1&followup=2#extra', '/research?project=1&followup=2&next=https://example.org']) {
      expect(followupTarget(value)).toBeUndefined()
    }
  })
})
