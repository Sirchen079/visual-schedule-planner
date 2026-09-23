import { http } from './http'
import type { AttachmentMeta } from './ai'
import type { UserAnswer, UserInputRequest } from './userInput'

export interface Draft { text: string; attachments: AttachmentMeta[] }
export interface Workspace { revision: number; state: { active_id: number | null; drafts: Record<string, Draft>; question_drafts?: Record<string, Record<string, UserAnswer>> } }
/** 「黑板」面板内容：AI 用 show_blackboard 工具推送的自包含 HTML 页 */
export interface BlackboardPage { title: string; html: string }
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
  questions?: UserInputRequest[]
  work_plan?: Array<Record<string, unknown>>
  blackboard?: BlackboardPage | null
}
export const getConversationState = (cid: number) => http.get<ConversationState>(`/ai/conversations/${cid}/state`)
export const getWorkspace = (surface: string) => http.get<Workspace>(`/ai/workspaces/${surface}`)
export const putWorkspace = (surface: string, workspace: Workspace) => http.put<Workspace>(`/ai/workspaces/${surface}`, workspace)
