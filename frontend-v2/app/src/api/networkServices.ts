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
export type WebServicesOut = Omit<Required<components['schemas']['WebServicesOut']>, 'config'> & { config: WebServicesConfig }
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
export function mcpServerIssue(server: MCPServerInfo | undefined, vision = false): string {
  if (!server) return '请选择已有的 MCP 服务器'
  if (!server.enabled) return '服务器尚未启用'
  if (!['http', 'stdio'].includes(server.transport)) return '服务器传输方式不受支持'
  if (server.transport === 'stdio' && !server.trusted) return '本地 stdio 服务器尚未受信任'
  // Vision is server-level consent: the model picks the tool at runtime, so the
  // read-only auto-approval flag is irrelevant for the vision lane.
  if (!vision && !server.auto_approve_readonly) return '尚未允许自动执行只读工具'
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
