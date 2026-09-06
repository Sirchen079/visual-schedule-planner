<script setup lang="ts">
import ProjectLink from '../components/ProjectLink.vue'
/**
 * 设置视图（/settings，次导航，M4a + M4c）：
 * AI 助手（自治档位/工作时段）+ 永久授权 + MCP 服务器（可管理）+ AI 配置 + 技能管理。
 * - 自治档位：standard/careful 二选一，点选即存（PUT 部分更新，回包落定）；
 *   新档位对下一条消息起的 run 生效，进行中的 run 不受影响。
 * - 永久授权：审批卡「始终允许」的沉淀；收回两段确认（防误触），收回后该工具回到逐次审批。
 * - MCP 服务器：增删改 + 启用开关 + 测试连接（结果显示工具数/错误）+ 工具清单展开；
 *   stdio 未信任时测试/工具禁用并提示（后端 403）；删除两段确认；添加/编辑共用内联表单，
 *   编辑与原行 diff 只发改过的字段，env/headers 不回显、留空 = 不发即不动。
 * - AI 配置：列表 + 添加（api_key 密码框，仅写入时提交）+ 启用（单选语义：启用新的自动停用上一个）；
 *   支持编辑连接信息与明确声明的输入能力，密钥永不回显。
 * - 技能管理：内置技能只读展示；用户技能启用为单选激活、删除两段确认；添加表单含正文 textarea。
 * - AI 写操作后自动刷新授权与 MCP 清单（授权可能由 run 中的「始终允许」新增）。
 */
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import DesktopPreferences from '../components/settings/DesktopPreferences.vue'
import ModelCapabilities from '../components/settings/ModelCapabilities.vue'
import NetworkPreferences from '../components/settings/NetworkPreferences.vue'
import { useModelCatalog } from '../composables/useModelCatalog'
import type { AiConfigInfo, InputModality, ReasoningEffort } from '../api/settings'
import DomainState from '../components/domain/DomainState.vue'
import { useRunStore } from '../stores/run'
import { AUTONOMY_DESC, AUTONOMY_LABELS, useSettingsStore, type Autonomy } from '../stores/settings'
import { applyTheme, currentTheme, type ThemeName } from '../utils/theme'
import type {
  AiConfigCreateBody,
  MCPServerCreateBody,
  MCPServerInfo,
  MCPServerUpdateBody,
  SkillCreateBody,
  SkillInfo,
} from '../api/settings'

const settings = useSettingsStore()
const run = useRunStore()
const route = useRoute()
const sections = [
  ['desktop', '悬浮窗与通知'], ['assistant', '外观与 AI 助手'], ['automation', '自动跟进'],
  ['configs', 'AI 模型'], ['network', '联网与视觉'], ['skills', '技能'], ['mcp', '外部工具'], ['grants', '授权'],
] as const
function jump(section: string) {
  if (sections.some(([id]) => id === section)) document.getElementById(`settings-${section}`)?.scrollIntoView({ block: 'start', behavior: 'smooth' })
}
watch(() => route.query.section, async value => { await nextTick(); if (typeof value === 'string') jump(value) })
const automationOptions = [
  { key: 'feature_followup_enabled', title: '学习与研究持续跟进', description: '检查学习进度，发现计划落后或需要调整时通知你。默认开启。' },
  { key: 'feature_autopilot_enabled', title: '秘书自动安排', description: '每天 08:00 后为临近截止的未排期任务安排日期，必要时拆分大任务；学习计划的自动调整仍遵守已有授权。默认关闭。' },
]
function automationEnabled(key: string) { return settings.settings?.[key] === 'true' }
function toggleAutomation(key: string) { void settings.saveSettings({ [key]: String(!automationEnabled(key)) }) }

/* ---- 工作时段编辑态（进页以 store 值初始化，保存后回落） ---- */
const hoursStart = ref('09:00')
const hoursEnd = ref('18:00')
const capacity = ref('480')

function syncHoursFromStore(): void {
  hoursStart.value = settings.workingHoursStart
  hoursEnd.value = settings.workingHoursEnd
  capacity.value = settings.dailyCapacity
}

const hoursDirty = ref(false)
function markDirty(): void {
  hoursDirty.value = true
}

async function saveHours(): Promise<void> {
  const ok = await settings.saveWorkingHours(hoursStart.value, hoursEnd.value, capacity.value)
  if (ok) hoursDirty.value = false
}

/* ---- 授权收回两段确认 ---- */
const confirmingGrant = ref<number | null>(null)

async function revokeGrant(id: number): Promise<void> {
  if (confirmingGrant.value !== id) {
    confirmingGrant.value = id
    return
  }
  confirmingGrant.value = null
  await settings.revokeGrant(id)
}

/* ---- MCP 状态徽标 ---- */
const MCP_STATUS_LABELS: Record<string, string> = {
  untested: '未测试',
  ok: '连接正常',
  error: '连接失败',
}

function mcpTargetLine(s: { transport: string; url: string | null; command: string | null }): string {
  return s.transport === 'http' ? (s.url ?? '—') : s.command || '—'
}

function grantDate(iso: string): string {
  return iso.slice(0, 10)
}

/* ---- MCP 添加/编辑共用内联表单（M4c） ---- */
const MCP_TRANSPORTS = ['http', 'stdio'] as const

interface McpFormModel {
  open: boolean
  /** null = 新增 */
  editId: number | null
  name: string
  transport: 'http' | 'stdio'
  url: string
  command: string
  argsJson: string
  envJson: string
  headersJson: string
  timeoutSec: string
  trusted: boolean
  autoApprove: boolean
  /** 编辑时的原行，用于 diff 出部分更新补丁 */
  orig: MCPServerInfo | null
}

const mcpForm = reactive<McpFormModel>({
  open: false,
  editId: null,
  name: '',
  transport: 'http',
  url: '',
  command: '',
  argsJson: '',
  envJson: '',
  headersJson: '',
  timeoutSec: '30',
  trusted: false,
  autoApprove: false,
  orig: null,
})
const mcpFormError = ref<string | null>(null)

const ARGS_PLACEHOLDER = 'JSON 数组，如 ["--port", "8080"]'
const ENV_PLACEHOLDER = 'JSON 对象，如 {"KEY": "value"}'
const HEADERS_PLACEHOLDER = 'JSON 对象，如 {"Authorization": "Bearer …"}'

