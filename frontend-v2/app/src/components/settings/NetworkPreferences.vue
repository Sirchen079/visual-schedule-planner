<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { listMcpServers, listMcpTools, type MCPServerInfo, type McpToolInfo } from '../../api/settings'
import {
  defaultFetchBinding, defaultSearchBinding, getVision, getWebServices, mcpServerIssue,
  mcpToolIssue, parseVisionArguments, removeTavilyKey, saveTavilyKey, saveVision,
  saveWebServices, type VisionConfig, type WebProvider, type WebServicesConfig,
} from '../../api/networkServices'

type Lane = 'search' | 'fetch' | 'vision'
const lanes: { key: Lane; title: string; description: string; number: string }[] = [
  { key: 'search', title: '联网搜索', description: '查找网页与来源，返回标题、链接和摘要。', number: '01' },
  { key: 'fetch', title: '网页读取', description: '读取指定链接的正文，可与搜索使用不同服务。', number: '02' },
  { key: 'vision', title: '视觉 MCP 补充', description: '当前模型或传输不支持图片时，先将图片交给指定工具，再把识别文字交给模型。', number: '03' },
]
const web = ref<WebServicesConfig | null>(null), vision = ref<VisionConfig | null>(null)
const search = ref(defaultSearchBinding()), reader = ref(defaultFetchBinding())
const visionText = ref(''), keyInput = ref(''), hasKey = ref(false)
const loading = reactive({ web: true, vision: true, servers: false })
const busy = reactive({ web: false, vision: false, key: false })
const errors = reactive({ web: '', vision: '', servers: '', key: '' })
const saved = reactive({ web: '', vision: '', key: '' })
const servers = ref<MCPServerInfo[]>([])
const tools = reactive<Record<number, McpToolInfo[]>>({})
const toolBusy = reactive<Record<number, boolean>>({})
const toolErrors = reactive<Record<number, string>>({})
const anyBusy = computed(() => busy.web || busy.vision || busy.key)
const tavilySelected = computed(() => web.value?.search_provider === 'tavily' || web.value?.fetch_provider === 'tavily')
const message = (e: unknown, fallback: string) => e instanceof Error ? e.message : fallback
function binding(lane: Lane) { return lane === 'search' ? search.value : lane === 'fetch' ? reader.value : vision.value! }
function usesMcp(lane: Lane) { return lane === 'vision' ? !!vision.value?.enabled : provider(lane) === 'mcp' }
function provider(lane: Lane): WebProvider { return lane === 'search' ? web.value!.search_provider : web.value!.fetch_provider }
function touch(lane: Lane) { saved[lane === 'vision' ? 'vision' : 'web'] = '' }
function setProvider(lane: Lane, event: Event) {
  const value = (event.target as HTMLSelectElement).value as WebProvider
  if (lane === 'search') web.value!.search_provider = value
  else web.value!.fetch_provider = value
  touch(lane)
  if (value === 'mcp') void loadTools(binding(lane).server_id)
}
function selectedServer(lane: Lane) { return servers.value.find(s => s.id === binding(lane).server_id) }
function selectedTool(lane: Lane) { return tools[binding(lane).server_id ?? 0]?.find(t => t.name === binding(lane).tool_name) }
function schemaText(lane: Lane) { return JSON.stringify(selectedTool(lane)?.input_schema ?? {}, null, 2) }
function changeServer(lane: Lane, event: Event) {
  const value = Number((event.target as HTMLSelectElement).value)
  binding(lane).server_id = value || (lane === 'vision' ? null : 0)
  binding(lane).tool_name = ''
  touch(lane)
  void loadTools(value)
}
async function loadTools(id: number | null, force = false) {
  if (!id || toolBusy[id] || (!force && tools[id])) return
  const issue = mcpServerIssue(servers.value.find(s => s.id === id))
  if (issue) { toolErrors[id] = issue; return }
  toolBusy[id] = true; toolErrors[id] = ''; delete tools[id]
  try { tools[id] = await listMcpTools(id) }
  catch { toolErrors[id] = '工具清单加载失败，请检查服务器连接后重试。' }
  finally { toolBusy[id] = false }
}
async function loadServers() {
  if (loading.servers) return
  loading.servers = true; errors.servers = ''
  try {
    servers.value = await listMcpServers()
    for (const id of Object.keys(tools)) delete tools[Number(id)]
    await Promise.all(lanes.filter(l => (l.key === 'vision' ? vision.value : web.value) && usesMcp(l.key)).map(l => loadTools(binding(l.key).server_id)))
  } catch { errors.servers = 'MCP 服务器清单读取失败；内置服务和 Tavily 仍可独立设置。' }
  finally { loading.servers = false }
}
async function loadWeb() {
  loading.web = true; errors.web = ''
  try {
    const data = await getWebServices()
    web.value = data.config; hasKey.value = data.tavily_has_api_key
    search.value = data.config.mcp_search ? { ...data.config.mcp_search } : defaultSearchBinding()
    reader.value = data.config.mcp_fetch ? { ...data.config.mcp_fetch } : defaultFetchBinding()
  } catch (e) { errors.web = message(e, '网络设置读取失败') }
  finally { loading.web = false }
}
async function loadVision() {
  loading.vision = true; errors.vision = ''
  try { vision.value = await getVision(); visionText.value = JSON.stringify(vision.value.arguments, null, 2) }
  catch (e) { errors.vision = message(e, '视觉设置读取失败') }
  finally { loading.vision = false }
}
function assertBinding(lane: Lane, args: Record<string, unknown>) {
  const issue = mcpServerIssue(selectedServer(lane)) || mcpToolIssue(selectedTool(lane), args)
  if (issue) throw new Error(`${lanes.find(l => l.key === lane)!.title}：${issue}`)
}
async function saveWeb() {
  if (!web.value || anyBusy.value) return
  busy.web = true; errors.web = ''; saved.web = ''
  try {
    if (tavilySelected.value && !hasKey.value) throw new Error('请先保存 Tavily API Key，或选择无需密钥的内置服务')
    const config: WebServicesConfig = { ...web.value }
    if (usesMcp('search')) {
      const b = { ...search.value, limit_argument: search.value.limit_argument?.trim() || null }
      assertBinding('search', { [b.query_argument]: '', ...(b.limit_argument ? { [b.limit_argument]: 5 } : {}) })
      config.mcp_search = b
    }
    if (usesMcp('fetch')) { assertBinding('fetch', { [reader.value.url_argument]: reader.value.url_as_list ? [''] : '' }); config.mcp_fetch = { ...reader.value } }
    web.value = (await saveWebServices(config)).config
    saved.web = '搜索与网页读取设置已保存'
  } catch (e) { errors.web = message(e, '网络设置保存失败，请重试') }
  finally { busy.web = false }
}
async function saveVisionConfig() {
  if (!vision.value || anyBusy.value) return
  busy.vision = true; errors.vision = ''; saved.vision = ''
  try {
    // Disabling must remain possible after the selected server is removed.
    const config: VisionConfig = vision.value.enabled
      ? { ...vision.value, arguments: parseVisionArguments(visionText.value, selectedServer('vision'), true) }
      : { enabled: false, server_id: null, tool_name: '', arguments: { image: '{{image_data_url}}', prompt: '{{prompt}}' } }
    if (config.enabled) assertBinding('vision', config.arguments)
    vision.value = await saveVision(config)
    visionText.value = JSON.stringify(vision.value.arguments, null, 2)
    saved.vision = config.enabled ? '视觉补充已启用；后续符合条件的图片会发送至所选服务' : '视觉补充已关闭'
  } catch (e) { errors.vision = message(e, '视觉设置保存失败，请重试') }
  finally { busy.vision = false }
}
async function updateKey(remove = false) {
  if (anyBusy.value) return
  busy.key = true; errors.key = ''; saved.key = ''
  try {
    const result = remove ? await removeTavilyKey() : await saveTavilyKey(keyInput.value)
    if (result) { hasKey.value = result.tavily_has_api_key; keyInput.value = '' }
    saved.key = remove ? 'Tavily 密钥已移除' : result ? 'Tavily 密钥已保存' : '已保留现有密钥'
  } catch { errors.key = '密钥操作失败，请检查本地凭据存储后重试。' }
  finally { busy.key = false }
}
onMounted(async () => { await Promise.all([loadWeb(), loadVision()]); await loadServers() })
</script>

