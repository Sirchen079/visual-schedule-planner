<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  confirmAiAction,
  createAiConfig,
  createAiSkill,
  enableAiConfig,
  enableAiSkill,
  executeAiAction,
  importAiSkill,
  listAiConfigs,
  listAiModels,
  listAiSkills,
  sendAiChat,
  testAiConfig,
  updateAiConfig,
  updateAiSkill,
} from '../api/ai'

const emit = defineEmits(['changed'])

const configs = ref([])
const skills = ref([])
const activeConfig = ref(null)
const activeSkillId = ref(null)
const configForm = ref(defaultConfig())
const skillForm = ref(defaultSkill())
const selectedSkillId = ref(null)
const messages = ref([])
const input = ref('')
const conversationId = ref(null)
const busy = ref(false)
const loading = ref(false)
const error = ref('')
const notice = ref('')
const pendingTokens = ref({})
const modelOptions = ref([])
const modelLoading = ref(false)
const fileInput = ref(null)
const shellRef = ref(null)
const messagesRef = ref(null)
const open = ref(false)
const assistantMode = ref('chat')
const fullscreen = ref(false)
const windowPosition = ref(loadWindowPosition())
const dragState = ref(null)
const previousFocus = ref(null)
const chatAbortController = ref(null)

const assistantName = computed(
  () => activeConfig.value?.assistant_name || configForm.value.assistant_name || '知时助手'
)
const hasConfig = computed(() => Boolean(activeConfig.value))
const canSaveConfig = computed(() => {
  const f = configForm.value
  return f.name.trim() && f.assistant_name.trim() && f.provider && f.model.trim() && (f.api_key.trim() || activeConfig.value)
})
const canSaveSkill = computed(() => skillForm.value.name.trim() && skillForm.value.content.trim())
const visibleMessages = computed(() =>
  messages.value.filter((message) => {
    const hasText = Boolean(message.content?.trim())
    const hasTools = Boolean(message.tool_results?.length)
    const hasActions = Boolean(message.pending_actions?.length)
    return hasText || hasTools || hasActions
  })
)
const shellStyle = computed(() => {
  if (fullscreen.value || !windowPosition.value) return {}
  return {
    left: `${windowPosition.value.x}px`,
    top: `${windowPosition.value.y}px`,
    right: 'auto',
    bottom: 'auto',
  }
})

function parseMessageBlocks(content) {
  const lines = String(content || '').split(/\r?\n/)
  const blocks = []
  let paragraph = []
  let list = []

  const flushParagraph = () => {
    if (!paragraph.length) return
    blocks.push({ type: 'paragraph', lines: paragraph })
    paragraph = []
  }
  const flushList = () => {
    if (!list.length) return
    blocks.push({ type: 'list', items: list })
    list = []
  }

  for (const rawLine of lines) {
    const line = rawLine.trim()
    const item = line.match(/^[-*]\s+(.+)$/)
    if (!line) {
      flushParagraph()
      flushList()
    } else if (item) {
      flushParagraph()
      list.push(item[1])
    } else {
      flushList()
      paragraph.push(line)
    }
  }

  flushParagraph()
  flushList()
  return blocks
}

function createMessage(message) {
  return {
    ...message,
    blocks: message.content?.trim() ? parseMessageBlocks(message.content) : [],
  }
}

function defaultConfig() {
  return {
    name: '默认配置',
    assistant_name: '知时助手',
    persona: '',
    provider: 'openai_chat',
    model: '',
    api_key: '',
    base_url: '',
    full_url: '',
    proxy_url: '',
    extra_headers_text: '{}',
  }
}

function defaultSkill() {
  return { name: '', description: '', content: '' }
}

function configToForm(config) {
  return {
    name: config.name || '默认配置',
    assistant_name: config.assistant_name || '知时助手',
    persona: config.persona || '',
    provider: config.provider || 'openai_chat',
    model: config.model || '',
    api_key: '',
    base_url: config.base_url || '',
    full_url: config.full_url || '',
    proxy_url: config.proxy_url || '',
    extra_headers_text: JSON.stringify(config.extra_headers || {}, null, 2),
  }
}

function parseHeaders() {
  const raw = configForm.value.extra_headers_text.trim()
  if (!raw) return {}
  const parsed = JSON.parse(raw)
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
    throw new Error('额外请求头必须是 JSON 对象')
  }
  return parsed
}

function configPayload({ includeConfigId = false } = {}) {
  const payload = {
    name: configForm.value.name.trim(),
    assistant_name: configForm.value.assistant_name.trim() || '知时助手',
    persona: configForm.value.persona.trim(),
    provider: configForm.value.provider,
    model: configForm.value.model.trim(),
    base_url: configForm.value.base_url.trim() || null,
    full_url: configForm.value.full_url.trim() || null,
    proxy_url: configForm.value.proxy_url.trim() || null,
    extra_headers: parseHeaders(),
    active_skill_id: activeSkillId.value || null,
  }
  if (configForm.value.api_key.trim()) payload.api_key = configForm.value.api_key.trim()
  if (includeConfigId && activeConfig.value) payload.config_id = activeConfig.value.id
  return payload
}