function resetMcpForm(patch: Partial<McpFormModel>): void {
  Object.assign(mcpForm, {
    open: true,
    editId: null,
    name: '',
    transport: 'http',
    url: '',
    command: '',
    argsJson: '',
    envJson: '',
    headersJson: '',
    timeoutSec: '30',
    trusted: false,
    autoApprove: false,
    orig: null,
    ...patch,
  })
  mcpFormError.value = null
}

function openMcpCreate(): void {
  resetMcpForm({})
}

function openMcpEdit(s: MCPServerInfo): void {
  resetMcpForm({
    editId: s.id,
    name: s.name,
    transport: s.transport === 'stdio' ? 'stdio' : 'http',
    url: s.url ?? '',
    command: s.command ?? '',
    argsJson: s.args_json,
    // env/headers 属敏感配置、后端不回显：留空 = 不发即不修改
    envJson: '',
    headersJson: '',
    timeoutSec: String(s.timeout_sec),
    trusted: s.trusted,
    autoApprove: s.auto_approve_readonly,
    orig: s,
  })
}

function closeMcpForm(): void {
  mcpForm.open = false
  mcpForm.editId = null
  mcpForm.orig = null
  mcpFormError.value = null
}

/** JSON 输入校验：留空合法（create 落缺省、edit 表示不动），非空则必须可解析。 */
function validJsonOrMark(text: string, label: string): boolean {
  if (!text.trim()) return true
  try {
    JSON.parse(text)
    return true
  } catch {
    mcpFormError.value = `${label}需为合法 JSON`
    return false
  }
}

async function submitMcpForm(): Promise<void> {
  mcpFormError.value = null
  const name = mcpForm.name.trim()
  if (!name) {
    mcpFormError.value = '名称必填'
    return
  }
  const transport = mcpForm.transport
  if (transport === 'http' && !mcpForm.url.trim()) {
    mcpFormError.value = 'http 服务器需填写 URL'
    return
  }
  if (transport === 'stdio' && !mcpForm.command.trim()) {
    mcpFormError.value = 'stdio 服务器需填写启动命令'
    return
  }
  if (!validJsonOrMark(mcpForm.argsJson, '启动参数')) return
  if (!validJsonOrMark(mcpForm.envJson, '环境变量')) return
  if (!validJsonOrMark(mcpForm.headersJson, '请求头')) return
  const timeoutSec = Math.max(1, Math.floor(Number(mcpForm.timeoutSec) || 30))

  if (mcpForm.editId === null) {
    const body: MCPServerCreateBody = {
      name,
      transport,
      command: transport === 'stdio' ? mcpForm.command.trim() : '',
      args_json: mcpForm.argsJson.trim() || '[]',
      env_json: mcpForm.envJson.trim() || '{}',
      url: transport === 'http' ? (mcpForm.url.trim() || null) : null,
      headers_json: mcpForm.headersJson.trim() || '{}',
      timeout_sec: timeoutSec,
      enabled: false,
      auto_approve_readonly: mcpForm.autoApprove,
      trusted: mcpForm.trusted,
    }
    if (await settings.addMcpServer(body)) closeMcpForm()
    return
  }

  // 编辑：与原行 diff，只发改动过的字段（MCPServerUpdate 缺省/null = 后端不动该字段）
  const orig = mcpForm.orig
  if (!orig) return
  const patch: MCPServerUpdateBody = {}
  if (name !== orig.name) patch.name = name
  if (transport !== orig.transport) patch.transport = transport
  if (transport === 'http') {
    const url = mcpForm.url.trim() || null
    if (url !== (orig.url ?? null)) patch.url = url
    if (orig.command) patch.command = '' // 换回 http 时清掉历史命令
  } else {
    const command = mcpForm.command.trim()
    if (command !== (orig.command ?? '')) patch.command = command
    if (orig.url) patch.url = null
  }
  const argsValue = mcpForm.argsJson.trim() || '[]'
  if (argsValue !== orig.args_json) patch.args_json = argsValue
  if (mcpForm.envJson.trim()) patch.env_json = mcpForm.envJson.trim()
  if (mcpForm.headersJson.trim()) patch.headers_json = mcpForm.headersJson.trim()
  if (timeoutSec !== orig.timeout_sec) patch.timeout_sec = timeoutSec
  if (mcpForm.autoApprove !== orig.auto_approve_readonly) patch.auto_approve_readonly = mcpForm.autoApprove
  if (mcpForm.trusted !== orig.trusted) patch.trusted = mcpForm.trusted
  if (await settings.saveMcpServer(orig.id, patch)) closeMcpForm()
}

/* ---- MCP 删除两段确认 / 测试连接 / 工具展开 ---- */
const confirmingMcpDelete = ref<number | null>(null)

function removeMcp(s: MCPServerInfo): void {
  if (confirmingMcpDelete.value !== s.id) {
    confirmingMcpDelete.value = s.id
    return
  }
  confirmingMcpDelete.value = null
  void settings.removeMcpServer(s.id)
}

/** stdio 未信任：后端对 test/tools 一律 403，UI 直接禁用并说明。 */
function needsTrust(s: MCPServerInfo): boolean {
  return s.transport === 'stdio' && !s.trusted
}

function testResultLine(s: MCPServerInfo): string {
  const r = settings.mcpTestResults[s.id]
  if (!r) return ''
  return r.ok ? `连接正常 · ${r.tool_count} 个工具` : (r.error ?? '连接失败')
}

const expandedTools = ref<number | null>(null)

function toggleTools(s: MCPServerInfo): void {
  if (expandedTools.value === s.id) {
    expandedTools.value = null
    return
  }
  expandedTools.value = s.id
  if (!settings.mcpTools[s.id]) void settings.loadMcpTools(s.id)
}

/* ---- AI 配置添加 / 编辑：能力由用户确认，不从模型名称推断 ---- */
const configFormOpen = ref(false)
const configEdit = ref<AiConfigInfo | null>(null)
const configName = ref('')
const configModel = ref('')
const configProtocol = ref<'openai_compat' | 'openai_responses' | 'anthropic'>('openai_compat')
const configBaseUrl = ref('')
const configApiKey = ref('')
const configContextWindow = ref<string | number>('')
const configMaxOutputTokens = ref<string | number>('')
const configReasoningEffort = ref<ReasoningEffort | ''>('')
const configInputModalities = ref<InputModality[]>(['text'])
const configFormError = ref<string | null>(null)
const configConnectionChanged = computed(() => !!configEdit.value && (
  configProtocol.value !== configEdit.value.provider_kind ||
  configBaseUrl.value.trim() !== (configEdit.value.base_url ?? '').trim()
))

