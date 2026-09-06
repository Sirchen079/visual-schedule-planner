import { http } from './http'
import type { AttachmentMeta } from './ai'

export interface Draft { text: string; attachments: AttachmentMeta[] }
export interface Workspace { revision: number; state: { active_id: number | null; drafts: Record<string, Draft> } }
export interface ConversationState {
  conversation_id: number
  active_run_id: string | null
  latest_run_id: string | null
  status: string
  approvals: Array<{ action_id: number; tool: string; args: Record<string, unknown>; preview: string; grant_available: boolean; status: string }>
  plan: { id: number; title: string; steps: Array<Record<string, unknown>> } | null
  can_resume: boolean
  message_count: number
  archive_count: number
  working_rounds: number
  summary: string
  model: string
  context_window: number | null
}
export const getConversationState = (cid: number) => http.get<ConversationState>(`/ai/conversations/${cid}/state`)
export const getWorkspace = (surface: string) => http.get<Workspace>(`/ai/workspaces/${surface}`)
export const putWorkspace = (surface: string, workspace: Workspace) => http.put<Workspace>(`/ai/workspaces/${surface}`, workspace)
