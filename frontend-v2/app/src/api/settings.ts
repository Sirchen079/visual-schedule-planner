/** 设置与 AI 管理接口。应用设置值使用字符串，PUT 提交部分更新。
 * MCP 的 env/headers 和模型密钥只写入，不回显敏感值。 */
import type { components } from './contracts/rest'
import { http } from './http'

/** 永久授权 = 生成 ToolGrantOut。 */
export type Grant = components['schemas']['ToolGrantOut']

/** 平铺设置表。已知键见 SettingsView 的消费；未知键原样保留（PUT 只交补丁）。 */
export type SettingsMap = Record<string, string>

/** MCP 服务器列表项。env/headers 不回显；command 可为空。 */
export type MCPServerInfo = components['schemas']['MCPServerOut']

/** 启用操作结果。AI 配置接口可能不包含 enabled 字段。 */
export type McpEnableResult = components['schemas']['EnableOut']

/** MCP 创建体 = 生成 MCPServerBody（全字段带后端缺省，UI 总是显式传齐避免歧义）。 */
export type MCPServerCreateBody = components['schemas']['MCPServerBody']

/** MCP 部分更新体 = 生成 MCPServerUpdate（全字段可空：null/缺省 = 不动该字段）。 */
export type MCPServerUpdateBody = components['schemas']['MCPServerUpdate']

/** AI 配置创建体 = 生成 ConfigBody。 */
export type ReasoningEffort = NonNullable<components['schemas']['ConfigBody']['reasoning_effort']>
export type InputModality = NonNullable<components['schemas']['ConfigBody']['input_modalities']>[number]
export type AiConfigCreateBody = components['schemas']['ConfigBody']

/** AI 技能创建体 = 生成 SkillBody。 */
export type SkillCreateBody = components['schemas']['SkillBody']

/** 创建类端点 201 回包 = 生成 CreatedOut：只回新行 id，创建后须重拉列表。 */
export type CreatedId = components['schemas']['CreatedOut']

/** MCP 工具清单项 = 生成 MCPToolOut（/tools 实时清单：name/description + input_schema/read_only）。 */
export type McpToolInfo = components['schemas']['MCPToolOut']

/** MCP 测试连接回包 = 生成 MCPTestOut：业务失败也是 200，看 ok 字段；失败带 error、tool_count=0。 */
export type McpTestResult = components['schemas']['MCPTestOut']

/** AI 配置列表项 = 生成 ConfigOut；api_key 属敏感永不回显。 */
export type AiConfigInfo = components['schemas']['ConfigOut']

/** AI 技能列表项 = 生成 SkillOut。 */
export type SkillInfo = components['schemas']['SkillOut']

/** 技能启用/停用回包 = 生成 EnableOut（与 MCP/配置启用同一统一回包，这里只用 ok）。 */
export type SkillEnableResult = components['schemas']['EnableOut']

export function getSettings(): Promise<SettingsMap> {
  return http.get<SettingsMap>('/api/settings')
}

/** 部分更新：后端包一层 {settings: patch}，回包为更新后的全量平铺表。 */
export function updateSettings(patch: SettingsMap): Promise<SettingsMap> {
  return http.put<SettingsMap>('/api/settings', { settings: patch })
}

export function listGrants(): Promise<Grant[]> {
  return http.get<Grant[]>('/ai/grants')
}

export function deleteGrant(grantId: number): Promise<void> {
  return http.del(`/ai/grants/${grantId}`)
}

/* ---- MCP 服务器（/ai/mcp/servers） ---- */

export function listMcpServers(): Promise<MCPServerInfo[]> {
  return http.get<MCPServerInfo[]>('/ai/mcp/servers')
}

/** 显式置 enabled（空体 {} 后端视为 true，这里总是显式传值避免歧义）。 */
export function setMcpServerEnabled(sid: number, enabled: boolean): Promise<McpEnableResult> {
  return http.post<McpEnableResult>(`/ai/mcp/servers/${sid}/enable`, { enabled })
}

/** 创建服务器：201 只回 {"id"}，创建后调用方必须重拉列表。 */
export function createMcpServer(body: MCPServerCreateBody): Promise<CreatedId> {
  return http.post<CreatedId>('/ai/mcp/servers', body)
}

/** 部分更新（MCPServerUpdate：仅传用户改过的字段，敏感字段留空 = 不发即不动）；回包为完整 MCPServerOut。 */
export function updateMcpServer(sid: number, patch: MCPServerUpdateBody): Promise<MCPServerInfo> {
  return http.put<MCPServerInfo>(`/ai/mcp/servers/${sid}`, patch)
}

export function deleteMcpServer(sid: number): Promise<void> {
  return http.del(`/ai/mcp/servers/${sid}`)
}

/** 测试连接：业务失败也是 200 看回包 ok；untrusted stdio → 403。端点会回写 last_status/last_error。 */
export function testMcpServer(sid: number): Promise<McpTestResult> {
  return http.post<McpTestResult>(`/ai/mcp/servers/${sid}/test`)
}

/** 实时工具清单；untrusted stdio 403、连接失败 502。 */
export function listMcpTools(sid: number): Promise<McpToolInfo[]> {
  return http.get<McpToolInfo[]>(`/ai/mcp/servers/${sid}/tools`)
}

/* ---- AI 配置（/ai/configs） ---- */

export function listAiConfigs(): Promise<AiConfigInfo[]> {
  return http.get<AiConfigInfo[]>('/ai/configs')
}

/** 创建配置：201 回 {"id"}（创建后重拉列表）；api_key 仅此次提交，之后不回显。 */
export function createAiConfig(body: AiConfigCreateBody): Promise<CreatedId> {
  return http.post<CreatedId>('/ai/configs', body)
}

/** 编辑提交完整 ConfigBody；空 api_key 保留已保存密钥。保存后重拉列表。 */
export function updateAiConfig(cid: number, body: AiConfigCreateBody): Promise<unknown> {
  return http.put<unknown>(`/ai/configs/${cid}`, body)
}

/** 启用（单选语义：会把其余配置全部置为未启用）。 */
export function enableAiConfig(cid: number): Promise<McpEnableResult> {
  return http.post<McpEnableResult>(`/ai/configs/${cid}/enable`)
}

/* ---- AI 技能（/ai/skills） ---- */

export function listSkills(): Promise<SkillInfo[]> {
  return http.get<SkillInfo[]>('/ai/skills')
}

/** 创建技能：201 回 {"id"}（创建后重拉列表）。建议 enabled=false 落库（单选激活交给用户显式启用）。 */
export function createSkill(body: SkillCreateBody): Promise<CreatedId> {
  return http.post<CreatedId>('/ai/skills', body)
}

/** 启用即单选激活（停用其余用户技能）；内置技能 404「技能不存在或为内置技能」。 */
export function enableSkill(sid: number): Promise<SkillEnableResult> {
  return http.post<SkillEnableResult>(`/ai/skills/${sid}/enable`)
}

/** 停用当前启用中的用户技能：幂等（无启用中也回 ok），内置技能不受影响。 */
export function disableActiveSkill(): Promise<SkillEnableResult> {
  return http.post<SkillEnableResult>('/ai/skills/disable-active')
}

export function deleteSkill(sid: number): Promise<void> {
  return http.del(`/ai/skills/${sid}`)
}