const catalog = useModelCatalog(configBaseUrl, configApiKey, configProtocol, () => configEdit.value?.id)
const catalogModels = catalog.models, catalogLoading = catalog.loading, catalogError = catalog.error, catalogLoaded = catalog.loaded, catalogTruncated = catalog.truncated
watch(configFormOpen, open => { if (!open) catalog.clear() }, { flush: 'sync' })
async function discoverModels(): Promise<void> {
  catalog.clear()
  if (configConnectionChanged.value && !configApiKey.value.trim()) {
    catalogError.value = '接口格式或地址已更改，请填写该服务的 Key 后再获取模型列表。'
    return
  }
  await catalog.discover()
}

function resetConfigFields(c: AiConfigInfo | null): void {
  configEdit.value = c ? { ...c } : null
  configName.value = c?.name ?? ''
  configModel.value = c?.model ?? ''
  configProtocol.value = c?.provider_kind === 'anthropic' || c?.provider_kind === 'openai_responses' ? c.provider_kind : 'openai_compat'
  configBaseUrl.value = c?.base_url ?? ''
  configApiKey.value = ''
  configContextWindow.value = c?.context_window ?? ''
  configMaxOutputTokens.value = c?.max_output_tokens ?? ''
  configReasoningEffort.value = c?.reasoning_effort ?? ''
  configInputModalities.value = [...(c?.input_modalities ?? ['text'])]
  configFormError.value = null
  catalog.clear()
}
function openConfigCreate(): void {
  resetConfigFields(null)
  configFormOpen.value = true
}
function openConfigEdit(c: AiConfigInfo): void {
  resetConfigFields(c)
  configFormOpen.value = true
  void nextTick(() => document.getElementById('settings-configs')?.scrollIntoView({ block: 'start', behavior: 'smooth' }))
}
function closeConfigForm(): void {
  configFormOpen.value = false
  resetConfigFields(null)
}
const MODALITY_LABELS: Record<InputModality, string> = { text: '文本', image: '图片', audio: '音频', video: '视频' }
const EFFORT_LABELS: Record<ReasoningEffort, string> = { none: '关闭', minimal: '极低', low: '低', medium: '中', high: '高', xhigh: '很高', max: '最高' }
function configCapabilitySummary(c: AiConfigInfo): string {
  return `${(c.input_modalities ?? ['text']).map(m => MODALITY_LABELS[m]).join(' / ') || '未选择输入类型'} · 上下文 ${c.context_window?.toLocaleString() ?? '未设置'} · 最大输出 ${c.max_output_tokens?.toLocaleString() ?? '未设置'} · 思考 ${c.reasoning_effort ? EFFORT_LABELS[c.reasoning_effort] : '跟随服务商'}`
}
function parseTokenLimit(raw: string | number, label: string, min: number, max: number): number | null {
  if (!String(raw).trim()) return null
  const value = Number(raw)
  if (!Number.isInteger(value) || value < min || value > max) throw new Error(`${label}须为 ${min.toLocaleString()} 至 ${max.toLocaleString()} 的整数，或留空。`)
  return value
}
async function submitConfigForm(): Promise<void> {
  if (settings.savingConfig) return
  configFormError.value = null
  const name = configName.value.trim(), model = configModel.value.trim()
  if (!name || !model) { configFormError.value = '名称与模型必填'; return }
  let contextWindow: number | null, maxOutputTokens: number | null
  try {
    contextWindow = parseTokenLimit(configContextWindow.value, '上下文窗口', 1024, 10_000_000)
    maxOutputTokens = parseTokenLimit(configMaxOutputTokens.value, '最大输出', 1, 1_000_000)
    if (contextWindow !== null && maxOutputTokens !== null && maxOutputTokens >= contextWindow) throw new Error('最大输出须小于上下文窗口。')
    if (configProtocol.value === 'anthropic' && configReasoningEffort.value === 'minimal') throw new Error('Anthropic 不支持极低档位，请重新选择思考程度。')
    if (!configInputModalities.value.includes('text')) throw new Error('AI 助手需要文本输入，必须保留文本。')
  } catch (e) {
    configFormError.value = e instanceof Error ? e.message : '请检查模型能力设置。'
    return
  }
  const original = configEdit.value
  const body: AiConfigCreateBody = {
    name, model, provider_kind: configProtocol.value,
    base_url: configBaseUrl.value.trim() || null,
    api_key: configApiKey.value.trim() || null,
    context_window: contextWindow, max_output_tokens: maxOutputTokens,
    input_modalities: [...configInputModalities.value], reasoning_effort: configReasoningEffort.value || null,
    // PUT 为完整 ConfigBody；保持不在此表单编辑的价格与请求限制。
    ...(original ? { price_input: original.price_input ?? 0, price_output: original.price_output ?? 0, request_limit: original.request_limit ?? 30 } : {}),
  }
  const ok = original ? await settings.saveConfig(original.id, body) : await settings.addConfig(body)
  if (ok) closeConfigForm()
}

/* ---- 技能添加表单与删除两段确认（M4c） ---- */
const skillFormOpen = ref(false)
const skillName = ref('')
const skillDesc = ref('')
const skillContent = ref('')
const skillFormError = ref<string | null>(null)

async function submitSkillForm(): Promise<void> {
  skillFormError.value = null
  const name = skillName.value.trim()
  if (!name) {
    skillFormError.value = '名称必填'
    return
  }
  const body: SkillCreateBody = {
    name,
    description: skillDesc.value.trim(),
    content: skillContent.value,
    // 新建默认停用：单选激活语义交给用户显式启用，避免悄悄改变 AI 行为
    enabled: false,
  }
  if (await settings.addSkill(body)) {
    skillFormOpen.value = false
    skillName.value = ''
    skillDesc.value = ''
    skillContent.value = ''
  }
}

const confirmingSkillDelete = ref<number | null>(null)

/** 停用当前启用中的用户技能（disable-active 为全局端点，不带 id）。 */
const disablingSkill = ref(false)

async function deactivateSkill(): Promise<void> {
  disablingSkill.value = true
  try {
    await settings.deactivateActiveSkill()
  } finally {
    disablingSkill.value = false
  }
}

