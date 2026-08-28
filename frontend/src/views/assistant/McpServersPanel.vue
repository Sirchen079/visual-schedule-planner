<script setup>
// MCP 服务器配置面板（自包含）：列表 / 新增 / 编辑 / 测试 / 启停 / 删除。
// 直接调用 mcp.js，状态自管；渲染在 AssistantSettings 的一个折叠分组里。
import { computed, inject, onMounted, ref } from 'vue'
import ArtIcon from '../../components/ArtIcon.vue'
import {
  listMcpServers,
  createMcpServer,
  updateMcpServer,
  deleteMcpServer,
  enableMcpServer,
  testMcpServer,
} from '../../api/mcp'

const toast = inject('toast', { success: () => {}, error: () => {}, info: () => {} })
const confirmDialog = inject('confirm-dialog', (o) => Promise.resolve(window.confirm(o.message || '')))

const servers = ref([])
const loading = ref(false)
const formOpen = ref(false)
const editingId = ref(null)
const saving = ref(false)
const testingId = ref(null)
const testResult = ref(null) // { serverId, ok, message, tools }
const jsonErrors = ref({ args: '', env: '', headers: '' })

// 批量导入 JSON（Claude Desktop / Cursor 通用 mcpServers 格式）
const importOpen = ref(false)
const importText = ref('')
const importError = ref('')
const importing = ref(false)

function blankForm() {
  return {
    name: '',
    transport: 'stdio',
    command: '',
    argsText: '[]',
    envText: '{}',
    url: '',
    headersText: '{}',
    timeout_sec: 30,
    auto_approve_readonly: false,
  }
}
const form = ref(blankForm())

const isStdio = computed(() => form.value.transport === 'stdio')
const formTitle = computed(() => (editingId.value === null ? '新增 MCP 服务器' : '编辑 MCP 服务器'))

function statusTone(s) {
  if (s === 'ok') return 'ok'
  if (s === 'error') return 'error'
  return 'unknown'
}

