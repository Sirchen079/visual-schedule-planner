/**
 * 设置页 store（扩展）：应用设置、AI 永久授权、MCP 服务器、AI 配置、AI 技能。
 * - 五路数据进页拉取，失败各自可见；动作错误统一进 actionError。
 * - setAutonomy / saveWorkingHours：PUT 部分更新后以回包全量落定（不乐观猜）。
 * - revokeGrant：收回即移除出行；失败保留并可见。
 * - MCP：enable 以回包 {enabled} 落定；创建 201 只回 {id} 故重拉列表；编辑以回包完整
 *   MCPServerOut 替换行；删除成功后出列；测试连接业务失败也是 200，回包整存 mcpTestResults
 *   供行内展示并同步行 last_status/last_error（端点会回写同值）；工具清单按 sid 缓存/报错。
 * - AI 配置：创建后重拉；启用为单选语义（其余落为未启用），以回包 ok 校验后本地落定。
 * - AI 技能：创建后重拉；启用即单选激活（其余用户技能停用、内置不动）；启用中可一键停用
 *   （disable-active，幂等）；删除成功后出列。
 * - 主题：reconcileTheme 以后端 ui.theme 调和跨端口偏好；saveThemePref 落库。
 */
import { defineStore } from 'pinia'
import { applyTheme, currentTheme, type ThemeName } from '../utils/theme'
import {
  createAiConfig,
  updateAiConfig,
  createMcpServer,
  createSkill,
  deleteGrant,
  deleteMcpServer,
  deleteSkill,
  disableActiveSkill,
  enableAiConfig,
  enableSkill,
  getSettings,
  listAiConfigs,
  listGrants,
  listMcpServers,
  listMcpTools,
  listSkills,
  setMcpServerEnabled,
  testMcpServer,
  updateMcpServer,
  updateSettings,
  type AiConfigCreateBody,
  type AiConfigInfo,
  type Grant,
  type MCPServerCreateBody,
  type MCPServerInfo,
  type MCPServerUpdateBody,
  type McpTestResult,
  type McpToolInfo,
  type SettingsMap,
  type SkillCreateBody,
  type SkillInfo,
} from '../api/settings'

export type Autonomy = 'standard' | 'careful'

export const AUTONOMY_LABELS: Record<Autonomy, string> = {
  standard: '标准',
  careful: '谨慎',
}

export const AUTONOMY_DESC: Record<Autonomy, string> = {
  standard: '安全类写入（如新建日程）直接执行；删除等敏感操作逐一请你批准。',
  careful: '所有写入都逐一请你批准，包括新建。最安心，也最受打扰。',
}

