/**
 * 会话文件夹附件客户端（对话绑定可读取的本地目录）。
 * 契约（手工定义，不走 contracts 生成类型——rest.d.ts 红线：不重生成，新增端点类型自持）：
 * - GET    /ai/conversations/{cid}/folders          → ConversationFolder[]（created_at ISO 字符串）
 * - POST   /ai/conversations/{cid}/folders          → 201 ConversationFolder（body {root_path}；
 *                                                     label 服务端取目录名；409 重复 / 400 非目录或不存在）
 * - DELETE /ai/conversations/{cid}/folders/{fid}    → 204
 */
import { http } from './http'

export interface ConversationFolder {
  id: number
  /** 展示名：服务端取 root_path 的目录名 */
  label: string
  root_path: string
  created_at: string
}

export function listFolders(cid: number): Promise<ConversationFolder[]> {
  return http.get(`/ai/conversations/${cid}/folders`)
}

export function attachFolder(cid: number, rootPath: string): Promise<ConversationFolder> {
  return http.post(`/ai/conversations/${cid}/folders`, { root_path: rootPath })
}

export function detachFolder(cid: number, id: number): Promise<void> {
  return http.del(`/ai/conversations/${cid}/folders/${id}`)
}
