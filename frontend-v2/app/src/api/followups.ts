import type { components } from './contracts/rest'
import { http } from './http'
type S = components['schemas']
export type Followup = S['FollowupRead']
export type FollowupStatus = S['FollowupStatus']
export const listFollowups = (project_id: number): Promise<Followup[]> => http.get('/api/followups', { project_id })
export const followupStatus = (): Promise<FollowupStatus> => http.get('/api/followups/status')
export const setFollowupEnabled = (enabled: boolean): Promise<FollowupStatus> => http.put('/api/followups/preferences', { enabled })
export const checkProgress = (project_id: number): Promise<Followup | null> => http.post('/api/followups/check', { project_id })
export const readFollowup = (id: number): Promise<Followup> => http.get(`/api/followups/${id}`)
export const applyFollowup = (row: Followup): Promise<Followup> => http.post(`/api/followups/${row.id}/apply`, { version: row.version })
export const respondFollowup = (row: Followup, snooze_until?: string): Promise<Followup> => http.post(`/api/followups/${row.id}/respond`, { version: row.version, snooze_until: snooze_until ?? null })
export function followupTarget(value?: string | null): string | undefined {
  return value && /^\/research\?project=[1-9]\d*&followup=[1-9]\d*$/.test(value) ? value : undefined
}
