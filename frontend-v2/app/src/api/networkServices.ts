import { http } from './http'
import type { MCPServerInfo, McpToolInfo } from './settings'
import type { components } from './contracts/rest'

// Routers return materialized defaults; the editor also submits every field.
export type MCPSearchBinding = Required<components['schemas']['MCPSearchBinding']>
export type MCPFetchBinding = Required<components['schemas']['MCPFetchBinding']>
export type WebServicesConfig = Omit<Required<components['schemas']['WebServicesConfig']>, 'mcp_search' | 'mcp_fetch'> & {
  mcp_search: MCPSearchBinding | null
  mcp_fetch: MCPFetchBinding | null
}
export type WebProvider = WebServicesConfig['search_provider']
export type WebServicesOut = Omit<components['schemas']['WebServicesOut'], 'config'> & { config: WebServicesConfig }
export type JsonValue = components['schemas']['JsonValue']
export type VisionConfig = Required<components['schemas']['VisionConfig']>
export type CredentialOut = components['schemas']['CredentialOut']

export const getWebServices = () => http.get<WebServicesOut>('/ai/web-services')
export const saveWebServices = (config: WebServicesConfig) => http.put<WebServicesOut>('/ai/web-services', config)
export const getVision = () => http.get<VisionConfig>('/ai/vision')
export const saveVision = (config: VisionConfig) => http.put<VisionConfig>('/ai/vision', config)
export const removeTavilyKey = () => http.del<CredentialOut>('/ai/web-services/credentials/tavily')
/** Blank means preserve. Credentials are never included in the ordinary settings body. */
export function saveTavilyKey(value: string): Promise<CredentialOut | null> {
  const api_key = value.trim()
  return api_key ? http.put<CredentialOut>('/ai/web-services/credentials/tavily', { api_key }) : Promise.resolve(null)
}

export function defaultSearchBinding(): MCPSearchBinding {
  return { server_id: 0, tool_name: '', query_argument: 'query', limit_argument: 'max_results', results_path: 'results', title_field: 'title', url_field: 'url', description_field: 'content' }
}
export function defaultFetchBinding(): MCPFetchBinding {
  return { server_id: 0, tool_name: '', url_argument: 'url', url_as_list: false, content_path: '' }
}
export function mcpServerIssue(server: MCPServerInfo | undefined): string {
  if (!server) return '请选择已有的 MCP 服务器'
  if (!server.enabled) return '服务器尚未启用'
  if (!['http', 'stdio'].includes(server.transport)) return '服务器传输方式不受支持'
  if (server.transport === 'stdio' && !server.trusted) return '本地 stdio 服务器尚未受信任'
  if (!server.auto_approve_readonly) return '尚未允许自动执行只读工具'
  return ''
}
export function mcpToolIssue(tool: McpToolInfo | undefined, arguments_: Record<string, unknown>): string {
  if (!tool) return '请加载工具并选择一个可用工具'
  if (!tool.read_only) return '所选工具未声明为只读，不能自动调用'
  const schema = tool.input_schema as Record<string, unknown>
  const required = Array.isArray(schema?.required) ? schema.required.filter((key): key is string => typeof key === 'string') : []
  const missing = required.filter(key => !Object.prototype.hasOwnProperty.call(arguments_, key))
  return missing.length ? `缺少工具必填参数：${missing.join('、')}。请调整高级参数映射或选择兼容工具。` : ''
}

export function parseVisionArguments(text: string, server: MCPServerInfo | undefined, enabled: boolean): Record<string, JsonValue> {
  let value: unknown
  try { value = JSON.parse(text) } catch { throw new Error('视觉参数须为有效 JSON，请检查引号和逗号') }
  if (!value || Array.isArray(value) || typeof value !== 'object') throw new Error('视觉参数须为 JSON 对象')
  if (text.length > 16000) throw new Error('视觉参数模板最多 16000 个字符')
  const tokens = new Set<string>()
  const allowed = new Set(['image_data_url', 'image_path', 'prompt', 'filename', 'mime_type'])
  function walk(item: unknown, depth: number) {
    if (depth > 12) throw new Error('参数模板嵌套过深')
    if (Array.isArray(item)) { item.forEach(v => walk(v, depth + 1)); return }
    if (item && typeof item === 'object') {
      for (const [key, v] of Object.entries(item)) {
        if (/api.?key|authorization|password|secret|token|headers|env|\{\{|\}\}/i.test(key)) throw new Error('参数模板不能包含凭据；请在 MCP 服务器设置中管理凭据')
        walk(v, depth + 1)
      }
    } else if (typeof item === 'string') {
      const remaining = item.replace(/\{\{\s*([a-z_]+)\s*\}\}/g, (_, token: string) => {
        if (!allowed.has(token)) throw new Error(`不支持占位符：${token}`)
        tokens.add(token)
        return ''
      })
      if (/\{\{|\}\}/.test(remaining)) throw new Error('视觉参数包含不完整的占位符')
    }
  }
  walk(value, 0)
  if (tokens.has('image_path') && !(server?.transport === 'stdio' && server.trusted)) throw new Error('image_path 仅适用于受信任的本地 stdio 服务器；远程服务请用 image_data_url')
  if (enabled && !tokens.has('image_data_url') && !tokens.has('image_path')) throw new Error('视觉参数必须包含 {{image_data_url}} 或 {{image_path}}')
  return value as Record<string, JsonValue>
}
