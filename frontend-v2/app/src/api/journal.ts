/**
 * 日记域 REST 封装（/api/journal/*）。类型已收敛到生成契约 rest.d.ts
 * （2026-09-05 契约批次 B1-B6 后全 typed）：
 * - GET /api/journal?limit=N → JournalEntryOut[]（按日期倒序，实测）
 * - GET /api/journal/today → JournalEntryOut | null（无条目 → 200 + 字面 null，2026-09-05 实测；
 *   旧手写注释「返回空形状条目」与契约/实测不符，已修正）
 * - GET /api/journal/{day} → JournalEntryOut | null（同上）
 * - PUT /api/journal/{day} {JournalUpsert} → JournalEntryOut（upsert，幂等）
 * - DELETE /api/journal/{day} → 204
 */
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