function removeSkill(sk: SkillInfo): void {
  if (confirmingSkillDelete.value !== sk.id) {
    confirmingSkillDelete.value = sk.id
    return
  }
  confirmingSkillDelete.value = null
  void settings.removeSkill(sk.id)
}

/* ---- 外观主题（re #065：即点即生效走 applyTheme，跨端口持久化走后端 ui.theme 键） ---- */
const theme = ref<ThemeName>('dark')

function setTheme(t: ThemeName): void {
  theme.value = t
  applyTheme(t)
  void settings.saveThemePref(t)
}

onMounted(() => {
  // 主题在 main.ts 挂载前已引导（并可能刚被 reconcileTheme 调和），回读当前生效值点亮分段按钮
  theme.value = currentTheme()
  settings.loadAll()
  void nextTick(() => { if (typeof route.query.section === 'string') jump(route.query.section) })
})
watch(() => settings.settings, s => { if (s && !hoursDirty.value) syncHoursFromStore() }, { immediate: true })

/* run 结束后刷新授权与 MCP 清单（「始终允许」会在 run 中沉淀授权） */
watch(
  () => run.phase,
  (p, prev) => {
    if (prev && (p === 'completed' || p === 'cancelled')) {
      void settings.loadGrants()
      void settings.loadMcpServers()
    }
  },
)

const AUTONOMY_TIERS: Autonomy[] = ['standard', 'careful']
</script>