async function load() {
  loading.value = true
  try {
    servers.value = await listMcpServers()
  } catch (e) {
    toast.error(`加载失败：${e.message}`)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  form.value = blankForm()
  editingId.value = null
  jsonErrors.value = { args: '', env: '', headers: '' }
  formOpen.value = true
}

function openEdit(server) {
  editingId.value = server.id
  form.value = {
    name: server.name,
    transport: server.transport,
    command: server.command || '',
    argsText: JSON.stringify(server.args || [], null, 0),
    envText: JSON.stringify(server.env || {}, null, 0),
    url: server.url || '',
    headersText: JSON.stringify(server.headers || {}, null, 0),
    timeout_sec: server.timeout_sec,
    auto_approve_readonly: server.auto_approve_readonly,
  }
  jsonErrors.value = { args: '', env: '', headers: '' }
  testResult.value = null
  formOpen.value = true
}

function closeForm() {
  formOpen.value = false
  editingId.value = null
}

// 失焦校验 JSON：args 必须是数组；env/headers 必须是对象
function validateJson(field, expectArray) {
  const raw = (form.value[`${field}Text`] || '').trim()
  if (!raw) {
    form.value[`${field}Text`] = expectArray ? '[]' : '{}'
    jsonErrors.value[field] = ''
    return
  }
  try {
    const parsed = JSON.parse(raw)
    if (expectArray && !Array.isArray(parsed)) throw new Error('必须是数组')
    if (!expectArray && (parsed === null || Array.isArray(parsed) || typeof parsed !== 'object')) throw new Error('必须是对象')
    jsonErrors.value[field] = ''
  } catch (e) {
    jsonErrors.value[field] = `JSON 格式错误（${e.message}）`
  }
}

function clampTimeout(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return 30
  return Math.min(120, Math.max(5, Math.floor(n)))
}

function buildPayload() {
  const args = JSON.parse(form.value.argsText || '[]')
  const env = JSON.parse(form.value.envText || '{}')
  const headers = JSON.parse(form.value.headersText || '{}')
  return {
    name: form.value.name.trim(),
    transport: form.value.transport,
    command: isStdio.value ? form.value.command.trim() : null,
    args: isStdio.value ? args : [],
    env: isStdio.value ? env : {},
    url: !isStdio.value ? form.value.url.trim() : null,
    headers: !isStdio.value ? headers : {},
    timeout_sec: clampTimeout(form.value.timeout_sec),
    auto_approve_readonly: form.value.auto_approve_readonly,
  }
}

const canSave = computed(
  () =>
    form.value.name.trim() &&
    !Object.values(jsonErrors.value).some(Boolean) &&
    (isStdio.value ? form.value.command.trim() : form.value.url.trim())
)

async function save() {
  validateJson('args', true)
  validateJson('env', false)
  validateJson('headers', false)
  if (!canSave.value) {
    toast.error('请补全必填项并修正 JSON 格式')
    return
  }
  saving.value = true
  try {
    const payload = buildPayload()
    if (editingId.value === null) {
      await createMcpServer(payload)
      toast.success('已添加')
    } else {
      await updateMcpServer(editingId.value, payload)
      toast.success('已保存')
    }
    formOpen.value = false
    await load()
  } catch (e) {
    toast.error(`保存失败：${e.message}`)
  } finally {
    saving.value = false
  }
}

async function toggleEnabled(server) {
  try {
    await enableMcpServer(server.id, !server.enabled)
    server.enabled = !server.enabled
  } catch (e) {
    toast.error(`切换失败：${e.message}`)
  }
}

async function test(server) {
  testingId.value = server.id
  testResult.value = null
  try {
    const result = await testMcpServer(server.id)
    testResult.value = { serverId: server.id, ...result }
    await load() // 刷新 last_status
  } catch (e) {
    testResult.value = { serverId: server.id, ok: false, message: e.message, tools: [] }
  } finally {
    testingId.value = null
  }
}

async function remove(server) {
  const ok = await confirmDialog({
    title: '删除 MCP 服务器',
    message: `确定删除「${server.name}」？删除后助手将不再调用其工具。`,
    confirmText: '删除',
    danger: true,
  })
  if (!ok) return
  try {
    await deleteMcpServer(server.id)
    toast.success('已删除')
    if (testResult.value?.serverId === server.id) testResult.value = null
    await load()
  } catch (e) {
    toast.error(`删除失败：${e.message}`)
  }
}

// 把单个服务器配置归一为 create payload
function serverConfigToPayload(name, cfg) {
  const isHttp = !cfg.command && !!cfg.url
  return {
    name: String(cfg.name || name || '导入的服务器').slice(0, 100).trim() || '导入的服务器',
    transport: isHttp ? 'http' : 'stdio',
    command: isHttp ? null : String(cfg.command || '').trim(),
    args: Array.isArray(cfg.args) ? cfg.args.map(String) : [],
    env: _toStringMap(cfg.env),
    url: isHttp ? String(cfg.url || '').trim() : null,
    headers: _toStringMap(cfg.headers),
    timeout_sec: clampTimeout(cfg.timeout_sec),
    auto_approve_readonly: !!cfg.auto_approve_readonly,
    enabled: cfg.enabled !== false,
  }
}

function _toStringMap(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
  const out = {}
  for (const [k, v] of Object.entries(value)) out[String(k)] = String(v)
  return out
}

// 解析标准 mcpServers JSON → [{name, cfg}, ...]
// 支持：{"mcpServers": {...}} / 裸 {name: {...}} 映射 / 单个 {command|url, ...}
function parseMcpServersJson(raw) {
  const parsed = JSON.parse(raw)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('JSON 必须是对象')
  }
  // 单个服务器：自身带 command 或 url
  if (parsed.command || parsed.url) {
    return [{ name: parsed.name || '导入的服务器', cfg: parsed }]
  }
  const map = parsed.mcpServers && typeof parsed.mcpServers === 'object' ? parsed.mcpServers : parsed
  const entries = []
  for (const [name, cfg] of Object.entries(map || {})) {
    if (cfg && typeof cfg === 'object' && !Array.isArray(cfg)) {
      entries.push({ name, cfg })
    }
  }
  if (!entries.length) throw new Error('未识别到任何服务器配置')
  return entries
}

async function runImport() {
  importError.value = ''
  const raw = importText.value.trim()
  if (!raw) {
    importError.value = '请粘贴 MCP 配置 JSON'
    return
  }
  let entries
  try {
    entries = parseMcpServersJson(raw)
  } catch (e) {
    importError.value = `JSON 解析失败：${e.message}`
    return
  }
  importing.value = true
  let okCount = 0
  const failed = []
  for (const { name, cfg } of entries) {
    const payload = serverConfigToPayload(name, cfg)
    try {
      await createMcpServer(payload)
      okCount += 1
    } catch (e) {
      failed.push(`${name}：${e.message}`)
    }
  }
  importing.value = false
  if (okCount) {
    toast.success(`已导入 ${okCount} 个服务器${failed.length ? `，${failed.length} 个失败` : ''}`)
    importOpen.value = false
    importText.value = ''
    await load()
  } else if (failed.length) {
    importError.value = `全部失败：${failed[0]}`
  }
}

