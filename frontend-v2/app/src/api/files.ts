/**
 * 资料库域 REST 封装（/api/files/*）。类型已收敛到生成契约 rest.d.ts
 * （2026-09-05 契约批次 B1-B6 后全 typed，FileOut 就位，re #B6）：
 * - GET /api/files?q → FileOut[]（按上传时间倒序，实测）
 * - POST /api/files：multipart（file 二进制 + 可选 notes 表单域）→ 201 FileOut
 *   （PDF/DOCX/XLSX/CSV/TXT 上传即解析，parse_status: parsed；其他 pending/unsupported）
 * - GET /api/files/{id} → FileOut；PATCH /api/files/{id}（实测 {notes} 可用）→ FileOut
 * - DELETE /api/files/{id} → 204（入回收站）；POST /api/files/{id}/restore → FileOut；
 *   DELETE /api/files/{id}/purge → 204（连物理文件一起删）
 * - GET /api/files/trash → FileOut[]
 * - 关联任务：POST /api/files/{id}/attach/{task_id}、/detach/{task_id}；GET /api/files/tasks/{task_id}
 * - 网页链接登记：POST /api/files/links（AI import_web_resources 工具同源）
 *
 * 上传用独立 multipart 封装（http.ts 只做 JSON）：同源相对路径走 Vite 代理 / 后端 SPA 托管，
 * 错误规整与 http.normalizeError 同语义。
 */
import type { components } from './contracts/rest'
import { http, HttpError } from './http'

type schemas = components['schemas']

/** 解析状态（实测枚举 parsed/pending/unsupported/failed；生成 FileOut.parse_status 为 string，标签映射用）。 */
export type ParseStatus = 'parsed' | 'pending' | 'unsupported' | 'failed' | (string & {})

/**
 * 资料库文件 = 生成 FileOut（逐字段一致）。resource_type 实测枚举为 file/link，
 * 生成面为 string——视图仅做 === 'link' 比较，无需收窄。
 */
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

/**
 * multipart 上传（POST /api/files）。返回 201 FileOut。
 * re #B6：notes 为 multipart 表单域（原 query 传法后端静默忽略，本次对齐契约改为表单域）。
 */
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