<template>
  <section class="settings-view">
    <Teleport defer to="#head-actions">
      <button class="reload" @click="settings.loadAll()">刷新</button>
    </Teleport>

    <header class="stv-head">
      <span class="stv-caption">设置</span>
      <span class="stv-note">悬浮窗、通知、外观和 AI 功能都在这里。点击分类可快速找到。</span>
    </header>
    <aside class="project-support"><div><strong>一起让知时更好用</strong><p>欢迎在 GitHub 提建议、反馈问题，或用一个 Star 支持项目。</p></div><ProjectLink prominent /></aside>
    <nav class="settings-nav" aria-label="设置分类">
      <button v-for="[id, label] in sections" :key="id" @click="jump(id)">{{ label }}</button>
    </nav>

    <p v-if="settings.actionError" class="stv-error" role="alert">{{ settings.actionError }}</p>

    <div class="panels">
      <DesktopPreferences />
      <section id="settings-automation" class="panel wide">
        <header class="p-head"><span class="p-title">自动跟进与安排</span></header>
        <p class="f-hint">在知时运行时生效；关闭主窗口并留在托盘即可继续，退出程序后暂停。</p>
        <div v-for="option in automationOptions" :key="option.key" class="auto-row">
          <div><span class="f-label">{{ option.title }}</span><p class="f-hint">{{ option.description }}</p></div>
          <button class="auto-switch" role="switch" :aria-label="option.title" :aria-checked="automationEnabled(option.key)" :disabled="!settings.settings || settings.loadingSettings || settings.savingKeys.length > 0" @click="toggleAutomation(option.key)"><span></span></button>
        </div>
      </section>
      <!-- AI 助手 -->
      <section id="settings-assistant" class="panel">
        <header class="p-head">
          <span class="p-title">外观与 AI 助手</span>
        </header>
        <DomainState
          :loading="settings.loadingSettings"
          loading-text="正在读取设置…"
          :error="settings.settingsError"
          :empty="false"
          @retry="settings.loadSettings()"
        />

        <!-- 外观：纯本地偏好，不依赖后端设置加载 -->
        <div class="f-group">
          <span class="f-label">外观</span>
          <div class="seg-row">
            <button class="seg" :class="{ on: theme === 'dark' }" @click="setTheme('dark')">深色</button>
            <button class="seg" :class="{ on: theme === 'light' }" @click="setTheme('light')">浅色</button>
          </div>
          <span class="f-hint">浅色是「日间书房」暖纸底色；偏好随本机后端保存，重启与换端口不丢。</span>
        </div>

        <template v-if="settings.settings">
          <div class="f-group">
            <span class="f-label">自治档位</span>
            <div class="tiers">
              <button
                v-for="tier in AUTONOMY_TIERS"
                :key="tier"
                class="tier"
                :class="{ on: settings.autonomy === tier }"
                :disabled="settings.savingKeys.includes('agent_autonomy')"
                @click="settings.setAutonomy(tier)"
              >
                <span class="t-name">{{ AUTONOMY_LABELS[tier] }}</span>
                <span class="t-desc">{{ AUTONOMY_DESC[tier] }}</span>
              </button>
            </div>
            <span class="f-hint">对下一条消息生效；不可逆操作（如彻底删除）任何档位都需批准。</span>
          </div>

          <div class="f-group">
            <span class="f-label">工作时段与日容量</span>
            <div class="hours-row">
              <input v-model="hoursStart" type="time" class="t-input" @input="markDirty" />
              <span class="hours-sep">至</span>
              <input v-model="hoursEnd" type="time" class="t-input" @input="markDirty" />
              <input v-model="capacity" type="number" min="0" step="30" class="t-input num" @input="markDirty" />
              <span class="hours-sep">分钟</span>
              <button
                class="act"
                :disabled="!hoursDirty || settings.savingKeys.includes('working_hours_start')"
                @click="saveHours"
              >
                {{ settings.savingKeys.includes('working_hours_start') ? '保存中…' : '保存' }}
              </button>
            </div>
            <span class="f-hint">AI 排程时会参考工作时段；日容量是每天可排的总分钟数。</span>
          </div>
        </template>
      </section>

      <!-- 永久授权 -->
      <section id="settings-grants" class="panel">
        <header class="p-head">
          <span class="p-title">永久授权</span>
          <span v-if="settings.grants" class="p-count">{{ settings.grants.length }} 项</span>
        </header>
        <DomainState
          :loading="settings.loadingGrants"
          loading-text="正在拉取授权列表…"
          :error="settings.grantsError"
          :empty="!settings.loadingGrants && settings.grants !== null && settings.grants.length === 0"
          empty-title="无永久授权"
          @retry="settings.loadGrants()"
        >
          审批卡上点「始终允许」才会产生授权；每一项都可以随时收回。
        </DomainState>
        <ul v-if="settings.grants && settings.grants.length > 0" class="items">
          <li v-for="g in settings.grants" :key="g.id" class="item">
            <div class="it-main">
              <span class="it-name mono">{{ g.tool_name }}</span>
              <span class="it-meta">参数 {{ g.arg_pattern }} · 授于 {{ grantDate(g.created_at) }}</span>
            </div>
            <button
              class="act"
              :class="{ danger: confirmingGrant === g.id }"
              :disabled="settings.busyGrants.includes(g.id)"
              @click="revokeGrant(g.id)"
            >
              {{ confirmingGrant === g.id ? '确认收回？' : '收回' }}
            </button>
            <button v-if="confirmingGrant === g.id" class="act" @click="confirmingGrant = null">取消</button>
          </li>
        </ul>
      </section>

      <!-- MCP 服务器（可管理） -->
      <section id="settings-mcp" class="panel wide">
        <header class="p-head">
          <span class="p-title">MCP 服务器</span>
          <span class="p-side">
            <span v-if="settings.mcpServers" class="p-count">{{ settings.mcpServers.length }} 台</span>
            <button class="act" @click="mcpForm.open && mcpForm.editId === null ? closeMcpForm() : openMcpCreate()">
              {{ mcpForm.open && mcpForm.editId === null ? '收起表单' : '添加服务器' }}
            </button>
          </span>
        </header>
        <DomainState
          :loading="settings.loadingMcp"
          loading-text="正在拉取 MCP 服务器…"
          :error="settings.mcpError"
          :empty="!settings.loadingMcp && settings.mcpServers !== null && settings.mcpServers.length === 0"
          empty-title="未配置"
          @retry="settings.loadMcpServers()"
        >
          接入外部 MCP 工具服务器后，AI 可以调用它们的能力；只读工具可设免审批。
        </DomainState>

        <!-- 添加 / 编辑内联表单 -->
        <form v-if="mcpForm.open" class="inline-form" @submit.prevent="submitMcpForm">
          <p class="form-title">
            {{ mcpForm.editId === null ? '添加 MCP 服务器' : `编辑「${mcpForm.orig?.name ?? ''}」` }}
          </p>
          <p v-if="mcpFormError" class="form-error" role="alert">{{ mcpFormError }}</p>
          <div class="form-row">
            <span class="f-label">名称</span>
            <input v-model="mcpForm.name" class="t-input grow" placeholder="如 filesystem" />
            <span class="f-label">传输</span>
            <button
              v-for="t in MCP_TRANSPORTS"
              :key="t"
              type="button"
              class="seg"
              :class="{ on: mcpForm.transport === t }"
              @click="mcpForm.transport = t"
            >
              {{ t }}
            </button>
          </div>
          <div v-if="mcpForm.transport === 'http'" class="form-row">
            <span class="f-label">URL</span>
            <input v-model="mcpForm.url" class="t-input grow" placeholder="http://127.0.0.1:9000/mcp" />
          </div>
          <template v-else>
            <div class="form-row">
              <span class="f-label">命令</span>
              <input v-model="mcpForm.command" class="t-input grow" placeholder="如 npx -y @modelcontextprotocol/server-fs" />
              <span class="f-label">启动参数</span>
              <input v-model="mcpForm.argsJson" class="t-input grow" :placeholder="ARGS_PLACEHOLDER" />
            </div>
            <div class="form-row">
              <span class="f-label">环境变量</span>
              <input v-model="mcpForm.envJson" class="t-input grow" :placeholder="ENV_PLACEHOLDER" />
            </div>
          </template>
          <div v-if="mcpForm.transport === 'http'" class="form-row">
            <span class="f-label">请求头</span>
            <input v-model="mcpForm.headersJson" class="t-input grow" :placeholder="HEADERS_PLACEHOLDER" />
          </div>
          <div class="form-row">
            <span class="f-label">超时（秒）</span>
            <input v-model="mcpForm.timeoutSec" type="number" min="1" class="t-input num" />
            <label class="check">
              <input v-model="mcpForm.autoApprove" type="checkbox" />
              只读工具免审批
            </label>
            <label class="check">
              <input v-model="mcpForm.trusted" type="checkbox" />
              信任此服务器
            </label>
          </div>
          <p v-if="mcpForm.transport === 'stdio'" class="f-hint warn">
            信任即授权：本机无认证环境下，信任后可被执行任意命令，仅信任你了解的来源。
          </p>
          <p v-if="mcpForm.editId !== null" class="f-hint">
            env / headers 属敏感配置、不回显：编辑时留空表示不修改。
          </p>
          <div class="form-row foot">
            <button type="submit" class="act" :disabled="settings.savingMcp">
              {{ settings.savingMcp ? '保存中…' : mcpForm.editId === null ? '添加' : '保存' }}
            </button>
            <button type="button" class="act" @click="closeMcpForm">取消</button>
          </div>
        </form>

        <ul v-if="settings.mcpServers && settings.mcpServers.length > 0" class="items">
          <li v-for="s in settings.mcpServers" :key="s.id" class="item stack">
            <div class="item-row">
              <div class="it-main">
                <span class="it-name">
                  {{ s.name }}
                  <span class="badge" :data-tone="s.last_status">{{ MCP_STATUS_LABELS[s.last_status] ?? s.last_status }}</span>
                  <span v-if="s.auto_approve_readonly" class="badge">只读免审</span>
                  <span v-if="s.trusted" class="badge">已信任</span>
                </span>
                <span class="it-meta">{{ s.transport }} · {{ mcpTargetLine(s) }} · {{ s.timeout_sec }}s</span>
                <span v-if="needsTrust(s)" class="it-meta wrap">
                  stdio 未信任：连接测试与工具清单不可用，点「编辑」勾选「信任此服务器」后开放。
                </span>
                <span v-if="s.last_status === 'error' && s.last_error" class="it-meta err wrap">{{ s.last_error }}</span>
              </div>
              <div class="it-acts">
                <button
                  class="act"
                  :disabled="settings.busyMcp.includes(s.id)"
                  @click="settings.toggleMcpServer(s.id, !s.enabled)"
                >
                  {{ s.enabled ? '停用' : '启用' }}
                </button>
                <button
                  class="act"
                  :disabled="settings.busyMcp.includes(s.id) || needsTrust(s)"
                  :title="needsTrust(s) ? 'stdio 服务器需先信任才能连接' : undefined"
                  @click="settings.testMcpConnection(s.id)"
                >
                  测试连接
                </button>
                <button
                  class="act"
                  :disabled="settings.busyMcp.includes(s.id) || needsTrust(s)"
                  :title="needsTrust(s) ? 'stdio 服务器需先信任才能拉取工具' : undefined"
                  @click="toggleTools(s)"
                >
                  {{ expandedTools === s.id ? '收起工具' : '工具' }}
                </button>
                <button class="act" :disabled="settings.busyMcp.includes(s.id)" @click="openMcpEdit(s)">编辑</button>
                <button
                  class="act danger"
                  :disabled="settings.busyMcp.includes(s.id)"
                  @click="removeMcp(s)"
                >
                  {{ confirmingMcpDelete === s.id ? '确认删除？' : '删除' }}
                </button>
                <button v-if="confirmingMcpDelete === s.id" class="act" @click="confirmingMcpDelete = null">取消</button>
              </div>
            </div>
            <p
              v-if="settings.mcpTestResults[s.id]"
              class="test-line"
              :class="{ err: !settings.mcpTestResults[s.id].ok }"
            >
              {{ testResultLine(s) }}
            </p>
            <div v-if="expandedTools === s.id" class="tools">
              <span v-if="settings.loadingTools.includes(s.id)" class="tools-note">
                正在拉取工具清单…
              </span>
              <span v-else-if="settings.mcpToolErrors[s.id]" class="tools-note err">
                {{ settings.mcpToolErrors[s.id] }}
                <button class="act" @click="settings.loadMcpTools(s.id)">重试</button>
              </span>
              <ul v-else-if="settings.mcpTools[s.id]?.length" class="tool-list">
                <li v-for="t in settings.mcpTools[s.id]" :key="t.name">
                  <span class="tool-name">{{ t.name }}</span>
                  <span v-if="t.description" class="tool-desc">{{ t.description }}</span>
                </li>
              </ul>
              <span v-else class="tools-note">该服务器未暴露任何工具。</span>
            </div>
          </li>
        </ul>
        <span class="f-hint">
          stdio 服务器必须显式信任后才能连接；env / headers 只在写入时提交，之后不再回显。
        </span>
      </section>

      <section id="settings-network" class="panel wide">
        <NetworkPreferences />
      </section>

      <!-- AI 配置 -->
      <section id="settings-configs" class="panel wide">
        <header class="p-head">
          <span class="p-title">AI 模型配置</span>
          <span class="p-side">
            <span v-if="settings.configs" class="p-count">{{ settings.configs.length }} 个</span>
            <button class="act" :disabled="settings.savingConfig" @click="configFormOpen ? closeConfigForm() : openConfigCreate()">
              {{ configFormOpen ? '收起表单' : '添加配置' }}
            </button>
          </span>
        </header>
        <DomainState
          :loading="settings.loadingConfigs"
          loading-text="正在拉取 AI 配置…"
          :error="settings.configsError"
          :empty="!configFormOpen && !settings.loadingConfigs && settings.configs !== null && settings.configs.length === 0"
          empty-title="未配置模型"
          @retry="settings.loadConfigs()"
        >
          添加模型配置并启用；报表生成与 AI 对话都用启用中的这个模型。
        </DomainState>

        <form v-if="configFormOpen" class="inline-form" @submit.prevent="submitConfigForm">
          <p class="form-title">{{ configEdit ? '编辑 AI 配置' : '添加 AI 配置' }}</p>
          <fieldset class="config-fields" :disabled="settings.savingConfig">
          <p v-if="configFormError" class="form-error" role="alert">{{ configFormError }}</p>
          <div class="form-row">
            <span class="f-label">名称</span>
            <input v-model="configName" aria-label="配置名称" class="t-input grow" placeholder="如 智谱Coding" />
          </div>
          <div class="form-row">
            <span class="f-label">接口格式</span>
            <select v-model="configProtocol" aria-label="接口格式" class="t-input grow"><option value="openai_compat">OpenAI Chat Completions</option><option value="openai_responses">OpenAI Responses</option><option value="anthropic">Anthropic</option></select>
          </div>
          <div class="form-row">
            <span class="f-label">Base URL</span>
            <input v-model="configBaseUrl" aria-label="Base URL" class="t-input grow" placeholder="https://…/v1（填写基础地址，不含 /responses）" />
          </div>
          <div class="form-row">
            <span class="f-label">API Key</span>
            <input
              v-model="configApiKey"
              type="password"
              aria-label="API Key"
              autocomplete="new-password"
              class="t-input grow"
              :placeholder="configEdit?.has_api_key ? '留空保留已保存的 Key' : 'sk-…'"
            />
          </div>
          <div class="form-row">
            <button id="fetch-models" type="button" class="act" :disabled="catalogLoading || !configBaseUrl.trim()" @click="discoverModels()">{{ catalogLoading ? '正在获取…' : '获取模型列表' }}</button>
            <span v-if="catalogLoaded" class="f-hint" role="status">{{ catalogModels.length ? `已获取 ${catalogModels.length} 个模型${catalogTruncated ? '（列表已截断）' : ''}` : '服务返回了空列表，可手动填写模型名称。' }}</span>
          </div>
          <p v-if="catalogError" class="form-error" role="alert">{{ catalogError }}</p>
          <div v-if="catalogModels.length" class="form-row">
            <label for="available-models" class="f-label">可用模型</label>
            <select id="available-models" v-model="configModel" class="t-input grow">
              <option value="">选择一个模型…</option>
              <option v-if="configModel && !catalogModels.some(m => m.id === configModel)" :value="configModel">{{ configModel }}（手动填写）</option>
              <option v-for="model in catalogModels" :key="model.id" :value="model.id">{{ model.name === model.id ? model.id : `${model.name} · ${model.id}` }}</option>
            </select>
          </div>
          <div class="form-row">
            <span class="f-label">模型名称</span>
            <input v-model="configModel" aria-label="模型名称" class="t-input grow" placeholder="从列表选择，或手动填写" />
          </div>
          <span class="f-hint">{{ configEdit ? 'Key 留空会保留已保存的密钥，填写新 Key 则替换。' : 'Key 仅在添加配置时保存，之后不再回显。' }} 获取模型列表不会保存配置。</span>
          <span v-if="configEdit && !configApiKey.trim()" class="f-hint">{{ configConnectionChanged ? '接口格式或地址已更改，获取列表前请填写该服务的 Key。' : configEdit.has_api_key ? '获取列表将使用此配置已保存的 Key。' : '此配置尚未保存 Key，可填写后获取模型列表。' }}</span>
          <ModelCapabilities :provider-kind="configProtocol" v-model:reasoning-effort="configReasoningEffort" v-model:context-window="configContextWindow" v-model:max-output-tokens="configMaxOutputTokens" v-model:input-modalities="configInputModalities" />
          <div class="form-row foot">
            <button type="submit" class="act" :disabled="settings.savingConfig">
              {{ settings.savingConfig ? '保存中…' : configEdit ? '保存更改' : '添加' }}
            </button>
            <button type="button" class="act" @click="closeConfigForm()">取消</button>
          </div>
          </fieldset>
        </form>

        <ul v-if="settings.configs && settings.configs.length > 0" class="items">
          <li v-for="c in settings.configs" :key="c.id" class="item">
            <div class="it-main">
              <span class="it-name">
                {{ c.name }}
                <span v-if="c.enabled" class="badge" data-tone="ok">启用中</span>
              </span>
              <span class="it-meta">{{ c.provider_kind }} · {{ c.model }} · {{ c.base_url || '—' }}</span>
              <span class="it-meta wrap">{{ configCapabilitySummary(c) }}</span>
            </div>
            <button class="act" :disabled="settings.savingConfig || settings.busyConfigs.includes(c.id)" :aria-label="`编辑配置 ${c.name}`" @click="openConfigEdit(c)">编辑</button>
            <button
              v-if="!c.enabled"
              class="act"
              :disabled="settings.savingConfig || settings.busyConfigs.includes(c.id)"
              @click="settings.enableConfig(c.id)"
            >
              {{ settings.busyConfigs.includes(c.id) ? '启用中…' : '启用' }}
            </button>
          </li>
        </ul>
        <span class="f-hint">
          同一时刻只有一个配置生效，启用新的会自动停用上一个。编辑已启用的配置后，后续请求使用新设置。
        </span>
      </section>

      <!-- 技能管理 -->
      <section id="settings-skills" class="panel wide">
        <header class="p-head">
          <span class="p-title">技能管理</span>
          <span class="p-side">
            <span v-if="settings.skills" class="p-count">{{ settings.skills.length }} 项</span>
            <button class="act" @click="skillFormOpen = !skillFormOpen">
              {{ skillFormOpen ? '收起表单' : '添加技能' }}
            </button>
          </span>
        </header>
        <DomainState
          :loading="settings.loadingSkills"
          loading-text="正在拉取技能列表…"
          :error="settings.skillsError"
          :empty="!settings.loadingSkills && settings.skills !== null && settings.skills.length === 0"
          empty-title="暂无技能"
          @retry="settings.loadSkills()"
        >
          内置技能随应用提供、始终生效；用户技能启用后注入 AI 对话，为它补充领域知识。
        </DomainState>

        <form v-if="skillFormOpen" class="inline-form" @submit.prevent="submitSkillForm">
          <p class="form-title">添加技能</p>
          <p v-if="skillFormError" class="form-error" role="alert">{{ skillFormError }}</p>
          <div class="form-row">
            <span class="f-label">名称</span>
            <input v-model="skillName" class="t-input grow" placeholder="如 周报写作偏好" />
            <span class="f-label">描述</span>
            <input v-model="skillDesc" class="t-input grow" placeholder="一句话说明它的用途" />
          </div>
          <textarea
            v-model="skillContent"
            class="t-input area"
            placeholder="技能正文：写给 AI 的指令与知识…"
          />
          <span class="f-hint">新建的技能默认停用，不会立刻改变 AI 行为；在下方列表点「启用」激活。</span>
          <div class="form-row foot">
            <button type="submit" class="act" :disabled="settings.savingSkill">
              {{ settings.savingSkill ? '添加中…' : '添加' }}
            </button>
            <button type="button" class="act" @click="skillFormOpen = false">取消</button>
          </div>
        </form>

        <ul v-if="settings.skills && settings.skills.length > 0" class="items">
          <li v-for="sk in settings.skills" :key="sk.id" class="item">
            <div class="it-main">
              <span class="it-name">
                {{ sk.name }}
                <span v-if="sk.is_builtin" class="badge">内置</span>
                <span v-if="sk.enabled" class="badge" data-tone="ok">{{ sk.is_builtin ? '始终生效' : '启用中' }}</span>
              </span>
              <span v-if="sk.description" class="it-meta wrap">{{ sk.description }}</span>
            </div>
            <template v-if="!sk.is_builtin">
              <button
                v-if="!sk.enabled"
                class="act"
                :disabled="settings.busySkills.includes(sk.id)"
                @click="settings.activateSkill(sk.id)"
              >
                {{ settings.busySkills.includes(sk.id) ? '启用中…' : '启用' }}
              </button>
              <button v-else class="act" :disabled="disablingSkill" @click="deactivateSkill">
                {{ disablingSkill ? '停用中…' : '停用' }}
              </button>
              <button
                class="act danger"
                :disabled="settings.busySkills.includes(sk.id)"
                @click="removeSkill(sk)"
              >
                {{ confirmingSkillDelete === sk.id ? '确认删除？' : '删除' }}
              </button>
              <button v-if="confirmingSkillDelete === sk.id" class="act" @click="confirmingSkillDelete = null">
                取消
              </button>
            </template>
          </li>
        </ul>
        <span class="f-hint">
          同一时刻至多启用一个用户技能，启用新的会自动停用上一个；「停用」关闭当前启用中的技能；内置技能不可更改。
        </span>
      </section>
    </div>
  </section>