function apiMessage(err) {
  return err?.message || '操作失败'
}

function pendingStatusText(action) {
  if (action.status === 'pending') return '等待确认'
  if (action.status === 'confirmed') return '已一次确认'
  if (action.status === 'executed') return '已执行'
  if (action.status === 'expired') return '已过期'
  return action.status || '待处理'
}

function loadWindowPosition() {
  try {
    const raw = localStorage.getItem('assistant-window-position')
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (Number.isFinite(parsed?.x) && Number.isFinite(parsed?.y)) {
      return clampWindowPosition(parsed.x, parsed.y, parsed.width, parsed.height)
    }
  } catch {
    return null
  }
  return null
}

function saveWindowPosition(position) {
  localStorage.setItem('assistant-window-position', JSON.stringify(position))
}

function clampWindowPosition(x, y, width, height) {
  if (typeof window === 'undefined') return { x, y, width, height }
  const margin = 12
  const safeWidth = width || 360
  const safeHeight = height || 420
  return {
    x: Math.min(Math.max(margin, x), Math.max(margin, window.innerWidth - safeWidth - margin)),
    y: Math.min(Math.max(margin, y), Math.max(margin, window.innerHeight - safeHeight - margin)),
    width: safeWidth,
    height: safeHeight,
  }
}

function startDrag(event) {
  if (fullscreen.value || event.button !== 0) return
  if (event.target.closest('button, input, textarea, select, a, summary')) return
  const shell = shellRef.value
  if (!shell) return
  const rect = shell.getBoundingClientRect()
  const start = windowPosition.value || {
    x: rect.left,
    y: rect.top,
    width: rect.width,
    height: rect.height,
  }
  dragState.value = {
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    originX: start.x,
    originY: start.y,
    width: rect.width,
    height: rect.height,
  }
  windowPosition.value = clampWindowPosition(start.x, start.y, rect.width, rect.height)
  shell.setPointerCapture?.(event.pointerId)
}

function dragWindow(event) {
  const drag = dragState.value
  if (!drag || drag.pointerId !== event.pointerId) return
  const next = clampWindowPosition(
    drag.originX + event.clientX - drag.startX,
    drag.originY + event.clientY - drag.startY,
    drag.width,
    drag.height
  )
  windowPosition.value = next
}

function endDrag(event) {
  const drag = dragState.value
  if (!drag || drag.pointerId !== event.pointerId) return
  dragState.value = null
  shellRef.value?.releasePointerCapture?.(event.pointerId)
  if (windowPosition.value) saveWindowPosition(windowPosition.value)
}

function updatePendingAction(actionId, patch) {
  messages.value = messages.value.map((message) => {
    if (!message.pending_actions?.length) return message
    return {
      ...message,
      pending_actions: message.pending_actions.map((action) =>
        action.id === actionId ? { ...action, ...patch } : action
      ),
    }
  })
}

function keepWindowInView() {
  if (!windowPosition.value || fullscreen.value) return
  windowPosition.value = clampWindowPosition(
    windowPosition.value.x,
    windowPosition.value.y,
    windowPosition.value.width,
    windowPosition.value.height
  )
  saveWindowPosition(windowPosition.value)
}

function openAssistant() {
  previousFocus.value = document.activeElement instanceof HTMLElement ? document.activeElement : null
  open.value = true
  assistantMode.value = 'chat'
  fullscreen.value = window.matchMedia?.('(max-width: 640px)')?.matches || false
  nextTick(() => {
    shellRef.value?.focus?.()
    scrollMessagesToBottom()
  })
}

function closeAssistant() {
  chatAbortController.value?.abort()
  open.value = false
  dragState.value = null
  previousFocus.value?.focus?.()
  previousFocus.value = null
}

function toggleFullscreen() {
  fullscreen.value = !fullscreen.value
  dragState.value = null
}

async function scrollMessagesToBottom() {
  await nextTick()
  const el = messagesRef.value
  if (el) el.scrollTop = el.scrollHeight
}

function focusableElements() {
  const shell = shellRef.value
  if (!shell) return []
  return [...shell.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')].filter(
    (el) => !el.disabled && !el.hidden && el.getClientRects().length > 0
  )
}

