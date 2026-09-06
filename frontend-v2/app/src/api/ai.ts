/** AI 会话与附件 REST 接口。历史消息包含展示文本、附件及持久化的执行元数据。 */
import { HttpError, http } from './http'

export interface ConversationSummary {
  id: number
  title: string
  updated_at: string
}

export interface AttachmentMeta {
  id: number
  name: string
  excerpt?: string
}

/** 持久化消息的展示数据，包括文本、附件、推理和工具执行记录。 */
export interface ConversationMessageDisplay {
  text: string
  run_id?: string
  status?: string
  error?: string | null
  reasoning?: string
  tools?: Array<Record<string, unknown>>
  attachments?: AttachmentMeta[]
}

export interface ConversationMessage {
  id: number
  role: 'user' | 'assistant' | string
  display: ConversationMessageDisplay
  created_at: string
}

export interface UploadAttachmentResult {
  file_id: number
  name: string
  kind: string
  parse_status: string
}

export function listConversations(): Promise<ConversationSummary[]> {
  return http.get<ConversationSummary[]>('/ai/conversations')
}

export function getConversationMessages(cid: number): Promise<ConversationMessage[]> {
  return http.get<ConversationMessage[]>(`/ai/conversations/${cid}`)
}

export function deleteConversation(cid: number): Promise<void> {
  return http.del(`/ai/conversations/${cid}`)
}

/** multipart 上传：不能用 http.ts 的 JSON 封装，直接 FormData（fetch 自动设 boundary）。 */
export async function uploadAttachment(file: File): Promise<UploadAttachmentResult> {
  const form = new FormData()
  form.append('file', file)
  let res: Response
  try {
    res = await fetch('/ai/attachments', { method: 'POST', body: form })
  } catch {
    throw new HttpError(0, '网络错误：无法连接本地服务（127.0.0.1:8421）')
  }
  if (!res.ok) throw await normalizeError(res)
  return (await res.json()) as UploadAttachmentResult
}

async function normalizeError(res: Response): Promise<HttpError> {
  // 与 http.ts 的 normalizeError 同规（避免导出该内部函数，这里复制最小实现）
  let message = `请求失败（HTTP ${res.status}）`
  try {
    const data: unknown = await res.json()
    if (data && typeof data === 'object') {
      const d = data as Record<string, unknown>
      if (typeof d.detail === 'string') message = d.detail
    }
  } catch {
    // 非 JSON 错误体
  }
  return new HttpError(res.status, message)
}