</template>

<style scoped>
.project-support { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px; border:1px solid var(--line-2); border-radius:10px; background:var(--bg-raise); padding:14px 16px; }
.project-support strong { font-family:var(--serif); color:var(--ink-1); font-size:16px; font-weight:500; }
.project-support p { margin:5px 0 0; font-size:12px; line-height:1.6; color:var(--ink-3); }
.config-fields { display:flex; flex-direction:column; gap:10px; border:0; padding:0; margin:0; min-width:0; }
.settings-nav { display:flex; flex-wrap:wrap; gap:6px; position:sticky; top:-18px; z-index:2; padding:10px 0; background:var(--bg-app); }
.settings-nav button { border:1px solid var(--line-2); border-radius:16px; padding:6px 12px; color:var(--ink-2); font-size:12px; }
.settings-nav button:hover,.settings-nav button:focus-visible { color:var(--amber); border-color:var(--amber); }
.panel { scroll-margin-top:76px; }
.auto-row { display:flex; align-items:center; justify-content:space-between; gap:20px; padding:10px 0; }
.auto-row p { margin:5px 0 0; line-height:1.6; }
.auto-switch { flex-shrink:0; width:38px; height:22px; border-radius:12px; background:var(--line-2); padding:3px; }
.auto-switch>span { display:block; width:16px; height:16px; border-radius:50%; background:var(--bg-raise); box-shadow:0 1px 3px #0003; transition:transform .15s; }
.auto-switch[aria-checked=true] { background:var(--amber); }
.auto-switch[aria-checked=true]>span { transform:translateX(16px); }
.auto-switch:disabled { opacity:.5; cursor:wait; }
.auto-switch:focus-visible { outline:2px solid var(--amber); outline-offset:3px; }
.settings-view {
  flex: 1;
  min-height: 0;
  padding: 18px 22px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow: auto;
}

.reload {
  font-size: 12.5px;
  color: var(--ink-2);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-pill);
  padding: 4px 13px;
}
.reload:hover {
  border-color: var(--line-hover);
  color: var(--amber-soft);
}