onMounted(load)
</script>

<template>
  <div class="mcp-panel">
    <div class="panel-title">
      <p class="muted">
        为助手接入 MCP（Model Context Protocol）工具服务器。启用服务器的工具会以
        <code>mcp__</code> 前缀注入对话，默认需用户确认后调用。
      </p>
      <div class="title-actions">
        <button class="ghost compact" @click="importOpen = !importOpen">
          {{ importOpen ? '收起导入' : '导入 JSON' }}
        </button>
        <button class="ghost compact" @click="openCreate">新增</button>
      </div>
    </div>

    <div v-if="importOpen" class="mcp-import card">
      <strong>粘贴 MCP 配置 JSON</strong>
      <p class="muted small">
        支持 Claude Desktop / Cursor 通用格式
        <code>{"mcpServers": {"名称": {"command": "...", "args": [...], "env": {...}}}}</code>，
        或单个服务器、裸映射；http 类型用 <code>{"url": "...", "headers": {...}}</code>。同名将更新。
      </p>
      <textarea
        v-model="importText"
        rows="6"
        class="import-input"
        spellcheck="false"
        placeholder='{"mcpServers": {"filesystem": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "D:/docs"]}}}'
      ></textarea>
      <small v-if="importError" class="err">{{ importError }}</small>
      <div class="form-foot">
        <span></span>
        <button class="primary" :disabled="importing" @click="runImport">
          {{ importing ? '导入中…' : '解析并导入' }}
        </button>
      </div>
    </div>

    <p v-if="loading" class="muted">加载中…</p>
    <p v-else-if="!servers.length" class="muted">尚未配置 MCP 服务器。</p>

    <div v-if="servers.length" class="mcp-list">
      <div v-for="s in servers" :key="s.id" class="mcp-row">
        <div class="mcp-row-main">
          <span class="status-dot" :class="statusTone(s.last_status)" :title="s.last_error || s.last_status"></span>
          <strong>{{ s.name }}</strong>
          <span class="badge" :class="s.transport">{{ s.transport === 'stdio' ? '本地命令' : '远程 HTTP' }}</span>
          <label class="switch-mini" :title="s.enabled ? '已启用' : '已停用'">
            <input type="checkbox" :checked="s.enabled" @change="toggleEnabled(s)" />
            <span>{{ s.enabled ? '启用' : '停用' }}</span>
          </label>
        </div>
        <div class="mcp-row-actions">
          <button class="ghost compact" :disabled="testingId === s.id" @click="test(s)">
            {{ testingId === s.id ? '测试中' : '测试' }}
          </button>
          <button class="ghost compact" @click="openEdit(s)">编辑</button>
          <button class="ghost compact danger" @click="remove(s)">删除</button>
        </div>

        <div v-if="testResult?.serverId === s.id" class="mcp-test-result" :class="{ ok: testResult.ok, err: !testResult.ok }">
          <template v-if="testResult.ok">
            <span>{{ testResult.message }}</span>
            <details v-if="testResult.tools?.length">
              <summary>查看 {{ testResult.tools.length }} 个工具</summary>
              <ul>
                <li v-for="t in testResult.tools" :key="t.name">
                  <code>{{ t.name }}</code>
                  <span class="muted">{{ t.description ? '：' + t.description : '' }}</span>
                </li>
              </ul>
            </details>
          </template>
          <span v-else>连接失败：{{ testResult.message }}</span>
        </div>
      </div>
    </div>

    <div v-if="formOpen" class="mcp-form card">
      <div class="form-head">
        <strong>{{ formTitle }}</strong>
        <button class="ghost compact" @click="closeForm">取消</button>
      </div>
      <div class="form-grid">
        <label>
          <span>名称</span>
          <input v-model="form.name" placeholder="如：本地文件系统" />
        </label>
        <label>
          <span>传输类型</span>
          <select v-model="form.transport">
            <option value="stdio">stdio（本地命令子进程）</option>
            <option value="http">http（远程 Streamable HTTP）</option>
          </select>
        </label>

        <template v-if="isStdio">
          <label class="full">
            <span>命令 <em class="req">*</em>（可执行文件，如 npx / uvx / python）</span>
            <input v-model="form.command" placeholder="npx" />
          </label>
          <label class="full">
            <span>参数（JSON 数组）</span>
            <textarea v-model="form.argsText" rows="2" placeholder='["-y", "@modelcontextprotocol/server-filesystem", "D:/docs"]' @blur="validateJson('args', true)"></textarea>
            <small v-if="jsonErrors.args" class="err">{{ jsonErrors.args }}</small>
          </label>
          <label class="full">
            <span>环境变量（JSON 对象，可留空；值将加密保存）</span>
            <textarea v-model="form.envText" rows="2" placeholder='{"API_TOKEN": "xxx"}' @blur="validateJson('env', false)"></textarea>
            <small v-if="jsonErrors.env" class="err">{{ jsonErrors.env }}</small>
          </label>
        </template>

        <template v-else>
          <label class="full">
            <span>URL <em class="req">*</em>（仅 http(s)://）</span>
            <input v-model="form.url" placeholder="https://mcp.example.com/mcp" />
          </label>
          <label class="full">
            <span>请求头（JSON 对象，可留空；值将加密保存）</span>
            <textarea v-model="form.headersText" rows="2" placeholder='{"Authorization": "Bearer xxx"}' @blur="validateJson('headers', false)"></textarea>
            <small v-if="jsonErrors.headers" class="err">{{ jsonErrors.headers }}</small>
          </label>
        </template>

        <label>
          <span>超时（秒，5–120）</span>
          <input v-model.number="form.timeout_sec" type="number" min="5" max="120" />
        </label>
        <label class="switch-field">
          <input type="checkbox" v-model="form.auto_approve_readonly" />
          <span>只读工具免确认（仅对带只读标记的工具生效）</span>
        </label>
      </div>
      <div class="form-foot">
        <p class="muted small">
          stdio 服务器需本机已安装对应命令（npx 需 Node、uvx 需 uv）。示例可参考
          <a href="https://github.com/modelcontextprotocol/servers" target="_blank" rel="noopener">MCP 官方服务器列表</a>。
        </p>
        <button class="primary" :disabled="!canSave || saving" @click="save">
          {{ saving ? '保存中' : '保存' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mcp-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.title-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}
.mcp-import {
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  border: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.mcp-import p { margin: 0; line-height: 1.6; }
.import-input {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12.5px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  resize: vertical;
}
.panel-title p {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.6;
}
code {
  font-family: inherit;
  background: var(--surface-3);
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 12px;
}
.mcp-list {
  display: grid;
  gap: 8px;
}
.mcp-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  border: 1px solid var(--border);
}
.mcp-row-main {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1 1 200px;
  min-width: 0;
}
.mcp-row-actions {
  display: flex;
  gap: 6px;
}
.status-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--surface-3);
  border: 1px solid var(--border);
}
.status-dot.ok { background: #3fb950; border-color: #3fb950; }
.status-dot.error { background: #f85149; border-color: #f85149; }
.badge {
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 10px;
  background: var(--surface-3);
  color: var(--text-soft);
  border: 1px solid var(--border);
}
.switch-mini {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--text-soft);
  cursor: pointer;
}
.mcp-test-result {
  width: 100%;
  font-size: 12.5px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
}
.mcp-test-result.ok { background: color-mix(in srgb, #3fb950 12%, var(--surface-2)); }
.mcp-test-result.err { background: color-mix(in srgb, #f85149 12%, var(--surface-2)); }
.mcp-test-result ul { margin: 6px 0 0; padding-left: 18px; }
.mcp-test-result li { margin: 2px 0; }
.mcp-form {
  padding: 14px;
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  border: 1px solid var(--border);
}
.form-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}
.form-grid label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12.5px;
}
.form-grid label.full { grid-column: 1 / -1; }
.form-grid label span { color: var(--text-soft); }
.req { color: #f85149; font-style: normal; }
.form-grid input,
.form-grid select,
.form-grid textarea {
  font-family: inherit;
  font-size: 13px;
  padding: 7px 9px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
}
.form-grid textarea { resize: vertical; }
.switch-field {
  flex-direction: row !important;
  align-items: center;
  gap: 7px !important;
}
.err { color: #f85149; }
.form-foot {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
}
.form-foot p { margin: 0; max-width: 48ch; }
.small { font-size: 11.5px; }
.primary {
  padding: 8px 18px;
  font-weight: 700;
  border-radius: var(--radius-sm);
  border: 1px solid var(--accent);
  background: var(--accent);
  color: #fff;
  cursor: pointer;
}
.primary:disabled { opacity: 0.5; cursor: not-allowed; }
button.danger { color: #f85149; }
@media (max-width: 560px) {
  .form-grid { grid-template-columns: 1fr; }
}
</style>
