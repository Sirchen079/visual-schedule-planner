import type { components } from './contracts/rest'
import { http } from './http'

type Schemas = components['schemas']
export type InboxItem = Schemas['InboxRead']
export type InboxProposal = Schemas['Revision']['proposal']
export type InboxStatus = InboxItem['status']
export const listInbox = (status: InboxStatus, offset = 0): Promise<Schemas['InboxPage']> =>
  http.get('/api/inbox', { status, offset, limit: 30 })
export const readInbox = (id: number): Promise<InboxItem> => http.get(`/api/inbox/${id}`)
export const captureInbox = (body: Schemas['CaptureBatch']): Promise<InboxItem[]> => http.post('/api/inbox', body)
export const reviseInbox = (id: number, body: Schemas['Revision']): Promise<InboxItem> => http.put(`/api/inbox/${id}`, body)
export const applyInbox = (row: InboxItem): Promise<InboxItem> => http.post(`/api/inbox/${row.id}/apply`, { version: row.version })
export const rejectInbox = (row: InboxItem): Promise<InboxItem> => http.post(`/api/inbox/${row.id}/reject`, { version: row.version })

export function describeProposal(proposal: InboxProposal): { title: string; detail: string } {
  const p = proposal
  if (p.kind === 'ledger') return {
    title: `${p.data.direction === 'income' ? '收入' : '支出'} ${p.data.amount} ${p.data.currency ?? 'CNY'}`,
    detail: [p.data.day, p.data.category ?? '未分类', p.data.payee, p.data.account ?? '默认账户'].filter(Boolean).join(' · '),
  }
  if (p.kind === 'event') return {
    title: p.data.title,
    detail: [p.data.date, p.data.start_time ? `${p.data.start_time}–${p.data.end_time}` : '全天', p.data.location, (p.data.remind_offsets ?? []).length ? '提醒：' + p.data.remind_offsets!.map(n => n === 0 ? '准时' : `提前${n}分钟`).join(' / ') + (!p.data.start_time && p.data.reminder_time ? `（${p.data.reminder_time}）` : '') : ''].filter(Boolean).join(' · '),
  }
  return { title: p.data.title, detail: p.data.due_date
    ? `截止 ${p.data.due_date.slice(0, 10)}${p.data.due_time ? ' ' + p.data.due_time : ''}` : '待办 · 未设截止日期' }
}