function trapFocus(event) {
  if (!open.value || !fullscreen.value) return
  const items = focusableElements()
  if (!items.length) {
    event.preventDefault()
    shellRef.value?.focus?.()
    return
  }
  const first = items[0]
  const last = items[items.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [configRows, skillRows] = await Promise.all([listAiConfigs(), listAiSkills()])
    configs.value = configRows
    skills.value = skillRows
    activeConfig.value = configs.value.find((c) => c.enabled) || configs.value[0] || null
    activeSkillId.value = activeConfig.value?.active_skill_id || skills.value.find((s) => s.enabled)?.id || null
    if (activeConfig.value) configForm.value = configToForm(activeConfig.value)
    if (!selectedSkillId.value && skills.value.length) {
      selectSkill(skills.value.find((s) => s.id === activeSkillId.value) || skills.value[0])
    }
  } catch (err) {
    error.value = apiMessage(err)
  } finally {
    loading.value = false
  }
}

function selectConfig(config) {
  activeConfig.value = config
  configForm.value = configToForm(config)
  modelOptions.value = []
}

function newConfig() {
  activeConfig.value = null
  configForm.value = defaultConfig()
  modelOptions.value = []
}

function selectSkill(skill) {
  selectedSkillId.value = skill.id
  skillForm.value = {
    name: skill.name || '',
    description: skill.description || '',
    content: skill.content || '',
  }
}

function newSkill() {
  selectedSkillId.value = null
  skillForm.value = defaultSkill()
}

async function saveConfig() {
  if (!canSaveConfig.value || busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const payload = configPayload()
    const saved = activeConfig.value
      ? await updateAiConfig(activeConfig.value.id, payload)
      : await createAiConfig({ ...payload, api_key: payload.api_key || '' })
    await enableAiConfig(saved.id)
    notice.value = '配置已保存并启用'
    await load()
  } catch (err) {
    error.value = apiMessage(err)
  } finally {
    busy.value = false
  }
}

async function fetchModels() {
  if (modelLoading.value || busy.value) return
  modelLoading.value = true
  error.value = ''
  notice.value = ''
  try {
    const payload = configPayload({ includeConfigId: true })
    if (!payload.api_key && !payload.config_id) {
      throw new Error('请先填写 API Key，或选择一个已保存的配置')
    }
    const res = await listAiModels(payload)
    modelOptions.value = res.models || []
    notice.value = modelOptions.value.length
      ? `已获取 ${modelOptions.value.length} 个模型`
      : '模型接口返回为空，仍可手动填写模型 ID'
  } catch (err) {
    error.value = apiMessage(err)
  } finally {
    modelLoading.value = false
  }
}

async function enableConfig(config) {
  busy.value = true
  error.value = ''
  try {
    await enableAiConfig(config.id)
    notice.value = `已启用「${config.name}」`
    await load()
  } catch (err) {
    error.value = apiMessage(err)
  } finally {
    busy.value = false
  }
}

async function testConfig() {
  if (!activeConfig.value || busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const res = await testAiConfig(activeConfig.value.id)
    notice.value = res.message || '连接测试完成'
  } catch (err) {
    error.value = apiMessage(err)
  } finally {
    busy.value = false
  }
}

async function saveSkill() {
  if (!canSaveSkill.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const payload = {
      name: skillForm.value.name.trim(),
      description: skillForm.value.description.trim(),
      content: skillForm.value.content.trim(),
    }
    const skill = selectedSkillId.value ? await updateAiSkill(selectedSkillId.value, payload) : await createAiSkill(payload)
    const enabled = await enableSkill(skill, { manageBusy: false })
    if (!enabled) return
    notice.value = `skill「${skill.name}」已保存并启用`
  } catch (err) {
    error.value = apiMessage(err)
  } finally {
    busy.value = false
  }
}

async function enableSkill(skill, { manageBusy = true } = {}) {
  if (!skill) return false
  if (manageBusy) busy.value = true
  error.value = ''
  try {
    const enabled = await enableAiSkill(skill.id)
    activeSkillId.value = enabled.id
    selectedSkillId.value = enabled.id
    if (activeConfig.value) {
      await updateAiConfig(activeConfig.value.id, { active_skill_id: enabled.id })
    }
    await load()
    return true
  } catch (err) {
    error.value = apiMessage(err)
    return false
  } finally {
    if (manageBusy) busy.value = false
  }
}

async function onSkillFile(event) {
  const file = event.target.files?.[0]
  if (!file) return
  error.value = ''
  const suffix = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
  if (!['.md', '.txt'].includes(suffix)) {
    error.value = '只支持导入 .md 或 .txt skill'
    event.target.value = ''
    return
  }
  busy.value = true
  try {
    const content = await file.text()
    const skill = await importAiSkill({ filename: file.name, content })
    const enabled = await enableSkill(skill, { manageBusy: false })
    if (!enabled) return
    notice.value = `已导入「${skill.name}」`
  } catch (err) {
    error.value = apiMessage(err)
  } finally {
    busy.value = false
    event.target.value = ''
  }
}

