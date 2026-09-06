import { afterEach, describe, expect, it, vi } from 'vitest'
import { createEntry, deleteEntry, listLedger, monthRange, restoreEntry, type LedgerEntry } from './ledger'

afterEach(() => vi.unstubAllGlobals())
describe('ledger API', () => {
  it('month boundaries include leap day and year end', () => {
    expect(monthRange('2024-02')).toEqual({start:'2024-02-01',end:'2024-02-29'})
    expect(monthRange('2026-12').end).toBe('2026-12-31')
    expect(() => monthRange('2026-13')).toThrow()
  })
  it('preserves decimal strings and retry key; version accompanies delete/restore', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({id:1}), {status:200}))
    vi.stubGlobal('fetch', fetch)
    await createEntry({day:'2026-09-05',direction:'expense',amount:'0.10',idempotency_key:'retry-1'})
    const body = JSON.parse(fetch.mock.calls[0]![1].body)
    expect(body.amount).toBe('0.10'); expect(body.idempotency_key).toBe('retry-1')
    fetch.mockImplementation(async () => new Response('{}', {status:200}))
    await deleteEntry({id:1,version:3} as LedgerEntry)
    expect(fetch.mock.calls[1]![0]).toBe('/api/ledger/1?version=3')
    await restoreEntry({id:1,version:4} as LedgerEntry)
    expect(JSON.parse(fetch.mock.calls[2]![1].body)).toEqual({version:4})
  })
  it('search, account and trash filters are encoded', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{}', {status:200}))
    vi.stubGlobal('fetch',fetch)
    await listLedger({start:'2026-09-01',end:'2026-09-30',account:'现金',query:'10%',deleted:true})
    const url = new URL(fetch.mock.calls[0]![0], 'http://localhost')
    expect(url.searchParams.get('account')).toBe('现金')
    expect(url.searchParams.get('query')).toBe('10%')
    expect(url.searchParams.get('deleted')).toBe('true')
  })
})