.stv-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.stv-caption {
  font-family: var(--serif);
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--ink-2);
}
.stv-note {
  font-size: 11.5px;
  color: var(--ink-3);
}
.stv-error {
  font-size: 12px;
  color: var(--terra-soft);
}

.panels {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  align-items: start;
}
.panel {
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  background: var(--bg-raise);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 120px;
}
.panel.wide {
  grid-column: 1 / -1;
}
.p-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  border-bottom: 1px solid var(--line);
  padding-bottom: 8px;
}
.p-title {
  font-family: var(--serif);
  font-size: 14.5px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--ink-2);
}
.p-count {
  font-size: 11.5px;
  color: var(--ink-3);
}
.p-side {
  display: flex;
  align-items: center;
  gap: 10px;
}

.f-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.f-label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink-2);
  flex: none;
}
.f-hint {
  font-size: 11px;
  color: var(--ink-3);
  line-height: 1.6;
}
.f-hint.warn {
  color: var(--terra-soft);
}

.tiers {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.tier {
  display: flex;
  flex-direction: column;
  gap: 4px;
  text-align: left;
  border: 1px solid var(--line-2);
  border-radius: var(--radius-s);
  background: var(--bg-app);
  padding: 10px 12px;
}
.tier:hover {
  border-color: var(--line-hover);
}
.tier.on {
  border-color: var(--amber-border-mid);
  background: var(--amber-wash);
}
.tier:disabled {
  /* 浅色主题经 --ctl-disabled-opacity 抬到 0.75（弱标签禁用态 ≥3:1）；暗色走 fallback 0.6 不变 */
  opacity: var(--ctl-disabled-opacity, 0.6);
  cursor: default;
}
.t-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
}
.tier.on .t-name {
  color: var(--amber-soft);
}
.t-desc {
  font-size: 11px;
  color: var(--ink-3);
  line-height: 1.6;
}