async function send() {
  const text = input.value.trim()
  if (!text || busy.value) return
  input.value = ''
  const messageIndex = messages.value.push(createMessage({ role: 'user', content: text })) - 1
  await scrollMessagesToBottom()
  busy.value = true
  error.value = ''
  const controller = new AbortController()
  chatAbortController.value = controller
  try {
    const res = await sendAiChat({ conversation_id: conversationId.value, message: text }, { signal: controller.signal })
    conversationId.value = res.conversation_id
    messages.value.push(createMessage({
      role: 'assistant',
      content: res.reply || '已处理',
      tool_results: res.tool_results || [],
      pending_actions: res.pending_actions || [],
    }))
    await scrollMessagesToBottom()
    emit('changed')
  } catch (err) {
    messages.value.splice(messageIndex, 1)
    if (!input.value.trim()) input.value = text
    if (!controller.signal.aborted) error.value = apiMessage(err)
  } finally {
    if (chatAbortController.value === controller) chatAbortController.value = null
    busy.value = false
  }
}

async function firstConfirm(action) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const res = await confirmAiAction(action.id)
    pendingTokens.value = { ...pendingTokens.value, [action.id]: res.confirm_token }
    if (res.action) updatePendingAction(action.id, res.action)
  } catch (err) {
    error.value = apiMessage(err)
  } finally {
    busy.value = false
  }
}

async function secondConfirm(action) {
  const token = pendingTokens.value[action.id]
  if (!token || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const res = await executeAiAction(action.id, token)
    messages.value.push(createMessage({ role: 'system', content: res.message || '危险操作已执行' }))
    updatePendingAction(action.id, { status: 'executed' })
    await scrollMessagesToBottom()
    const nextTokens = { ...pendingTokens.value }
    delete nextTokens[action.id]
    pendingTokens.value = nextTokens
    emit('changed')
  } catch (err) {
    error.value = apiMessage(err)
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  load()
  window.addEventListener('resize', keepWindowInView)
})

watch(assistantMode, (mode) => {
  if (mode === 'chat') scrollMessagesToBottom()
})

onBeforeUnmount(() => {
  chatAbortController.value?.abort()
  window.removeEventListener('resize', keepWindowInView)
})
</script>

