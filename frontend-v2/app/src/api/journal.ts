/** 日记 REST 接口。列表按日期倒序；无指定日期的日记时返回 null；保存使用幂等 upsert。 */
import type { components } from './contracts/rest'
import { http } from './http'

type schemas = components['schemas']

/** 日记条目 = 生成 JournalEntryOut（mood 生成面为可选可空）。 */
export type JournalEntry = schemas['JournalEntryOut']

/** upsert 入参 = 生成 JournalUpsert：content 全量覆盖，mood 可空（清除心情）。 */
export type JournalUpsertInput = schemas['JournalUpsert']

export function listJournal(limit = 30): Promise<JournalEntry[]> {
  return http.get<JournalEntry[]>('/api/journal', { limit })
}

export function getJournalToday(): Promise<JournalEntry | null> {
  return http.get<JournalEntry | null>('/api/journal/today')
}

export function getJournalDay(day: string): Promise<JournalEntry | null> {
  return http.get<JournalEntry | null>(`/api/journal/${day}`)
}

export function upsertJournalDay(day: string, input: JournalUpsertInput): Promise<JournalEntry> {
  return http.put<JournalEntry>(`/api/journal/${day}`, input)
}

export function deleteJournalDay(day: string): Promise<void> {
  return http.del(`/api/journal/${day}`)
}