.hours-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.hours-sep {
  font-size: 12px;
  color: var(--ink-3);
}
.t-input {
  font-family: var(--mono);
  font-size: 12.5px;
  color: var(--ink);
  background: var(--bg-app);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-s);
  padding: 5px 9px;
}
.t-input:focus {
  outline: none;
  border-color: var(--line-hover);
}
.t-input.num {
  width: 76px;
}
.t-input.grow {
  flex: 1 1 200px;
  min-width: 0;
}
.t-input.area {
  width: 100%;
  min-height: 96px;
  resize: vertical;
  line-height: 1.7;
}

/* 内联表单（MCP 添加/编辑、AI 配置、技能共用骨架） */
.inline-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  border: 1px dashed var(--line-2);
  border-radius: var(--radius-s);
  background: var(--bg-app);
  padding: 12px;
}
.form-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink-2);
}
.form-error {
  font-size: 12px;
  color: var(--terra-soft);
}
.form-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.form-row.foot {
  justify-content: flex-end;
}
.check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--ink-2);
  cursor: pointer;
}
.seg {
  font-size: 12px;
  color: var(--ink-3);
  border: 1px solid var(--line);
  border-radius: var(--radius-pill);
  padding: 3px 12px;
}
.seg:hover {
  border-color: var(--line-hover);
  color: var(--ink-2);
}
.seg.on {
  color: var(--amber-soft);
  border-color: var(--line-hover);
}
.seg-row {
  display: flex;
  gap: 8px;
}

.items {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.item {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--line);
  background: var(--bg-app);
  border-radius: var(--radius-s);
  padding: 8px 11px;
}
.item.stack {
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
}
.item-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.it-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.it-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.it-name.mono {
  font-family: var(--mono);
  font-size: 12.5px;
}
.it-meta {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.it-meta.err {
  color: var(--terra-soft);
}
.it-meta.wrap {
  white-space: normal;
}
.it-acts {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.badge {
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--ink-3);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-pill);
  padding: 0 8px;
  line-height: 16px;
}
.badge[data-tone='ok'] {
  color: var(--amber-soft);
  border-color: var(--amber-border-dim);
}
.badge[data-tone='error'] {
  color: var(--terra-soft);
  border-color: var(--terra-dashed);
}
.act {
  flex: none;
  font-size: 11.5px;
  color: var(--amber-soft);
  border: 1px solid var(--line-2);
  border-radius: var(--radius-s);
  padding: 3px 10px;
}
.act:hover {
  border-color: var(--line-hover);
}
.act.danger {
  color: var(--terra-soft);
}
.act.danger:hover {
  border-color: var(--terra-dashed);
}
.act:disabled {
  /* 浅色主题经 --ctl-disabled-opacity 抬到 0.75（disabled 文本 ≥3:1）；暗色走 fallback 0.5 不变 */
  opacity: var(--ctl-disabled-opacity, 0.5);
  cursor: default;
}

/* 测试连接结果与工具清单展开 */
.test-line {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--amber-soft);
  border-top: 1px dashed var(--line-2);
  padding-top: 7px;
}
.test-line.err {
  color: var(--terra-soft);
}
.tools {
  border-top: 1px dashed var(--line-2);
  padding-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.tools-note {
  font-size: 11.5px;
  color: var(--ink-3);
  display: flex;
  align-items: center;
  gap: 8px;
}
.tools-note.err {
  color: var(--terra-soft);
}
.tool-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.tool-list li {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.tool-name {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--ink);
}
.tool-desc {
  font-size: 11px;
  color: var(--ink-3);
  line-height: 1.6;
}

@media (max-width: 900px) {
  .panels {
    grid-template-columns: 1fr;
  }
}
</style>