<template>
  <button v-if="!open" class="assistant-fab" @click="openAssistant">
    <span>✦</span>
    <strong>{{ assistantName }}</strong>
  </button>

  <div
    v-else
    class="assistant-layer"
    :class="{ fullscreen }"
  >
    <div
      ref="shellRef"
      class="assistant-shell"
      :role="fullscreen ? 'dialog' : 'region'"
      :aria-modal="fullscreen ? 'true' : null"
      :aria-label="assistantName"
      tabindex="-1"
      :class="{ fullscreen, dragging: dragState }"
      :style="shellStyle"
      @keydown.esc.stop.prevent="closeAssistant"
      @keydown.tab="trapFocus"
      @pointermove="dragWindow"
      @pointerup="endDrag"
      @pointercancel="endDrag"
    >
  <div class="assistant">
    <header class="assistant-head" @pointerdown="startDrag">
      <div class="head-copy">
        <h2 class="page-title">
          <span class="page-title-icon float">✦</span>
          <span class="gradient-text">{{ assistantName }}</span>
        </h2>
        <p class="muted">幕僚式日程与资料参谋，可对话安排、查看和规划事项。</p>
      </div>
      <div class="head-actions">
        <div class="mode-switch compact-mode-switch" role="tablist" aria-label="助手视图">
          <button
            class="ghost compact"
            :class="{ active: assistantMode === 'chat' }"
            role="tab"
            :aria-selected="assistantMode === 'chat'"
            @click="assistantMode = 'chat'"
          >
            对话
          </button>
          <button
            class="ghost compact"
            :class="{ active: assistantMode === 'settings' }"
            role="tab"
            :aria-selected="assistantMode === 'settings'"
            @click="assistantMode = 'settings'"
          >
            设置
          </button>
        </div>
        <button class="ghost compact refresh-action" :disabled="loading || busy" @click="load">刷新</button>
        <button class="ghost compact fullscreen-action" @click="toggleFullscreen">
          {{ fullscreen ? '退出全屏' : '全屏' }}
        </button>
        <button class="ghost compact close-action" @click="closeAssistant">收起</button>
      </div>
    </header>

    <div v-if="error" class="card alert-line" role="alert">{{ error }}</div>
    <div v-if="notice" class="card notice-line" role="status">{{ notice }}</div>

    <main class="assistant-body">
      <div v-if="assistantMode === 'settings'" class="assistant-settings">
        <section class="card config-panel">
          <div class="panel-title">
            <div>
              <h3>模型配置</h3>
              <p class="muted">API key 只保存在本地后端数据库。</p>
            </div>
            <button class="ghost compact" @click="newConfig">新建</button>
          </div>

          <div v-if="configs.length" class="pill-list">
            <button
              v-for="config in configs"
              :key="config.id"
              class="ghost pill"
              :class="{ active: activeConfig?.id === config.id, enabled: config.enabled }"
              @click="selectConfig(config)"
            >
              {{ config.name }}
            </button>
          </div>

          <div class="form-grid">
            <label>
              <span>配置名称</span>
              <input v-model="configForm.name" placeholder="默认配置" />
            </label>
            <label>
              <span>Provider</span>
              <select v-model="configForm.provider">
                <option value="openai_chat">OpenAI Chat Completions</option>
                <option value="openai_responses">OpenAI Responses</option>
                <option value="claude_messages">Claude Messages</option>
              </select>
            </label>
            <label>
              <span>模型</span>
              <div class="model-picker">
                <input v-model="configForm.model" placeholder="点击获取模型，或手动填写模型 ID" />
                <button class="ghost compact" :disabled="modelLoading || busy" @click="fetchModels">
                  {{ modelLoading ? '获取中' : '获取模型' }}
                </button>
              </div>
              <select
                v-if="modelOptions.length"
                v-model="configForm.model"
                class="model-select"
              >
                <option value="">选择模型</option>
                <option v-for="model in modelOptions" :key="model" :value="model">
                  {{ model }}
                </option>
              </select>
            </label>
            <label>
              <span>API Key</span>
              <input v-model="configForm.api_key" type="password" placeholder="留空表示不修改" />
            </label>
            <label>
              <span>Base URL</span>
              <input v-model="configForm.base_url" placeholder="可选" />
            </label>
            <label>
              <span>完整 URL</span>
              <input v-model="configForm.full_url" placeholder="可选，优先于 Base URL" />
            </label>
            <label>
              <span>HTTP Proxy</span>
              <input v-model="configForm.proxy_url" placeholder="可选，例如 http://127.0.0.1:7890" />
            </label>
            <label>
              <span>额外 Headers</span>
              <textarea v-model="configForm.extra_headers_text" class="headers-input" spellcheck="false"></textarea>
            </label>
          </div>

          <div class="panel-actions">
            <button :disabled="!canSaveConfig || busy" @click="saveConfig">保存并启用</button>
            <button class="ghost" :disabled="!hasConfig || busy" @click="testConfig">测试连接</button>
            <button v-if="activeConfig && !activeConfig.enabled" class="ghost" :disabled="busy" @click="enableConfig(activeConfig)">
              仅启用
            </button>
          </div>
        </section>

        <section class="card persona-panel">
          <div class="panel-title">
            <div>
              <h3>助手人设</h3>
              <p class="muted">为空时使用内置幕僚式默认人设，和 skill 工作规则分开。</p>
            </div>
          </div>

          <div class="form-grid">
            <label>
              <span>助手名称</span>
              <input v-model="configForm.assistant_name" placeholder="知时助手" />
            </label>
            <label>
              <span>自定义人设</span>
              <textarea
                v-model="configForm.persona"
                class="persona-input"
                placeholder="可选；留空使用内置默认人设"
              ></textarea>
            </label>
          </div>

          <div class="panel-actions">
            <button :disabled="!canSaveConfig || busy" @click="saveConfig">保存人设与配置</button>
          </div>
        </section>

        <section class="card skill-panel">
          <div class="panel-title">
            <div>
              <h3>Skill 规则</h3>
              <p class="muted">skill 只保存工作规则，和助手人设分开。</p>
            </div>
            <button class="ghost compact" @click="fileInput?.click()">导入</button>
            <input ref="fileInput" type="file" accept=".md,.txt" hidden @change="onSkillFile" />
          </div>

          <div v-if="skills.length" class="pill-list">
            <button
              v-for="skill in skills"
              :key="skill.id"
              class="ghost pill"
              :class="{ active: selectedSkillId === skill.id, enabled: activeSkillId === skill.id || skill.enabled }"
              @click="selectSkill(skill)"
            >
              {{ skill.name }}
            </button>
          </div>

          <div class="skill-tools">
            <button class="ghost compact" @click="newSkill">新建 skill</button>
            <button
              v-if="selectedSkillId"
              class="ghost compact"
              :disabled="busy || activeSkillId === selectedSkillId"
              @click="enableSkill(skills.find((s) => s.id === selectedSkillId))"
            >
              启用当前
            </button>
          </div>

          <div class="form-grid">
            <label>
              <span>名称</span>
              <input v-model="skillForm.name" placeholder="论文规划 / 每周复盘" />
            </label>
            <label>
              <span>描述</span>
              <input v-model="skillForm.description" placeholder="这个 skill 适合什么工作流" />
            </label>
            <label>
              <span>正文</span>
              <textarea
                v-model="skillForm.content"
                class="skill-input"
                placeholder="写入助手规则、任务拆解方法、资料整理偏好..."
              ></textarea>
            </label>
          </div>

          <button :disabled="!canSaveSkill || busy" @click="saveSkill">保存并启用 skill</button>
        </section>
      </div>

      <section v-else class="card chat-panel chat-stage">
        <div class="chat-head">
          <div class="chat-copy">
            <h3>{{ assistantName }} 对话</h3>
            <p class="muted">低风险操作会直接执行；危险操作会显示二次确认卡片。</p>
          </div>
          <span v-if="busy" class="tag">处理中</span>
          <button v-else class="ghost compact" @click="assistantMode = 'settings'">配置</button>
        </div>

        <div ref="messagesRef" class="messages" role="log" aria-live="polite" :aria-busy="busy">
          <div v-if="!messages.length" class="empty-chat">
            <div class="empty-icon float-slow">✧</div>
            <div>告诉{{ assistantName }}你要安排什么，或让它整理刚上传的资料。</div>
          </div>

          <article v-for="(message, index) in visibleMessages" :key="index" :class="['message', message.role]">
            <div class="message-role">
              {{ message.role === 'user' ? '你' : message.role === 'assistant' ? assistantName : '系统' }}
            </div>
            <div
              v-if="message.content?.trim()"
              class="message-content"
            >
              <template v-for="(block, blockIndex) in message.blocks" :key="blockIndex">
                <ul v-if="block.type === 'list'" class="message-list">
                  <li v-for="(item, itemIndex) in block.items" :key="itemIndex">{{ item }}</li>
                </ul>
                <p v-else-if="block.type === 'paragraph'" class="message-paragraph">
                  <template v-for="(line, lineIndex) in block.lines" :key="lineIndex">
                    <span>{{ line }}</span>
                    <br v-if="lineIndex < block.lines.length - 1" />
                  </template>
                </p>
              </template>
            </div>

            <div v-if="message.tool_results?.length" class="tool-results">
              <span class="tag">已执行 {{ message.tool_results.length }} 个工具</span>
              <details>
                <summary>查看结果</summary>
                <pre>{{ JSON.stringify(message.tool_results, null, 2) }}</pre>
              </details>
            </div>

            <div v-for="action in message.pending_actions || []" :key="action.id" class="pending-card">
              <div class="pending-head">
                <div>
                  <strong>危险操作待确认</strong>
                  <p>{{ pendingStatusText(action) }}</p>
                </div>
                <span class="danger-dot"></span>
              </div>
              <p class="pending-summary">{{ action.summary }}</p>
              <ul v-if="action.preview?.length" class="pending-preview">
                <li v-for="(line, previewIndex) in action.preview" :key="previewIndex">{{ line }}</li>
              </ul>
              <div class="pending-actions">
                <button v-if="!pendingTokens[action.id]" class="ghost" :disabled="busy" @click="firstConfirm(action)">
                  第一次确认
                </button>
                <button v-else class="danger" :disabled="busy" @click="secondConfirm(action)">
                  我已理解影响，执行
                </button>
              </div>
            </div>
          </article>
        </div>

        <div class="composer">
          <textarea
            v-model="input"
            placeholder="例如：帮我把本周论文阅读拆成三天计划，并给明晚加一个提醒..."
            @keydown.ctrl.enter.prevent="send"
          ></textarea>
          <button :disabled="busy || !input.trim()" @click="send">{{ busy ? '处理中...' : '发送' }}</button>
        </div>
      </section>
    </main>
  </div>
  </div>
  </div>