/** 从平铺表读自治档位，非法/缺失值回落 standard（后端缺省档）。 */
export function readAutonomy(settings: SettingsMap | null): Autonomy {
  return settings?.agent_autonomy === 'careful' ? 'careful' : 'standard'
}

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    settings: null as SettingsMap | null,
    grants: null as Grant[] | null,
    mcpServers: null as MCPServerInfo[] | null,
    configs: null as AiConfigInfo[] | null,
    skills: null as SkillInfo[] | null,
    loadingSettings: false,
    loadingGrants: false,
    loadingMcp: false,
    loadingConfigs: false,
    loadingSkills: false,
    settingsError: null as string | null,
    grantsError: null as string | null,
    mcpError: null as string | null,
    configsError: null as string | null,
    skillsError: null as string | null,
    actionError: null as string | null,
    /** 正在保存的设置补丁键（保存中禁用对应控件） */
    savingKeys: [] as string[],
    /** MCP 添加/编辑共用内联表单的提交中标记 */
    savingMcp: false,
    savingConfig: false,
    savingSkill: false,
    /** 收回中的授权 id / 开关、测试、删除中的服务器 id / 启用中的配置与技能 id */
    busyGrants: [] as number[],
    busyMcp: [] as number[],
    busyConfigs: [] as number[],
    busySkills: [] as number[],
    /** MCP 测试连接回包按服务器 id 存（业务失败 ok:false 也整存展示） */
    mcpTestResults: {} as Record<number, McpTestResult>,
    /** 已拉取的实时工具清单 / 拉取失败原因，按服务器 id */
    mcpTools: {} as Record<number, McpToolInfo[]>,
    mcpToolErrors: {} as Record<number, string>,
    /** 正在拉取工具清单的服务器 id */
    loadingTools: [] as number[],
  }),

  getters: {
    autonomy: (s): Autonomy => readAutonomy(s.settings),
    workingHoursStart: (s): string => s.settings?.working_hours_start ?? '09:00',
    workingHoursEnd: (s): string => s.settings?.working_hours_end ?? '18:00',
    dailyCapacity: (s): string => s.settings?.daily_capacity_minutes ?? '480',
  },

  actions: {
    /**
     * 主题跨端口调和（契约：ui.theme 存后端 settings KV 作跨端口权威源，
     * localStorage 只是本 origin 首帧缓存）。main.ts 挂载后
     * 调用：远端有值且与本地生效值不一致 → 以远端为准重刷并写缓存；远端无键而本地
     * 非缺省 → 播种回后端（升级前已选浅色的用户换端口不丢）。后端不可达保持本地，静默。
     */
    async reconcileTheme(): Promise<void> {
      try {
        const remote = (await getSettings())['ui.theme']
        const local = currentTheme()
        if (remote === 'light' || remote === 'dark') {
          if (remote !== local) applyTheme(remote)
        } else if (local !== 'dark') {
          void updateSettings({ 'ui.theme': local }).catch(() => {})
        }
      } catch {
        // 后端不可达：保持本地主题，下次启动再调和
      }
    },

    /** 设置页切换主题后持久化（调用方已 applyTheme 即点即生效）；落库失败不打扰。 */
    async saveThemePref(t: ThemeName): Promise<void> {
      try {
        const full = await updateSettings({ 'ui.theme': t })
        if (this.settings) this.settings = full
      } catch {
        // UI 偏好不落库不阻塞：本 origin 内 localStorage 已生效
      }
    },

    async loadSettings(): Promise<void> {
      this.loadingSettings = true
      this.settingsError = null
      try {
        this.settings = await getSettings()
      } catch (e) {
        this.settingsError = e instanceof Error ? e.message : '设置加载失败'
      } finally {
        this.loadingSettings = false
      }
    },

    async loadGrants(): Promise<void> {
      this.loadingGrants = true
      this.grantsError = null
      try {
        this.grants = await listGrants()
      } catch (e) {
        this.grantsError = e instanceof Error ? e.message : '授权列表加载失败'
      } finally {
        this.loadingGrants = false
      }
    },

    async loadMcpServers(): Promise<void> {
      this.loadingMcp = true
      this.mcpError = null
      try {
        this.mcpServers = await listMcpServers()
      } catch (e) {
        this.mcpError = e instanceof Error ? e.message : 'MCP 服务器加载失败'
      } finally {
        this.loadingMcp = false
      }
    },

    async loadConfigs(): Promise<void> {
      this.loadingConfigs = true
      this.configsError = null
      try {
        this.configs = await listAiConfigs()
      } catch (e) {
        this.configsError = e instanceof Error ? e.message : 'AI 配置加载失败'
      } finally {
        this.loadingConfigs = false
      }
    },

    async loadSkills(): Promise<void> {
      this.loadingSkills = true
      this.skillsError = null
      try {
        this.skills = await listSkills()
      } catch (e) {
        this.skillsError = e instanceof Error ? e.message : '技能列表加载失败'
      } finally {
        this.loadingSkills = false
      }
    },

    loadAll(): void {
      void this.loadSettings()
      void this.loadGrants()
      void this.loadMcpServers()
      void this.loadConfigs()
      void this.loadSkills()
    },

    /** 通用部分更新；patch 的键记入 savingKeys，回包全量落定。 */
    async saveSettings(patch: SettingsMap): Promise<boolean> {
      const keys = Object.keys(patch)
      this.savingKeys = [...this.savingKeys, ...keys]
      this.actionError = null
      try {
        this.settings = await updateSettings(patch)
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? `设置未保存：${e.message}` : '设置未保存'
        return false
      } finally {
        this.savingKeys = this.savingKeys.filter((k) => !keys.includes(k))
      }
    },

    async setAutonomy(tier: Autonomy): Promise<boolean> {
      return this.saveSettings({ agent_autonomy: tier })
    },

    async saveWorkingHours(start: string, end: string, capacityMinutes: string): Promise<boolean> {
      return this.saveSettings({
        working_hours_start: start,
        working_hours_end: end,
        daily_capacity_minutes: capacityMinutes,
      })
    },

    /** 收回永久授权：成功后出列；失败保留并 actionError 可见。 */
    async revokeGrant(grantId: number): Promise<boolean> {
      this.busyGrants = [...this.busyGrants, grantId]
      this.actionError = null
      try {
        await deleteGrant(grantId)
        this.grants = (this.grants ?? []).filter((g: Grant) => g.id !== grantId)
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? `收回失败：${e.message}` : '收回失败'
        return false
      } finally {
        this.busyGrants = this.busyGrants.filter((x) => x !== grantId)
      }
    },

    /* ---- MCP 服务器管理 ---- */

    /** 开关 MCP 服务器：以回包 enabled 落定。 */
    async toggleMcpServer(sid: number, enabled: boolean): Promise<boolean> {
      this.busyMcp = [...this.busyMcp, sid]
      this.actionError = null
      try {
        const res = await setMcpServerEnabled(sid, enabled)
        const row = (this.mcpServers ?? []).find((s) => s.id === sid)
        // enabled 缺失时使用请求的目标状态。
        if (row) row.enabled = res.enabled ?? enabled
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? `切换失败：${e.message}` : '切换失败'
        return false
      } finally {
        this.busyMcp = this.busyMcp.filter((x) => x !== sid)
      }
    },

    /** 添加服务器：201 只回 {id}，重拉列表落定（MCP 创建不回完整对象）。 */
    async addMcpServer(body: MCPServerCreateBody): Promise<boolean> {
      this.savingMcp = true
      this.actionError = null
      try {
        await createMcpServer(body)
        await this.loadMcpServers()
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? `添加失败：${e.message}` : '添加失败'
        return false
      } finally {
        this.savingMcp = false
      }
    },

    /** 保存编辑：PUT 部分更新（只发改过的字段），以回包完整 MCPServerOut 替换行。 */
    async saveMcpServer(sid: number, patch: MCPServerUpdateBody): Promise<boolean> {
      this.savingMcp = true
      this.actionError = null
      try {
        const row = await updateMcpServer(sid, patch)
        this.mcpServers = (this.mcpServers ?? []).map((s) => (s.id === sid ? row : s))
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? `保存失败：${e.message}` : '保存失败'
        return false
      } finally {
        this.savingMcp = false
      }
    },

    /** 删除服务器：成功后出列；失败保留并 actionError 可见。 */
    async removeMcpServer(sid: number): Promise<boolean> {
      this.busyMcp = [...this.busyMcp, sid]
      this.actionError = null
      try {
        await deleteMcpServer(sid)
        this.mcpServers = (this.mcpServers ?? []).filter((s) => s.id !== sid)
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? `删除失败：${e.message}` : '删除失败'
        return false
      } finally {
        this.busyMcp = this.busyMcp.filter((x) => x !== sid)
      }
    },

    /** 测试连接：业务失败也是 200 → 回包整存 mcpTestResults；并同步行 last_status/last_error（端点回写同值）。 */
    async testMcpConnection(sid: number): Promise<boolean> {
      this.busyMcp = [...this.busyMcp, sid]
      this.actionError = null
      try {
        const res = await testMcpServer(sid)
        this.mcpTestResults = { ...this.mcpTestResults, [sid]: res }
        const row = (this.mcpServers ?? []).find((s) => s.id === sid)
        if (row) {
          row.last_status = res.ok ? 'ok' : 'error'
          row.last_error = res.ok ? null : (res.error ?? '连接失败')
        }
        return res.ok
      } catch (e) {
        this.actionError = e instanceof Error ? `测试失败：${e.message}` : '测试失败'
        return false
      } finally {
        this.busyMcp = this.busyMcp.filter((x) => x !== sid)
      }
    },

    /** 拉取实时工具清单（「工具」展开时调用）；失败落 mcpToolErrors 供行内重试。 */
    async loadMcpTools(sid: number): Promise<void> {
      this.loadingTools = [...this.loadingTools, sid]
      this.mcpToolErrors = { ...this.mcpToolErrors, [sid]: '' }
      try {
        const tools = await listMcpTools(sid)
        this.mcpTools = { ...this.mcpTools, [sid]: tools }
      } catch (e) {
        this.mcpToolErrors = {
          ...this.mcpToolErrors,
          [sid]: e instanceof Error ? e.message : '工具清单拉取失败',
        }
      } finally {
        this.loadingTools = this.loadingTools.filter((x) => x !== sid)
      }
    },

    /* ---- AI 配置管理 ---- */

    /** 添加配置：201 只回 {id}，重拉列表落定。 */
    async addConfig(body: AiConfigCreateBody): Promise<boolean> {
      this.savingConfig = true
      this.actionError = null
      try {
        await createAiConfig(body)
        await this.loadConfigs()
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? `添加失败：${e.message}` : '添加失败'
        return false
      } finally {
        this.savingConfig = false
      }
    },

    /** 编辑提交全量配置，重新读取服务器保存结果；保存失败时保留原列表。 */
    async saveConfig(cid: number, body: AiConfigCreateBody): Promise<boolean> {
      this.savingConfig = true
      this.actionError = null
      try {
        await updateAiConfig(cid, body)
        await this.loadConfigs()
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? `保存失败：${e.message}` : '保存失败'
        return false
      } finally {
        this.savingConfig = false
      }
    },

    /** 启用配置（单选语义）：以回包 ok 校验后本地落定 —— 目标启用、其余全部未启用。 */
    async enableConfig(cid: number): Promise<boolean> {
      this.busyConfigs = [...this.busyConfigs, cid]
      this.actionError = null
      try {
        const res = await enableAiConfig(cid)
        if (res.ok === false) {
          this.actionError = '启用未生效，请重试'
          return false
        }
        this.configs = (this.configs ?? []).map((c) => ({ ...c, enabled: c.id === cid }))
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? `启用失败：${e.message}` : '启用失败'
        return false
      } finally {
        this.busyConfigs = this.busyConfigs.filter((x) => x !== cid)
      }
    },

    /* ---- AI 技能管理 ---- */

    /** 添加技能：201 只回 {id}，重拉列表落定。 */
    async addSkill(body: SkillCreateBody): Promise<boolean> {
      this.savingSkill = true
      this.actionError = null
      try {
        await createSkill(body)
        await this.loadSkills()
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? `添加失败：${e.message}` : '添加失败'
        return false
      } finally {
        this.savingSkill = false
      }
    },

    /** 启用技能（单选激活）：其余用户技能停用、内置技能不动；内置 id 传入会 404 走失败分支。 */
    async activateSkill(sid: number): Promise<boolean> {
      this.busySkills = [...this.busySkills, sid]
      this.actionError = null
      try {
        const res = await enableSkill(sid)
        if (!res.ok) {
          this.actionError = '技能未启用，请重试'
          return false
        }
        this.skills = (this.skills ?? []).map((s) =>
          s.is_builtin ? s : { ...s, enabled: s.id === sid },
        )
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? `启用失败：${e.message}` : '启用失败'
        return false
      } finally {
        this.busySkills = this.busySkills.filter((x) => x !== sid)
      }
    },

    /** 停用当前启用中的用户技能（幂等；内置技能不动）。无启用中也成功落定。 */
    async deactivateActiveSkill(): Promise<boolean> {
      this.actionError = null
      try {
        const res = await disableActiveSkill()
        if (!res.ok) {
          this.actionError = '技能未停用，请重试'
          return false
        }
        this.skills = (this.skills ?? []).map((s) =>
          s.is_builtin ? s : { ...s, enabled: false },
        )
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? `停用失败：${e.message}` : '停用失败'
        return false
      }
    },

    /** 删除用户技能：成功后出列；内置技能后端 404，失败保留并 actionError 可见。 */
    async removeSkill(sid: number): Promise<boolean> {
      this.busySkills = [...this.busySkills, sid]
      this.actionError = null
      try {
        await deleteSkill(sid)
        this.skills = (this.skills ?? []).filter((s) => s.id !== sid)
        return true
      } catch (e) {
        this.actionError = e instanceof Error ? `删除失败：${e.message}` : '删除失败'
        return false
      } finally {
        this.busySkills = this.busySkills.filter((x) => x !== sid)
      }
    },
  },
})