<template>
  <div id="network-preferences-root" class="network-preferences" aria-label="联网与图片理解设置">
    <header class="network-heading"><div><h2>联网与图片理解</h2><p>按用途选择服务，让知时搜索网页、读取正文与理解图片。</p></div><span class="badge">内置服务免密钥</span></header>
    <p v-if="loading.web || loading.vision" class="notice" role="status">正在读取服务设置…</p>
    <div v-if="errors.web && !web" class="error" role="alert">{{ errors.web }} <button type="button" @click="loadWeb">重新读取</button></div>
    <div v-if="errors.vision && !vision" class="error" role="alert">{{ errors.vision }} <button type="button" @click="loadVision">重新读取</button></div>

    <template v-for="lane in lanes" :key="lane.key">
      <section v-if="lane.key === 'vision' ? vision : web" class="service-card" :aria-labelledby="`network-${lane.key}-title`">
        <header class="card-heading"><span class="number">{{ lane.number }}</span><div><h3 :id="`network-${lane.key}-title`">{{ lane.title }}</h3><p>{{ lane.description }}</p></div></header>
        <fieldset :disabled="anyBusy" @input="touch(lane.key)" @change="touch(lane.key)">
          <label v-if="lane.key !== 'vision'" class="field">服务来源
            <select :id="`network-${lane.key}-provider`" :aria-label="`${lane.title}服务来源`" :value="provider(lane.key)" @change="setProvider(lane.key, $event)">
              <option value="builtin">内置 · 无需 API Key</option><option value="tavily">Tavily</option><option value="mcp">MCP 工具</option>
            </select>
          </label>
          <label v-else class="consent"><input id="network-vision-enabled" v-model="vision!.enabled" type="checkbox" aria-label="启用视觉补充并允许发送图片" @change="vision!.enabled && loadTools(vision!.server_id)"><span><strong>启用视觉补充并允许发送图片</strong><small>开启并保存后，本地上传文件中的图片数据、文件名和提问会发送到所选 MCP 服务；本地路径模板还会让受信任的本地工具读取该文件。请确认你信任此服务。</small></span></label>
          <p v-if="lane.key !== 'vision' && provider(lane.key) === 'builtin'" class="hint">{{ lane.key === 'search' ? '使用内置联网搜索，无需配置密钥。' : '使用内置网页正文提取，无需配置密钥。' }}</p>
          <label v-if="lane.key !== 'vision' && provider(lane.key) === 'tavily'" class="field depth">处理深度
            <select v-if="lane.key === 'search'" v-model="web!.tavily_search_depth" aria-label="Tavily 搜索深度"><option value="basic">标准搜索（basic）</option><option value="advanced">深入搜索（advanced）</option></select>
            <select v-else v-model="web!.tavily_extract_depth" aria-label="Tavily 网页读取深度"><option value="basic">标准提取（basic）</option><option value="advanced">深入提取（advanced）</option></select>
            <small>使用下方单独保存的 Tavily 密钥。</small>
          </label>
          <div v-if="usesMcp(lane.key)" class="mcp-binding">
            <div class="fields">
              <label class="field">MCP 服务器
                <select :id="`network-${lane.key}-server`" :aria-label="`${lane.title} MCP 服务器`" :value="binding(lane.key).server_id || 0" :disabled="loading.servers" @change="changeServer(lane.key, $event)">
                  <option :value="0">选择已配置的服务器</option>
                  <option v-if="binding(lane.key).server_id && !selectedServer(lane.key)" :value="binding(lane.key).server_id">原服务器已不可用（{{ binding(lane.key).server_id }}）</option>
                  <option v-for="server in servers" :key="server.id" :value="server.id" :disabled="!!mcpServerIssue(server)">{{ server.name }}{{ mcpServerIssue(server) ? ` · ${mcpServerIssue(server)}` : '' }}</option>
                </select>
              </label>
              <label class="field">只读工具
                <select :id="`network-${lane.key}-tool`" :aria-label="`${lane.title}只读工具`" v-model="binding(lane.key).tool_name" :disabled="!!mcpServerIssue(selectedServer(lane.key)) || !!toolBusy[binding(lane.key).server_id || 0]">
                  <option value="">选择工具</option>
                  <option v-if="binding(lane.key).tool_name && !selectedTool(lane.key)" :value="binding(lane.key).tool_name">{{ binding(lane.key).tool_name }} · 尚未验证</option>
                  <option v-for="tool in tools[binding(lane.key).server_id || 0] || []" :key="tool.name" :value="tool.name" :disabled="!tool.read_only">{{ tool.name }}{{ !tool.read_only ? ' · 非只读，不可选' : '' }}</option>
                </select>
              </label>
            </div>
            <div class="tool-actions"><button type="button" :disabled="!!mcpServerIssue(selectedServer(lane.key)) || !!toolBusy[binding(lane.key).server_id || 0]" @click="loadTools(binding(lane.key).server_id, true)">{{ toolBusy[binding(lane.key).server_id || 0] ? '正在加载工具…' : '重新加载工具' }}</button><span v-if="tools[binding(lane.key).server_id || 0]?.length === 0">服务器未返回可用工具</span></div>
            <p v-if="mcpServerIssue(selectedServer(lane.key))" class="hint">{{ mcpServerIssue(selectedServer(lane.key)) }}。请先在 MCP 管理中启用服务器、允许自动执行只读工具；stdio 还需标记为受信任。</p>
            <p v-if="toolErrors[binding(lane.key).server_id || 0]" class="error" role="alert">{{ toolErrors[binding(lane.key).server_id || 0] }}</p>
            <p v-if="selectedTool(lane.key)?.description" class="hint tool-description">{{ selectedTool(lane.key)?.description }}</p>
            <details class="advanced">
              <summary>高级：参数兼容与结果映射</summary>
              <p class="hint">先查看所选工具需要的参数，再调整对应字段；保存网页 MCP 设置会校验工具清单，不会执行搜索、读取网页或发送图片。</p>
              <template v-if="lane.key === 'search'">
                <div class="fields"><label class="field">搜索词参数名<input v-model="search.query_argument" placeholder="query"></label><label class="field">结果数量参数名（可留空）<input v-model="search.limit_argument" placeholder="max_results"></label><label class="field">结果列表路径<input v-model="search.results_path" placeholder="results；留空为整体结果"></label><label class="field">标题字段<input v-model="search.title_field" placeholder="title"></label><label class="field">链接字段<input v-model="search.url_field" placeholder="url"></label><label class="field">摘要字段<input v-model="search.description_field" placeholder="content"></label></div>
                <p class="hint">例如工具接收 query 与 max_results，返回 results 数组。若不支持数量参数，请留空。仅支持搜索词和数量映射，不能添加其他必填参数。</p>
              </template>
              <template v-else-if="lane.key === 'fetch'">
                <div class="fields"><label class="field">网页地址参数名<input v-model="reader.url_argument" placeholder="url"></label><label class="field">正文结果路径<input v-model="reader.content_path" placeholder="留空为整体文本"></label></div>
                <label class="check"><input v-model="reader.url_as_list" type="checkbox">以数组发送地址（如 urls: [地址]）</label>
                <p class="hint">例如 Tavily MCP Extract：地址参数填 urls，勾选数组，正文路径填 results.0.raw_content。路径以点分隔，最多 8 层。</p>
              </template>
              <template v-else>
                <label class="field">视觉参数模板（JSON）<textarea id="network-vision-arguments" v-model="visionText" rows="8" spellcheck="false" aria-label="视觉参数模板 JSON"></textarea></label>
                <p class="hint" v-pre>将参数名改为工具实际要求的名称。支持 {{image_data_url}}、{{prompt}}、{{filename}}、{{mime_type}}；{{image_path}} 仅可用于受信任的本地 stdio 服务。凭据请配置在 MCP 服务器中。</p>
              </template>
              <details v-if="selectedTool(lane.key)" class="schema"><summary>查看工具输入格式</summary><pre>{{ schemaText(lane.key) }}</pre></details>
            </details>
          </div>
          <p v-if="lane.key === 'vision' && !vision!.enabled" class="hint">已关闭。支持图片的模型仍按能力配置直接接收图片；否则会明确提示图片未读取。音频、视频不使用此视觉补充。</p>
        </fieldset>
        <p v-if="lane.key === 'fetch' && errors.web" class="error" role="alert">{{ errors.web }}</p>
        <p v-if="lane.key === 'vision' && errors.vision" class="error" role="alert">{{ errors.vision }}</p>
        <footer v-if="lane.key === 'fetch'" class="save-row"><button id="network-web-save" class="primary" type="button" :disabled="anyBusy" @click="saveWeb">{{ busy.web ? '正在保存…' : '保存搜索与读取设置' }}</button><span class="success" role="status">{{ saved.web }}</span></footer>
        <footer v-if="lane.key === 'vision'" class="save-row"><button id="network-vision-save" class="primary" type="button" :disabled="anyBusy" @click="saveVisionConfig">{{ busy.vision ? '正在保存…' : '保存视觉设置' }}</button><span class="success" role="status">{{ saved.vision }}</span></footer>
      </section>
    </template>

    <section v-if="web" class="credentials" aria-labelledby="network-key-title">
      <header class="card-heading"><div><h3 id="network-key-title">Tavily API Key</h3><p>搜索和网页读取共用。密钥保存在本地凭据存储，留空保留原值。</p></div><span class="badge" :class="{ ready: hasKey }">{{ hasKey ? '已配置' : '未配置' }}</span></header>
      <label class="field">{{ hasKey ? '更换密钥' : '添加密钥' }}<input id="network-tavily-key" v-model="keyInput" aria-label="Tavily API Key" type="password" autocomplete="new-password" spellcheck="false" maxlength="4096" :disabled="anyBusy" :placeholder="hasKey ? '留空保留已保存的密钥' : '输入 Tavily API Key'" @input="saved.key = ''"></label>
      <div class="save-row"><button type="button" :disabled="anyBusy" @click="updateKey()">{{ busy.key ? '正在处理…' : '保存密钥' }}</button><button v-if="hasKey" type="button" class="remove" :disabled="anyBusy" @click="updateKey(true)">移除密钥</button><span role="status" class="success">{{ saved.key }}</span></div>
      <p v-if="tavilySelected && !hasKey" class="hint">已选择 Tavily，请先保存密钥；也可切回内置服务直接使用。</p>
      <p v-if="errors.key" class="error" role="alert">{{ errors.key }}</p>
    </section>
    <div class="mcp-footer"><p>MCP 服务器需提前在 MCP 管理中配置。更改后可在此刷新清单。</p><button type="button" :disabled="loading.servers || anyBusy" @click="loadServers">{{ loading.servers ? '正在刷新…' : '刷新 MCP 服务器' }}</button></div>
    <p v-if="errors.servers" class="error" role="alert">{{ errors.servers }}</p>
  </div>