</template>

<style scoped>
.assistant-fab {
  position: fixed;
  right: 28px;
  bottom: 28px;
  z-index: 210;
  display: inline-flex;
  align-items: center;
  gap: 9px;
  max-width: min(360px, calc(100vw - 32px));
  padding: 13px 18px 13px 14px;
  border-radius: var(--radius-pill);
  box-shadow: var(--shadow-xl), 0 0 28px var(--accent-glow);
}

.assistant-fab strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.assistant-fab span {
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.28);
  box-shadow: var(--shadow-inset);
}

.assistant-layer {
  position: fixed;
  inset: 0;
  z-index: 210;
  background: transparent;
  pointer-events: none;
}

.assistant-layer.fullscreen {
  background: rgba(232, 248, 255, 0.62);
  backdrop-filter: blur(3px);
  -webkit-backdrop-filter: blur(3px);
}

.assistant-shell {
  position: fixed;
  right: 24px;
  bottom: 24px;
  width: min(560px, calc(100vw - 32px));
  height: min(680px, calc(100vh - 32px));
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: rgba(255, 255, 255, 0.98);
  box-shadow: var(--shadow-xl), var(--shadow-inset);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  touch-action: auto;
  user-select: auto;
  pointer-events: auto;
  overflow: hidden;
}

