import type { components } from './contracts/rest'
import { http, request } from './http'

type Schemas = components['schemas']
export type LedgerEntry = Schemas['EntryRead']
export type LedgerInput = Schemas['EntryCreate']
export type LedgerPage = Schemas['EntryPage']
export type LedgerSummary = Schemas['LedgerSummary']
export type LedgerCurrency = LedgerEntry['currency']

export const currencies: LedgerCurrency[] = ['CNY', 'USD', 'EUR', 'GBP', 'HKD', 'JPY']
export function monthRange(month: string): { start: string; end: string } {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month)) throw new Error('请选择有效月份')
  const [year, m] = month.split('-').map(Number) as [number, number]
  const last = new Date(year, m, 0).getDate()
  return { start: `${month}-01`, end: `${month}-${last}` }
}
export function listLedger(query: { start: string; end: string; currency?: LedgerCurrency;
  account?: string; query?: string; deleted?: boolean; offset?: number }): Promise<LedgerPage> {
  return http.get('/api/ledger', { ...query, limit: 50 })
}
export function ledgerSummary(query: { start: string; end: string; currency?: LedgerCurrency;
  account?: string }): Promise<LedgerSummary> {
  return http.get('/api/ledger/summary', query)
}
export const readEntry = (id: number): Promise<LedgerEntry> => http.get(`/api/ledger/${id}`)
export const createEntry = (input: LedgerInput): Promise<LedgerEntry> => http.post('/api/ledger', input)
export const replaceEntry = (id: number, input: Schemas['EntryReplace']): Promise<LedgerEntry> => http.put(`/api/ledger/${id}`, input)
export const deleteEntry = (entry: LedgerEntry): Promise<LedgerEntry> => request(`/api/ledger/${entry.id}`, { method: 'DELETE', query: { version: entry.version } })
export const restoreEntry = (entry: LedgerEntry): Promise<LedgerEntry> => http.post(`/api/ledger/${entry.id}/restore`, { version: entry.version })
