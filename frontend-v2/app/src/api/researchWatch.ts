import type { components } from './contracts/rest'
import { http } from './http'
type S = components['schemas']
export type Watch = S['WatchRead']
export type Config = S['WatchConfig']
export type Run = S['WatchRunRead']
export const readWatch = (id: number, before?: number): Promise<Watch> => http.get(`/api/research/projects/${id}/watch`, { before })
export const saveWatch = (id: number, value: S['WatchUpdate']): Promise<Watch> => http.put(`/api/research/projects/${id}/watch`, value)
export const runWatch = (id: number): Promise<Run> => http.post(`/api/research/projects/${id}/watch/run`, {})