.assistant-shell.dragging {
  user-select: none;
}

.assistant-shell.fullscreen {
  inset: 18px;
  width: auto;
  height: auto;
  padding: 18px;
}

.assistant {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  min-height: 0;
  margin: 0;
}

.assistant-head,
.panel-title,
.panel-actions,
.head-actions,
.chat-head,
.pending-head,
.pending-actions,
.skill-tools {
  display: flex;
  gap: 12px;
}

.assistant-head {
  align-items: center;
  justify-content: space-between;
  cursor: grab;
  touch-action: none;
  gap: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}

.assistant-shell:not(.fullscreen) .assistant-head .muted {
  display: none;
}

.assistant-shell:not(.fullscreen) .assistant-head {
  align-items: center;
}

.assistant-shell:not(.fullscreen) .page-title {
  gap: 8px;
}

.assistant-shell:not(.fullscreen) .page-title-icon {
  width: 36px;
  height: 36px;
  font-size: 18px;
}

.assistant-shell:not(.fullscreen) .assistant-head h2 {
  font-size: 18px;
}

.assistant-shell:not(.fullscreen) .head-actions {
  gap: 6px;
}

.assistant-shell:not(.fullscreen) .refresh-action {
  display: none;
}

.head-copy,
.chat-copy {
  min-width: 0;
}

.assistant-head .page-title,
.chat-head h3 {
  overflow-wrap: anywhere;
}

.assistant-shell.dragging .assistant-head {
  cursor: grabbing;
}

.assistant-shell.fullscreen .assistant-head {
  cursor: default;
}

.assistant-head h2,
.panel-title h3,
.chat-head h3 {
  margin: 0;
}

.assistant-head p,
.panel-title p,
.chat-head p,
.pending-head p {
  margin: 4px 0 0;
}

