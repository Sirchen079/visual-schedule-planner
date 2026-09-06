import type { components } from './contracts/rest'
import { http } from './http'
type S = components['schemas']
export type MaterialRead = S['MaterialRead']
export type MaterialSearch = S['MaterialSearch']
export const readMaterial = (id: number, part = 1, revision?: string): Promise<MaterialRead> => http.get(`/api/materials/${id}`, { part, revision })
export const searchMaterials = (query: string, file_id?: number, project_id?: number, file_offset = 0): Promise<MaterialSearch> => http.get('/api/materials/search', { query, file_id, project_id, file_offset })
export function materialTarget(file: number, part = 1, revision?: string): string {
  const query = new URLSearchParams({ file: String(file), part: String(part) })
  if (revision) query.set('revision', revision)
  return '/library?' + query.toString()
}
