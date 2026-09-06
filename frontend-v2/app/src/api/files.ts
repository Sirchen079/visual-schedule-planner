/** 资料库 REST 接口。上传使用 multipart 表单；类型来自生成的 rest.d.ts。 */
import type { components } from './contracts/rest'
import { http, HttpError } from './http'

type schemas = components['schemas']

/** 文件解析状态标签；未知状态保留原值。 */
export type ParseStatus = 'parsed' | 'pending' | 'unsupported' | 'failed' | (string & {})

/** 资料库文件类型。resource_type 的 file/link 值由视图判断。 */
export type LibraryFile = schemas['FileOut']

export interface FilePatchInput {
  notes?: string
}

export function listFiles(q?: string): Promise<LibraryFile[]> {
  return http.get<LibraryFile[]>('/api/files', q ? { q } : undefined)
}

export function listTrashFiles(): Promise<LibraryFile[]> {
  return http.get<LibraryFile[]>('/api/files/trash')
}

export function patchFile(fileId: number, patch: FilePatchInput): Promise<LibraryFile> {
  return http.patch<LibraryFile>(`/api/files/${fileId}`, patch)
}

export function deleteFile(fileId: number): Promise<void> {
  return http.del(`/api/files/${fileId}`)
}

export function restoreFile(fileId: number): Promise<LibraryFile> {
  return http.post<LibraryFile>(`/api/files/${fileId}/restore`)
}

export function purgeFile(fileId: number): Promise<void> {
  return http.del(`/api/files/${fileId}/purge`)
}

export function listTaskFiles(taskId: number): Promise<LibraryFile[]> {
  return http.get<LibraryFile[]>(`/api/files/tasks/${taskId}`)
}

/** 从 FastAPI 错误体提取可读消息（与 http.normalizeError 同语义，multipart 场景复用）。 */
async function normalizeError(res: Response): Promise<HttpError> {
  let message = `请求失败（HTTP ${res.status}）`
  try {
    const data: unknown = await res.json()
    if (data && typeof data === 'object') {
      const d = data as Record<string, unknown>
      if (typeof d.detail === 'string') message = d.detail
    }
  } catch {
    // 错误体不是 JSON，保留默认消息
  }
  return new HttpError(res.status, message)
}

/** 上传文件和可选 notes 表单字段，返回新文件记录。 */
export async function uploadFile(file: File, notes?: string): Promise<LibraryFile> {
  const form = new FormData()
  form.append('file', file)
  if (notes) form.append('notes', notes)
  let res: Response
  try {
    res = await fetch('/api/files', {
      method: 'POST',
      body: form,
    })
  } catch {
    throw new HttpError(0, '网络错误：无法连接本地服务（127.0.0.1:8421）')
  }
  if (!res.ok) throw await normalizeError(res)
  const text = await res.text()
  return JSON.parse(text) as LibraryFile
}