.head-actions {
  align-items: center;
  flex-shrink: 0;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.assistant-body {
  display: flex;
  min-height: 0;
  flex: 1;
  overflow: hidden;
}

.assistant-settings {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  padding: 2px 4px 4px;
}

.assistant-shell:not(.fullscreen) .assistant-settings {
  grid-template-columns: 1fr;
}

.config-panel,
.persona-panel,
.skill-panel,
.chat-panel {
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

.chat-panel {
  border-radius: var(--radius-sm);
  box-shadow: none;
}

.mode-switch {
  display: inline-grid;
  grid-template-columns: repeat(2, minmax(54px, 1fr));
  gap: 4px;
  padding: 4px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  background: rgba(255, 255, 255, 0.7);
  box-shadow: var(--shadow-inset);
}

.mode-switch button {
  min-height: 30px;
  border-radius: var(--radius-pill);
  box-shadow: none;
}

.mode-switch button.active {
  color: #fff;
  background: linear-gradient(135deg, var(--accent), var(--sea-400));
  box-shadow: 0 5px 16px var(--accent-glow);
}

.panel-title,
.chat-head,
.pending-head {
  align-items: flex-start;
  justify-content: space-between;
}

.panel-title h3,
.chat-head h3 {
  font-size: 16px;
  font-weight: 800;
}

.panel-title .compact,
.skill-tools .compact {
  flex-shrink: 0;
}

.pill-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 14px 0;
}

.pill {
  padding: 7px 13px;
  font-size: 12px;
  box-shadow: var(--shadow-inset);
}

.pill.active,
.pill.enabled {
  color: #fff;
  background: linear-gradient(135deg, var(--accent), var(--sea-400));
  box-shadow: 0 4px 14px var(--accent-glow), var(--shadow-inset);
}

.form-grid {
  display: grid;
  gap: 10px;
}

label {
  display: grid;
  gap: 5px;
}

label span {
  color: var(--text-soft);
  font-size: 12px;
  font-weight: 700;
}

.model-picker {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
}

.model-picker input {
  min-width: 0;
}

.model-select {
  margin-top: 6px;
}

.headers-input,
.persona-input {
  min-height: 82px;
  font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
}

.persona-input {
  min-height: 108px;
}

.skill-input {
  min-height: 150px;
}

.panel-actions,
.skill-tools {
  align-items: center;
  flex-wrap: wrap;
  margin-top: 12px;
}

.compact {
  padding: 7px 14px;
  font-size: 12px;
}

.alert-line,
.notice-line {
  padding: 12px 16px;
  font-weight: 600;
}

.alert-line {
  color: var(--pri-high);
  background: rgba(242, 107, 122, 0.08);
}

.notice-line {
  color: var(--accent-hover);
  background: var(--accent-soft);
}

.chat-panel {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-stage {
  width: 100%;
  margin: 0 auto;
}

.assistant-shell.fullscreen .chat-stage {
  max-width: 980px;
}

.assistant-shell:not(.fullscreen) .chat-panel {
  padding: 0;
  border: 0;
  background: transparent;
}

.assistant-shell:not(.fullscreen) .chat-head {
  display: none;
}

.messages {
  flex: 1;
  min-height: 0;
  overflow-y: scroll;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 6px 6px 8px 2px;
  scrollbar-gutter: stable;
}

.empty-chat {
  margin: auto;
  text-align: center;
  color: var(--text-soft);
  max-width: 380px;
}

.empty-icon {
  font-size: 42px;
  margin-bottom: 8px;
}

.message {
  width: min(88%, 640px);
  max-width: 100%;
  flex: 0 0 auto;
  display: block;
  height: auto;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  box-shadow: var(--shadow-inset);
  contain: layout paint;
  overflow: hidden;
}

.assistant-shell:not(.fullscreen) .message {
  max-width: calc(100% - 14px);
}

.assistant-shell:not(.fullscreen) .message.user {
  width: fit-content;
  max-width: min(82%, 360px);
}

.assistant-shell:not(.fullscreen) .message.assistant,
.assistant-shell:not(.fullscreen) .message.system {
  width: min(92%, 430px);
  max-width: min(92%, 430px);
}

.message.user {
  align-self: flex-end;
  background: var(--accent-soft);
}

.message.assistant,
.message.system {
  align-self: flex-start;
}

.message.system {
  border-color: var(--border-strong);
}

.message-role {
  font-size: 12px;
  font-weight: 800;
  color: var(--text-soft);
}

.message-content {
  display: block;
  margin-top: 5px;
  color: var(--text);
  font-size: 14px;
  line-height: 1.7;
  max-width: 100%;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.message-paragraph,
.message-list {
  margin: 0 0 8px;
}

.message-paragraph:last-child,
.message-list:last-child {
  margin-bottom: 0;
}

.message-list {
  padding-left: 18px;
}

.message-list li + li {
  margin-top: 3px;
}

.tool-results {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}

summary {
  cursor: pointer;
  color: var(--text-soft);
  font-size: 13px;
  font-weight: 700;
}

pre {
  max-height: 180px;
  margin: 8px 0 0;
  overflow: auto;
  padding: 10px;
  border-radius: var(--radius-xs);
  background: var(--surface);
  color: var(--text);
  font-size: 12px;
}

.pending-card {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid rgba(242, 107, 122, 0.38);
  border-radius: var(--radius-sm);
  background: rgba(242, 107, 122, 0.08);
}

.pending-head strong {
  color: var(--pri-high);
}

.danger-dot {
  width: 12px;
  height: 12px;
  margin-top: 5px;
  border-radius: 50%;
  background: var(--pri-high);
  box-shadow: 0 0 0 5px rgba(242, 107, 122, 0.12);
  flex-shrink: 0;
}

.pending-summary {
  color: var(--text);
  font-weight: 600;
}

.pending-preview {
  margin: 10px 0 0;
  padding-left: 18px;
  color: var(--text);
  font-size: 13px;
  line-height: 1.6;
}

.pending-actions {
  justify-content: flex-end;
  margin-top: 10px;
}

.composer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.composer textarea {
  min-height: 58px;
  max-height: 104px;
  resize: none;
  overflow-y: auto;
}

.assistant-shell:not(.fullscreen) .composer {
  grid-template-columns: minmax(0, 1fr) 62px;
  gap: 8px;
}

.assistant-shell:not(.fullscreen) .composer button {
  width: 62px;
  min-width: 62px;
  padding: 0;
}

@media (max-width: 980px) {
  .assistant-layer {
    background: transparent;
  }

  .assistant-layer.fullscreen {
    background: rgba(232, 248, 255, 0.66);
  }

  .assistant-shell {
    right: 16px;
    bottom: 16px;
    width: min(560px, calc(100vw - 32px));
    height: min(680px, calc(100vh - 32px));
    padding: 12px;
  }

  .assistant-head {
    flex-direction: row;
  }

  .assistant-settings {
    grid-template-columns: 1fr;
  }

  .chat-panel {
    min-height: 0;
  }
}

@media (max-width: 640px) {
  .assistant-head .muted,
  .panel-title .muted,
  .chat-head .muted {
    display: none;
  }

  .panel-actions,
  .model-picker,
  .composer {
    width: 100%;
    grid-template-columns: 1fr;
  }

  .head-actions {
    display: flex;
    width: auto;
    flex-wrap: nowrap;
  }

  .composer button {
    width: 100%;
  }

  .assistant-fab {
    right: 14px;
    bottom: 14px;
  }

  .message {
    width: fit-content;
  }

  .assistant-shell.fullscreen {
    inset: 8px;
  }
}
</style>
