import type { components } from './contracts/rest'
import { http } from './http'
type S = components['schemas']
export type Bill = S['BillRead']
export type Occurrence = S['BillOccurrenceRead']
export type BillInput = S['BillCreate']
export type Payment = S['BillPayment']
export const listBills = (offset = 0): Promise<S['BillPage']> => http.get('/api/bills', { offset, limit: 20 })
export const readBill = (id: number): Promise<Bill> => http.get(`/api/bills/${id}`)
export const createBill = (payload: BillInput): Promise<Bill> => http.post('/api/bills', payload)
export const updateBill = (id: number, payload: S['BillUpdate']): Promise<Bill> => http.put(`/api/bills/${id}`, payload)
export const billHistory = (id: number, before?: number): Promise<S['BillHistory']> => http.get(`/api/bills/${id}/history`, { before })
export const payBill = (id: number, payload: Payment): Promise<Occurrence> => http.post(`/api/bills/occurrences/${id}/pay`, payload)
export const skipBill = (id: number, version: number, reason: string): Promise<Occurrence> => http.post(`/api/bills/occurrences/${id}/skip`, { version, reason })

export const readOccurrence = (id: number): Promise<Occurrence> => http.get(`/api/bills/occurrences/${id}`)