</template>

<style scoped>
.network-preferences { min-width:0; color:var(--ink); }
.network-heading,.card-heading { display:flex; align-items:flex-start; gap:12px; justify-content:space-between; }
.network-heading { margin-bottom:18px; }
h2 { font-size:16px; margin:0; } h3 { font-size:14px; margin:0; }
p { margin:5px 0 0; color:var(--ink-3); font-size:12px; line-height:1.7; overflow-wrap:anywhere; }
.badge { flex-shrink:0; color:var(--ink-2); border:1px solid var(--line-2); background:var(--bg-sink); border-radius:var(--radius-pill); padding:4px 9px; font-size:11px; }
.badge.ready,.success { color:var(--ok); }
.service-card,.credentials { min-width:0; border:1px solid var(--line); border-radius:var(--radius-m); background:var(--bg-raise); padding:18px; margin-top:12px; }
.card-heading { justify-content:flex-start; margin-bottom:15px; }.card-heading>div { flex:1; min-width:0; }
.number { color:var(--amber); font-family:var(--mono); font-size:12px; padding-top:2px; }
fieldset { min-width:0; border:0; padding:0; margin:0; }
.fields { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
.field { display:flex; flex-direction:column; gap:7px; font-size:12px; color:var(--ink-2); min-width:0; }
input:not([type=checkbox]),select,textarea { box-sizing:border-box; width:100%; min-width:0; border:1px solid var(--line-2); border-radius:var(--radius-s); background:var(--bg-sink); color:var(--ink); padding:9px 10px; font:inherit; line-height:1.5; }
select { text-overflow:ellipsis; } textarea { resize:vertical; font-family:var(--mono); font-size:12px; }
input::placeholder { color:var(--ink-faint); } input[type=checkbox] { accent-color:var(--amber); flex-shrink:0; width:16px; height:16px; margin:2px 0 0; }
.mcp-binding,.depth { margin-top:14px; }.hint { margin-top:10px; }.consent,.check { display:flex; align-items:flex-start; gap:9px; font-size:12px; line-height:1.6; }
.consent { background:var(--amber-wash); border:1px solid var(--amber-border-weak); border-radius:var(--radius-s); padding:12px; }
.consent strong { font-size:13px; font-weight:600; }.consent small { display:block; color:var(--ink-2); margin-top:5px; font-size:12px; }.check { margin-top:12px; }
.advanced { margin-top:14px; padding-top:12px; border-top:1px solid var(--line); } summary { cursor:pointer; color:var(--ink-2); font-size:12px; line-height:1.6; }
.advanced .fields,.advanced>.field { margin-top:12px; }.schema { margin-top:12px; } pre { max-height:230px; overflow:auto; white-space:pre-wrap; overflow-wrap:anywhere; font-family:var(--mono); font-size:11px; color:var(--ink-3); background:var(--bg-sink); padding:10px; border-radius:var(--radius-s); }
.tool-actions,.save-row { display:flex; align-items:center; flex-wrap:wrap; gap:10px; margin-top:14px; font-size:12px; }.save-row { padding-top:12px; }.service-card>.save-row { border-top:1px solid var(--line); }
button { border:1px solid var(--line-2); border-radius:var(--radius-s); padding:8px 11px; color:var(--ink-2); background:var(--bg-sink); font-size:12px; line-height:1.5; cursor:pointer; }
button.primary { color:var(--btn-new-text); background:var(--btn-new-bg); border-color:transparent; } button:hover:not(:disabled) { border-color:var(--line-hover); }.primary:hover:not(:disabled) { background:var(--btn-new-bg-hover); }
button:disabled,fieldset:disabled { opacity:.6; } button:disabled { cursor:default; }
button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible,summary:focus-visible { outline:2px solid var(--amber); outline-offset:3px; }
.remove,.error { color:var(--terra-soft); }.error { margin:12px 0; font-size:12px; line-height:1.7; overflow-wrap:anywhere; }.error button { margin-left:6px; }.notice { margin-bottom:12px; }.tool-actions>span { color:var(--ink-3); }
.mcp-footer { display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin-top:14px; }.mcp-footer p { flex:1; min-width:180px; }.success { overflow-wrap:anywhere; }
@media(max-width:600px) { .network-heading { flex-direction:column; gap:9px; }.service-card,.credentials { padding:14px; }.fields { grid-template-columns:minmax(0,1fr); }.save-row { align-items:flex-start; }.success { flex-basis:100%; } }
</style>
