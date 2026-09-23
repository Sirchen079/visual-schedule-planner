/**
 * 长期记忆客户端。
 * 契约（手工定义，不走 contracts 生成类型——rest.d.ts 红线：不重生成，新增端点类型自持）：
 * - GET  /api/memories                → MemoryItem[]（扁平列表 + kind 字段，updated_at 倒序）
 * - POST /api/memories                → MemoryItem（手动添加，source 固定 'user'）
 * - PATCH /api/memories/{id}          → MemoryItem（缺省字段不动；kind/content/keywords）
 * - DELETE /api/memories/{id}         → {"ok": true}
 * - GET/PUT /api/memories/enabled     → {"enabled": boolean}（开关语义默认开：缺失视为开）
 */
import { http } from './http'

/** 记忆分类：用户画像 / 偏好 / 决定 / 事实 / 项目背景 */
export type MemoryKind = 'profile' | 'preference' | 'decision' | 'fact' | 'project'

export interface MemoryItem {
  id: number
  kind: MemoryKind
  content: string
  keywords: string
  /** 'ai' = AI 记下；'user' = 手动添加 */
  source: 'ai' | 'user'
  source_conversation_id: number | null
  created_at: string
  updated_at: string
}

export interface MemoryCreateBody {
  kind: MemoryKind
  content: string
  keywords?: string
}

/** PATCH 语义：缺省字段后端不动 */
export interface MemoryUpdateBody {
  kind?: MemoryKind
  content?: string
  keywords?: string
}

export interface MemoryEnabled {
  enabled: boolean
}

export function listMemories(): Promise<MemoryItem[]> {
  return http.get('/api/memories')
}

export function createMemory(body: MemoryCreateBody): Promise<MemoryItem> {
  return http.post('/api/memories', body)
}

export function updateMemory(id: number, body: MemoryUpdateBody): Promise<MemoryItem> {
  return http.patch(`/api/memories/${id}`, body)
}

export function deleteMemory(id: number): Promise<{ ok: boolean }> {
  return http.del(`/api/memories/${id}`)
}

export function getMemoryEnabled(): Promise<MemoryEnabled> {
  return http.get('/api/memories/enabled')
}

export function setMemoryEnabled(enabled: boolean): Promise<MemoryEnabled> {
  return http.put('/api/memories/enabled', { enabled })
}
