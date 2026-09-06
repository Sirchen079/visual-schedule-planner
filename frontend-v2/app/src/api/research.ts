import type { components } from './contracts/rest'
import { http } from './http'
type S = components['schemas']
export type Project = S['ProjectRead']
export type ProjectSpec = S['ProjectSpec']
export type ProjectDetail = S['ProjectDetail']
export type ResearchPlan = S['PlanRead']
export type ResearchSource = S['SourceRead']
export type Step = S['StepDraft']
export type Feedback = S['FeedbackRead']
export type FeedbackInput = Omit<S['FeedbackCreate'], 'version' | 'request_key'>
export type FeedbackPage = S['FeedbackPage']
export type RevisionDraft = S['RevisionDraft']
export type PlanHistory = S['PlanHistory']
const base = '/api/research'
export const listProjects = (archived = false): Promise<Project[]> => http.get(`${base}/projects`, { archived })
export const readProject = (id: number): Promise<ProjectDetail> => http.get(`${base}/projects/${id}`)
export const createProject = (spec: ProjectSpec, request_key: string): Promise<Project> => http.post(`${base}/projects`, { ...spec, request_key })
export const updateProject = (id: number, version: number, spec: ProjectSpec): Promise<Project> => http.put(`${base}/projects/${id}`, { version, spec })
export const archiveProject = (p: Project): Promise<Project> => http.post(`${base}/projects/${p.id}/archive`, { version: p.version, archived: p.status === 'active' })
export const gatherSources = (id: number): Promise<S['GatherResult']> => http.post(`${base}/projects/${id}/sources/gather`, { max_sources: 3 })
export const addSource = (id: number, url: string): Promise<ResearchSource> => http.post(`${base}/projects/${id}/sources`, { url })
export const fetchSource = (id: number, sid: number, refresh = false): Promise<ResearchSource> => http.post(`${base}/projects/${id}/sources/${sid}/fetch?refresh=${refresh}`, {})
export const attachMaterial = (id: number, file_id: number): Promise<ResearchSource> => http.post(`${base}/projects/${id}/materials`, { file_id })
export const previewPlan = (id: number, version: number, rationale: string, steps: Step[]): Promise<ResearchPlan> => http.post(`${base}/projects/${id}/plans`, { version, rationale, steps })
export const replan = (p: Project): Promise<ResearchPlan> => http.post(`${base}/projects/${p.id}/replan`, { version: p.version })
export const applyPlan = (id: number): Promise<ResearchPlan> => http.post(`${base}/plans/${id}/apply`, {})
export const readPlan = (id: number): Promise<ResearchPlan> => http.get(`${base}/plans/${id}`)
export const listFeedback = (id: number, before?: number | null): Promise<FeedbackPage> => http.get(`${base}/projects/${id}/feedback`, before ? { before } : {})
export const recordFeedback = (p: Project, input: FeedbackInput, request_key: string): Promise<Feedback> => http.post(`${base}/projects/${p.id}/feedback`, { ...input, version: p.version, request_key })
export const withdrawFeedback = (p: Project, id: number): Promise<Feedback> => http.post(`${base}/projects/${p.id}/feedback/${id}/withdraw`, { version: p.version })
export const previewExtension = (id: number, version: number, rationale: string, steps: Step[], feedback_ids: number[]): Promise<ResearchPlan> => http.post(`${base}/projects/${id}/extensions`, { version, rationale, steps, feedback_ids })
export const previewRevision = (id: number, plan: RevisionDraft): Promise<ResearchPlan> => http.post(`${base}/projects/${id}/revisions`, plan)
export const listPlans = (id: number, before?: number | null): Promise<PlanHistory> => http.get(`${base}/projects/${id}/plans`, before ? { before } : {})
export function publicSourceUrl(value: string): string | undefined {
  try { const u = new URL(value); return ['http:', 'https:'].includes(u.protocol) && !u.username && !u.password ? u.href : undefined } catch { return undefined }
}
