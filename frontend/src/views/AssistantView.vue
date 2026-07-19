<script setup>
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  confirmAiAction,
  createAiConfig,
  createAiSkill,
  enableAiConfig,
  enableAiSkill,
  executeAiAction,
  importAiSkill,
  getAiConversation,
  listAiConfigs,
  listAiConversations,
  listAiModels,
  listAiSkills,
  renameConversation,
  deleteConversation,
  sendAiChat,
  testAiConfig,
  updateAiConfig,
  updateAiSkill,
  uploadAiAttachment,
} from '../api/ai'
import { getSettings, updateSettings } from '../api/settings'
import { uploadFile } from '../api/files'
import ArtIcon from '../components/ArtIcon.vue'
import AssistantChat from './assistant/AssistantChat.vue'
import AssistantHistory from './assistant/AssistantHistory.vue'
import AssistantSettings from './assistant/AssistantSettings.vue'
import SegmentedControl from '../components/ui/SegmentedControl.vue'

const props = defineProps({
  floatMode: { type: Boolean, default: false },
})
const emit = defineEmits(['changed', 'collapse'])

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
const conversations = ref([])
const historyLoading = ref(false)
const modelOptions = ref([])
const modelLoading = ref(false)
const fileInput = ref(null)
const chatFileInput = ref(null)
const aiAttachmentInput = ref(null)
const chatRef = ref(null)
const uploadingFiles = ref(false)
const attachingFiles = ref(false)
const chatAttachments = ref([])
const failedChatText = ref('')
const shellRef = ref(null)
const open = ref(props.floatMode)
const assistantMode = ref('chat')
const fullscreen = ref(false)
const windowPosition = ref(loadWindowPosition())
const dragState = ref(null)
// fab 入口按钮可拖动（与悬浮窗球形按钮一致）：pointer 区分点击/拖动，位置持久化
const fabPosition = ref(loadFabPosition())
let fabDownAt = null
let fabDragging = false
const FAB_DRAG_THRESHOLD = 4
const previousFocus = ref(null)
const chatAbortController = ref(null)

// 助手模式：assistant=知时助手（原版问答式）/ agent=知时代理（主动代劳的秘书）
const STOCK_NAMES = ['知时助手', '知时代理']
const assistantModeType = ref('agent')
const assistantModeOptions = [
  { value: 'assistant', label: '知时助手' },
  { value: 'agent', label: '知时代理' },
]
const assistantName = computed(() => {
  const custom = (activeConfig.value?.assistant_name || configForm.value.assistant_name || '').trim()
  if (custom && !STOCK_NAMES.includes(custom)) return custom
  return assistantModeType.value === 'agent' ? '知时代理' : '知时助手'
})
const modeSubtitle = computed(() =>
  assistantModeType.value === 'agent'
    ? '你的贴身秘书：主动办妥事务，事事有回应。'
    : '安静地整理日程、资料和下一步行动。'
)
const hasConfig = computed(() => Boolean(activeConfig.value))
const hasEnabledConfig = computed(() => Boolean(activeConfig.value?.enabled))
const canSaveConfig = computed(() => {
  const f = configForm.value
  return f.name.trim() && f.assistant_name.trim() && f.provider && f.model.trim() && (f.api_key.trim() || activeConfig.value)
})
const canSaveSkill = computed(() => skillForm.value.name.trim() && skillForm.value.content.trim())
const shellStyle = computed(() => {
  if (props.floatMode) return {} // 悬浮窗独立窗口：填满，不用窗口内定位
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
    native_web_search_enabled: false,
    native_web_search_options_text: '{}',
    search_enhancement_enabled: false,
    price_input: '',
    price_output: '',
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
    native_web_search_enabled: Boolean(config.native_web_search_enabled),
    native_web_search_options_text: JSON.stringify(config.native_web_search_options || {}, null, 2),
    search_enhancement_enabled: Boolean(config.search_enhancement_enabled),
    price_input: Number(config.price_input) > 0 ? String(config.price_input) : '',
    price_output: Number(config.price_output) > 0 ? String(config.price_output) : '',
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

function parseNativeWebSearchOptions() {
  const raw = configForm.value.native_web_search_options_text.trim()
  if (!raw) return {}
  const parsed = JSON.parse(raw)
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
    throw new Error('原生联网参数必须是 JSON 对象')
  }
  return parsed
}

// 价目输入：留空/非法/负数都归一为 0（后端约定 0 = 未设置，不参与成本估算）
function priceValue(value) {
  const n = parseFloat(value)
  return Number.isFinite(n) && n > 0 ? n : 0
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
    native_web_search_enabled: configForm.value.native_web_search_enabled,
    native_web_search_options: parseNativeWebSearchOptions(),
    search_enhancement_enabled: configForm.value.search_enhancement_enabled,
    price_input: priceValue(configForm.value.price_input),
    price_output: priceValue(configForm.value.price_output),
    active_skill_id: activeSkillId.value || null,
  }
  if (configForm.value.api_key.trim()) payload.api_key = configForm.value.api_key.trim()
  if (includeConfigId && activeConfig.value) payload.config_id = activeConfig.value.id
  return payload
}

function apiMessage(err) {
  return err?.message || '操作失败'
}

function formatFileSize(size) {
  const value = Number(size || 0)
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${value} B`
}

function uploadedFileLine(file) {
  return `- #${file.id} ${file.original_name} | 类型:${file.mime_type || '未知'} | 大小:${formatFileSize(file.size)} | 备注:${file.notes || '无'}`
}

function attachmentLine(file) {
  return `- ${file.original_name} | ${file.kind === 'image' ? '图片识别' : '文档解析'} | 类型:${file.mime_type || '未知'} | 大小:${formatFileSize(file.size)}`
}

function chatDisplayText(text, attachments = []) {
  const normalized = text?.trim() || (attachments.length ? '请分析这些附件。' : '')
  if (!attachments.length) return normalized
  return [
    normalized,
    '',
    '本轮给 AI 查看：',
    ...attachments.map(attachmentLine),
  ].join('\n')
}

function uploadedFilesPrompt(files, instruction = '') {
  return [
    '我刚把以下资料交给你处理；系统已经把它们保存到资料库。',
    instruction ? `用户补充说明：${instruction}` : '用户没有补充说明，请根据文件名、备注和当前任务上下文判断。',
    '请你根据当前任务和资料信息判断它们应该归属到哪些任务，并自动完成整理：',
    '- 如果已有合适任务，请用 attach_file_to_task 关联资料。',
    '- 如果需要新任务或提醒，请创建任务/提醒，并在参数里带上 file_ids 自动关联资料。',
    '- 如果信息不足，请先列出你的判断和少量候选，不要臆测未提供的文件正文。',
    '',
    ...files.map(uploadedFileLine),
  ].join('\n')
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

function loadFabPosition() {
  try {
    const raw = localStorage.getItem('assistant-fab-position')
    if (!raw) return null
    const p = JSON.parse(raw)
    if (Number.isFinite(p?.x) && Number.isFinite(p?.y)) return p
  } catch { /* 忽略损坏的存储 */ }
  return null
}
function saveFabPosition(p) {
  localStorage.setItem('assistant-fab-position', JSON.stringify(p))
}
function clampFabPosition(x, y, w, h) {
  const margin = 8
  return {
    x: Math.min(Math.max(margin, x), Math.max(margin, window.innerWidth - w - margin)),
    y: Math.min(Math.max(margin, y), Math.max(margin, window.innerHeight - h - margin)),
  }
}
const fabStyle = computed(() => {
  if (!fabPosition.value) return {}
  return { left: `${fabPosition.value.x}px`, top: `${fabPosition.value.y}px`, right: 'auto', bottom: 'auto' }
})
function onFabPointerDown(e) {
  if (e.button !== 0) return
  const rect = e.currentTarget.getBoundingClientRect()
  fabDownAt = {
    x: e.clientX, y: e.clientY,
    ox: fabPosition.value?.x ?? rect.left,
    oy: fabPosition.value?.y ?? rect.top,
    w: rect.width, h: rect.height,
  }
  fabDragging = false
  e.currentTarget.setPointerCapture?.(e.pointerId)
}
function onFabPointerMove(e) {
  if (!fabDownAt) return
  const dx = e.clientX - fabDownAt.x
  const dy = e.clientY - fabDownAt.y
  if (!fabDragging && Math.hypot(dx, dy) > FAB_DRAG_THRESHOLD) fabDragging = true
  if (fabDragging) {
    e.preventDefault()
    fabPosition.value = clampFabPosition(fabDownAt.ox + dx, fabDownAt.oy + dy, fabDownAt.w, fabDownAt.h)
  }
}
function onFabPointerUp(e) {
  if (!fabDownAt) return
  e.currentTarget?.releasePointerCapture?.(e.pointerId)
  if (!fabDragging) openAssistant()
  else saveFabPosition(fabPosition.value)
  fabDownAt = null
  fabDragging = false
}

function startDrag(event) {
  if (props.floatMode) return // 悬浮窗用原生 -webkit-app-region: drag 拖动窗口
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

function handleAssistantPrompt(event) {
  const text = event.detail?.text
  if (!text) return
  openAssistant()
  assistantMode.value = 'chat'
  input.value = text
  nextTick(() => chatRef.value?.focusComposer())
}

function closeAssistant() {
  if (props.floatMode) {
    // 悬浮窗：收起为按钮态（由父组件 AssistantFloat 处理窗口 resize）
    emit('collapse')
    return
  }
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
  chatRef.value?.scrollToBottom()
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

async function loadConversations() {
  historyLoading.value = true
  error.value = ''
  try {
    conversations.value = await listAiConversations()
  } catch (err) {
    error.value = apiMessage(err)
  } finally {
    historyLoading.value = false
  }
}

function showHistory() {
  if (assistantMode.value === 'history') {
    loadConversations()
    return
  }
  assistantMode.value = 'history'
}

function startNewChat() {
  if (busy.value || uploadingFiles.value || attachingFiles.value) return
  conversationId.value = null
  messages.value = []
  input.value = ''
  chatAttachments.value = []
  pendingTokens.value = {}
  failedChatText.value = ''
  assistantMode.value = 'chat'
  notice.value = '已开始新聊天'
  nextTick(scrollMessagesToBottom)
}

async function openConversation(row) {
  if (!row || busy.value || uploadingFiles.value || attachingFiles.value) return
  historyLoading.value = true
  error.value = ''
  try {
    const data = await getAiConversation(row.id)
    conversationId.value = data.id
    messages.value = (data.messages || []).map(createMessage)
    chatAttachments.value = []
    pendingTokens.value = {}
    failedChatText.value = ''
    assistantMode.value = 'chat'
    await scrollMessagesToBottom()
  } catch (err) {
    error.value = apiMessage(err)
  } finally {
    historyLoading.value = false
  }
}

// 历史会话管理：重命名 / 删除（删除当前会话则回到新聊天）
const confirmDialog = inject('confirm-dialog', null)

async function renameConversationById(row, title) {
  const next = (title || '').trim()
  if (!next || next === row.title) return
  try {
    const updated = await renameConversation(row.id, next)
    const idx = conversations.value.findIndex((c) => c.id === row.id)
    if (idx !== -1) conversations.value[idx] = { ...conversations.value[idx], ...updated }
    notice.value = '已重命名'
  } catch (err) {
    error.value = apiMessage(err)
  }
}

async function deleteConversationById(row) {
  const ok = confirmDialog
    ? await confirmDialog({
        title: '删除会话',
        message: `确定删除「${row.title || '新的会话'}」吗？该会话的全部消息将一并删除，且不可恢复。`,
        confirmText: '删除',
        danger: true,
      })
    : true
  if (!ok) return
  try {
    await deleteConversation(row.id)
    conversations.value = conversations.value.filter((c) => c.id !== row.id)
    if (conversationId.value === row.id) startNewChat()
    notice.value = '已删除会话'
  } catch (err) {
    error.value = apiMessage(err)
  }
}

function refreshActiveView() {
  if (assistantMode.value === 'history') {
    loadConversations()
    return
  }
  load()
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

async function sendChatText(text, { restoreToInput = false, attachments = [] } = {}) {
  const cleanText = text?.trim() || (attachments.length ? '请分析这些附件。' : '')
  if ((!cleanText && !attachments.length) || busy.value) return false
  const displayText = chatDisplayText(cleanText, attachments)
  const messageIndex = messages.value.push(createMessage({ role: 'user', content: displayText })) - 1
  await scrollMessagesToBottom()
  busy.value = true
  error.value = ''
  const controller = new AbortController()
  chatAbortController.value = controller
  try {
    const res = await sendAiChat(
      {
        conversation_id: conversationId.value,
        message: cleanText,
        attachments: attachments.map((file) => ({ id: file.id })),
      },
      { signal: controller.signal }
    )
    conversationId.value = res.conversation_id
    failedChatText.value = ''
    messages.value.push(createMessage({
      role: 'assistant',
      content: res.reply || '已处理',
      tool_results: res.tool_results || [],
      pending_actions: res.pending_actions || [],
    }))
    await scrollMessagesToBottom()
    emit('changed')
    return true
  } catch (err) {
    messages.value.splice(messageIndex, 1)
    if (restoreToInput && !input.value.trim()) input.value = text || ''
    if (!controller.signal.aborted) {
      error.value = apiMessage(err)
      // 手动发送失败的原文记录下来，对话区显示「重试」条，可一键重发同一条
      if (restoreToInput) failedChatText.value = text || ''
    }
    return false
  } finally {
    if (chatAbortController.value === controller) chatAbortController.value = null
    busy.value = false
  }
}

async function send() {
  const text = input.value.trim()
  const attachments = [...chatAttachments.value]
  if ((!text && !attachments.length) || busy.value || uploadingFiles.value || attachingFiles.value) return
  input.value = ''
  chatAttachments.value = []
  const ok = await sendChatText(text, { restoreToInput: true, attachments })
  if (!ok && !chatAttachments.value.length) chatAttachments.value = attachments
}

// 重发上一条发送失败的消息；若输入框仍是当时恢复的原文则清掉，避免重复发送
async function retryFailed() {
  const text = failedChatText.value
  if (!text || busy.value) return
  failedChatText.value = ''
  if (input.value.trim() === text.trim()) input.value = ''
  await sendChatText(text, { restoreToInput: true })
}

async function onAiAttachmentFiles(event) {
  const files = Array.from(event.target.files || [])
  if (!files.length) return
  if (busy.value || uploadingFiles.value || attachingFiles.value) {
    event.target.value = ''
    return
  }
  attachingFiles.value = true
  error.value = ''
  notice.value = ''
  try {
    for (const file of files) {
      chatAttachments.value.push(await uploadAiAttachment(file))
    }
    notice.value = `已添加 ${files.length} 个对话附件`
  } catch (err) {
    error.value = apiMessage(err)
  } finally {
    attachingFiles.value = false
    event.target.value = ''
  }
}

function removeChatAttachment(id) {
  chatAttachments.value = chatAttachments.value.filter((file) => file.id !== id)
}

async function onChatFiles(event) {
  const files = Array.from(event.target.files || [])
  if (!files.length) return
  if (busy.value || uploadingFiles.value || attachingFiles.value) {
    event.target.value = ''
    return
  }
  const instruction = input.value.trim()
  uploadingFiles.value = true
  error.value = ''
  notice.value = ''
  const uploaded = []
  try {
    for (const file of files) {
      const note = instruction
        ? `对话上传说明：${instruction}`
        : `由${assistantName.value}对话上传，等待 AI 判断归属并关联任务`
      uploaded.push(await uploadFile(file, note))
    }
  } catch (err) {
    error.value = apiMessage(err)
  } finally {
    uploadingFiles.value = false
    event.target.value = ''
  }
  if (!uploaded.length) return
  if (instruction && input.value.trim() === instruction) input.value = ''
  notice.value = `已上传 ${uploaded.length} 个资料`
  emit('changed')
  const text = uploadedFilesPrompt(uploaded, instruction)
  if (hasEnabledConfig.value) {
    await sendChatText(text)
  } else {
    messages.value.push(createMessage({
      role: 'system',
      content: `${text}\n\n请先在设置中配置并启用模型，再让${assistantName.value}整理这些资料。`,
    }))
    await scrollMessagesToBottom()
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
  // 读取助手模式（知时助手/知时代理），失败按默认 agent 处理
  getSettings()
    .then((s) => { assistantModeType.value = s.assistant_mode === 'assistant' ? 'assistant' : 'agent' })
    .catch(() => {})
  window.addEventListener('resize', keepWindowInView)
  window.addEventListener('assistant:prompt', handleAssistantPrompt)
  // 悬浮窗：主窗口打开时主进程发 float:collapse，收起为按钮态
  if (props.floatMode) {
    window.electronAPI?.onFloatCollapse?.(() => emit('collapse'))
  }
})

// 切换助手模式：写入后端设置，名称/人设/能力门限即时随模式切换
async function changeAssistantMode(mode) {
  const prev = assistantModeType.value
  assistantModeType.value = mode // 乐观更新
  try {
    await updateSettings({ assistant_mode: mode })
    notice.value = mode === 'agent' ? '已切换到知时代理：我会更主动地为你办妥事务' : '已切换到知时助手：有求必应，不多打扰'
  } catch (err) {
    assistantModeType.value = prev
    error.value = apiMessage(err)
  }
}

watch(assistantMode, (mode) => {
  if (mode === 'chat') scrollMessagesToBottom()
  if (mode === 'history') loadConversations()
})

// notice/error 自动消失：成功/通知类 4 秒、错误类 8 秒，均保留手动关闭
let noticeTimer = null
let errorTimer = null
watch(notice, (value) => {
  window.clearTimeout(noticeTimer)
  noticeTimer = null
  if (value) noticeTimer = window.setTimeout(() => { notice.value = '' }, 4000)
})
watch(error, (value) => {
  window.clearTimeout(errorTimer)
  errorTimer = null
  if (value) errorTimer = window.setTimeout(() => { error.value = '' }, 8000)
})

onBeforeUnmount(() => {
  chatAbortController.value?.abort()
  window.clearTimeout(noticeTimer)
  window.clearTimeout(errorTimer)
  window.removeEventListener('resize', keepWindowInView)
  window.removeEventListener('assistant:prompt', handleAssistantPrompt)
})
</script>

<template>
  <button v-if="!open" class="assistant-fab" :class="{ dragging: fabDragging }" :style="fabStyle" :aria-label="assistantName" @pointerdown="onFabPointerDown" @pointermove="onFabPointerMove" @pointerup="onFabPointerUp" @pointercancel="onFabPointerUp">
    <ArtIcon name="assistant" tone="aqua" :size="38" tile />
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
      :class="{ fullscreen, dragging: dragState, 'float-mode': floatMode }"
      :style="shellStyle"
      @keydown.esc.stop.prevent="closeAssistant"
      @keydown.tab="trapFocus"
      @pointermove="dragWindow"
      @pointerup="endDrag"
      @pointercancel="endDrag"
    >
  <div class="assistant">
    <header class="assistant-head" @pointerdown="startDrag">
      <div class="head-main">
        <div class="head-copy">
          <h2 class="page-title">
            <ArtIcon name="assistant" tone="aqua" :size="36" tile :label="assistantName" />
            <span>{{ assistantName }}</span>
          </h2>
        </div>
        <div class="head-actions">
          <button class="ghost compact new-chat-action" :disabled="busy || uploadingFiles || attachingFiles" @click="startNewChat">
            <ArtIcon name="plus" tone="aqua" :size="16" />
            <span>新聊天</span>
          </button>
          <button class="ghost compact refresh-action" :disabled="loading || historyLoading || busy" @click="refreshActiveView">
            <ArtIcon name="refresh" tone="aqua" :size="16" />
            <span>刷新</span>
          </button>
          <button class="ghost compact fullscreen-action" @click="toggleFullscreen">
            <ArtIcon name="expand" tone="pearl" :size="16" />
            <span>{{ fullscreen ? '退出全屏' : '全屏' }}</span>
          </button>
          <button class="ghost compact close-action" @click="closeAssistant">
            <ArtIcon name="close" tone="pearl" :size="16" />
            <span>收起</span>
          </button>
        </div>
      </div>
      <div class="head-switches">
        <SegmentedControl
          :model-value="assistantModeType"
          :options="assistantModeOptions"
          size="sm"
          aria-label="助手模式"
          @update:model-value="changeAssistantMode"
        />
        <div class="mode-switch" role="tablist" aria-label="助手视图">
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
            :class="{ active: assistantMode === 'history' }"
            role="tab"
            :aria-selected="assistantMode === 'history'"
            @click="showHistory"
          >
            历史
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
      </div>
      <p class="muted head-subtitle">{{ modeSubtitle }}</p>
    </header>

    <div v-if="error" class="card alert-line" role="alert">
      <span class="alert-text">{{ error }}</span>
      <button type="button" class="ghost compact line-close" aria-label="关闭错误提示" @click="error = ''">
        <ArtIcon name="close" tone="coral" :size="14" />
      </button>
    </div>
    <div v-if="notice" class="card notice-line" role="status">
      <span class="alert-text">{{ notice }}</span>
      <button type="button" class="ghost compact line-close" aria-label="关闭提示" @click="notice = ''">
        <ArtIcon name="close" tone="aqua" :size="14" />
      </button>
    </div>

    <main class="assistant-body">
      <AssistantSettings
        v-if="assistantMode === 'settings'"
        :configs="configs"
        :active-config="activeConfig"
        :config-form="configForm"
        :can-save-config="canSaveConfig"
        :has-config="hasConfig"
        :busy="busy"
        :model-options="modelOptions"
        :model-loading="modelLoading"
        :skills="skills"
        :selected-skill-id="selectedSkillId"
        :active-skill-id="activeSkillId"
        :skill-form="skillForm"
        :can-save-skill="canSaveSkill"
        @new-config="newConfig"
        @select-config="selectConfig"
        @save-config="saveConfig"
        @test-config="testConfig"
        @enable-config="enableConfig"
        @fetch-models="fetchModels"
        @new-skill="newSkill"
        @select-skill="selectSkill"
        @save-skill="saveSkill"
        @enable-skill="enableSkill"
        @import-skill="fileInput?.click()"
      />

      <AssistantHistory
        v-else-if="assistantMode === 'history'"
        :conversations="conversations"
        :history-loading="historyLoading"
        :active-id="conversationId"
        :interaction-busy="busy || uploadingFiles || attachingFiles"
        @open="openConversation"
        @new-chat="startNewChat"
        @rename="renameConversationById"
        @delete="deleteConversationById"
      />

      <AssistantChat
        v-else
        ref="chatRef"
        v-model="input"
        :messages="messages"
        :assistant-name="assistantName"
        :busy="busy"
        :uploading-files="uploadingFiles"
        :attaching-files="attachingFiles"
        :chat-attachments="chatAttachments"
        :pending-tokens="pendingTokens"
        :failed-text="failedChatText"
        @send="send"
        @retry="retryFailed"
        @dismiss-failed="failedChatText = ''"
        @first-confirm="firstConfirm"
        @second-confirm="secondConfirm"
        @remove-attachment="removeChatAttachment"
        @pick-chat-files="chatFileInput?.click()"
        @pick-ai-attachments="aiAttachmentInput?.click()"
        @open-settings="assistantMode = 'settings'"
      />
    </main>

    <!-- 隐藏文件输入保留在壳层：子组件通过事件让父层触发选择，请求逻辑不变 -->
    <input ref="chatFileInput" type="file" multiple hidden @change="onChatFiles" />
    <input ref="aiAttachmentInput" type="file" multiple hidden @change="onAiAttachmentFiles" />
    <input ref="fileInput" type="file" accept=".md,.txt" hidden @change="onSkillFile" />
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
  padding: 12px 18px 12px 12px;
  border-radius: var(--radius-pill);
  color: #fff;
  background: linear-gradient(135deg, var(--accent), var(--sea-400));
  box-shadow: var(--shadow-xl), 0 0 24px var(--accent-glow);
  transition: transform 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease;
  cursor: grab;
  touch-action: none;
}

.assistant-fab:hover {
  transform: translateY(-2px);
  filter: saturate(1.04);
  box-shadow: var(--shadow-xl), 0 0 30px var(--accent-glow);
}
.assistant-fab.dragging {
  cursor: grabbing;
  transition: none;
  user-select: none;
}
.assistant-fab.dragging:hover {
  transform: none;
}

.assistant-fab strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.assistant-fab :deep(.art-icon.tile) {
  color: #fff;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.42), rgba(255, 255, 255, 0.16)),
    rgba(255, 255, 255, 0.18);
  border-color: rgba(255, 255, 255, 0.46);
  box-shadow: var(--shadow-inset), 0 0 18px rgba(255, 255, 255, 0.22);
}

.assistant-layer {
  position: fixed;
  inset: 0;
  z-index: 210;
  background: transparent;
  pointer-events: none;
}

.assistant-layer.fullscreen {
  background: var(--overlay-bg);
  backdrop-filter: blur(5px);
  -webkit-backdrop-filter: blur(5px);
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
  background: color-mix(in srgb, var(--surface) 92%, white 8%);
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

.head-main,
.head-actions,
.head-switches {
  display: flex;
  gap: 12px;
}

.assistant-head {
  display: flex;
  flex-direction: column;
  gap: 10px;
  cursor: grab;
  touch-action: none;
  padding: 2px 2px 12px;
  border-bottom: 1px solid var(--border);
}

.head-main {
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-width: 0;
}

.head-switches {
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.head-subtitle {
  margin: 0;
  font-size: 12px;
}

.assistant-shell:not(.fullscreen) .assistant-head .muted {
  display: none;
}

.assistant-shell:not(.fullscreen) .page-title {
  gap: 8px;
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

.head-copy {
  min-width: 0;
  flex: 1;
}

.assistant-head .page-title {
  color: var(--text);
  min-width: 0;
}

.assistant-head .page-title span:last-child {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.assistant-shell.dragging .assistant-head {
  cursor: grabbing;
}

.assistant-shell.fullscreen .assistant-head {
  cursor: default;
}

.assistant-head h2 {
  margin: 0;
}

.assistant-head p {
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

.mode-switch {
  display: inline-grid;
  grid-template-columns: repeat(3, minmax(52px, 1fr));
  gap: 4px;
  padding: 4px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  box-shadow: var(--shadow-inset);
}

.mode-switch button {
  min-height: 30px;
  border-radius: 10px;
  box-shadow: none;
}

.mode-switch button.active {
  color: #fff;
  background: linear-gradient(135deg, var(--accent), var(--sea-400));
  box-shadow: 0 5px 16px var(--accent-glow);
}

.alert-line,
.notice-line {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 16px;
  font-weight: 600;
}

.alert-text {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}

.alert-line {
  color: var(--pri-high);
  background: color-mix(in srgb, var(--danger) 8%, transparent);
}

.notice-line {
  color: var(--accent-hover);
  background: var(--accent-soft);
}

.line-close {
  flex-shrink: 0;
  padding: 4px 8px;
}

@media (max-width: 980px) {
  .assistant-layer {
    background: transparent;
  }

  .assistant-layer.fullscreen {
    background: var(--overlay-bg);
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
}

@media (max-width: 640px) {
  .assistant-head .muted {
    display: none;
  }

  .head-actions {
    display: flex;
    width: auto;
    flex-wrap: nowrap;
  }

  .assistant-fab {
    right: 14px;
    bottom: 14px;
    width: 58px;
    height: 58px;
    padding: 0;
    justify-content: center;
    border-radius: 50%;
  }

  .assistant-fab strong {
    display: none;
  }

  .assistant-fab :deep(.art-icon.tile) {
    width: 40px;
    height: 40px;
  }

  .assistant-shell.fullscreen {
    inset: 8px;
  }
}

/* 悬浮窗独立窗口模式：填满窗口，header 原生拖动，精简布局适配窄窗 */
.assistant-shell.float-mode {
  position: absolute;
  inset: 0;
  right: auto;
  bottom: auto;
  width: 100%;
  height: 100%;
  padding: 10px;
  /* 透明窗口下 backdrop-filter 失效，改用不透明底色，避免透出桌面 */
  background: var(--surface-solid);
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}
.assistant-shell.float-mode .assistant {
  gap: 8px;
}
.assistant-shell.float-mode .assistant-head {
  -webkit-app-region: drag;
  padding: 2px 2px 8px;
  gap: 8px;
  /* 强制纵向：覆盖 @media(max-width:980px) 把 header 改成 row 的规则——
     悬浮窗 400px 会误触发该 media，使「标题/收起」行与「助手模式切换」行
     挤在同一水平行而重叠 */
  flex-direction: column;
}
.assistant-shell.float-mode .assistant-head .page-title .art-icon {
  display: none;
}
.assistant-shell.float-mode .assistant-head h2 {
  font-size: 15px;
}
.assistant-shell.float-mode .head-actions,
.assistant-shell.float-mode .head-switches {
  -webkit-app-region: no-drag;
  gap: 4px;
}
.assistant-shell.float-mode .mode-switch {
  grid-template-columns: repeat(3, minmax(40px, 1fr));
  padding: 3px;
  gap: 3px;
}
.assistant-shell.float-mode .mode-switch button {
  min-height: 26px;
  font-size: 12px;
  padding: 0 6px;
}
.assistant-shell.float-mode .fullscreen-action {
  display: none;
}

/* 悬浮窗窄窗：双助手切换与视图 tab 并排均分宽度，避免一个偏大、被 space-between 拉向两端而错位 */
.assistant-shell.float-mode .head-switches {
  flex-wrap: nowrap;
}

.assistant-shell.float-mode .head-switches .mode-switch {
  flex: 1 1 0;
  min-width: 0;
}
</style>

<!-- 对话/历史/设置子组件复用同名 class，样式集中在壳层维护。
     该块不设 scoped（scoped 无法覆盖子组件内部元素），统一以 .assistant-shell 作前缀避免外泄。 -->
<style>
.assistant-shell .panel-title,
.assistant-shell .panel-actions,
.assistant-shell .chat-head,
.assistant-shell .history-head,
.assistant-shell .pending-head,
.assistant-shell .pending-actions,
.assistant-shell .skill-tools {
  display: flex;
  gap: 12px;
}

.assistant-shell .chat-copy {
  min-width: 0;
}

.assistant-shell .chat-head h3 {
  overflow-wrap: anywhere;
}

.assistant-shell .panel-title p,
.assistant-shell .chat-head p,
.assistant-shell .history-head p,
.assistant-shell .pending-head p {
  margin: 4px 0 0;
}

.assistant-shell .panel-title,
.assistant-shell .chat-head,
.assistant-shell .history-head,
.assistant-shell .pending-head {
  align-items: flex-start;
  justify-content: space-between;
}

.assistant-shell .panel-title h3,
.assistant-shell .chat-head h3,
.assistant-shell .history-head h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 800;
}

.assistant-shell .panel-title .compact,
.assistant-shell .skill-tools .compact {
  flex-shrink: 0;
}

.assistant-shell .assistant-settings {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  /* 必须显式 max-content：auto 行在定高容器里会被拉伸分配剩余空间，
     <details> 卡片内容超出轨道高度，导致手风琴互相重叠 */
  grid-auto-rows: max-content;
  gap: 16px;
  padding: 2px 4px 4px;
  align-content: start;
  align-items: start;
}

.assistant-shell:not(.fullscreen) .assistant-settings {
  grid-template-columns: 1fr;
}

.assistant-shell .pill-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 14px 0;
}

.assistant-shell .pill {
  padding: 7px 13px;
  font-size: 12px;
  box-shadow: var(--shadow-inset);
}

.assistant-shell .pill.active,
.assistant-shell .pill.enabled {
  color: #fff;
  background: linear-gradient(135deg, var(--accent), var(--sea-400));
  box-shadow: 0 4px 14px var(--accent-glow), var(--shadow-inset);
}

.assistant-shell .form-grid {
  display: grid;
  gap: 10px;
}

.assistant-shell .assistant-settings label {
  display: grid;
  gap: 5px;
}

.assistant-shell .assistant-settings label span {
  color: var(--text-soft);
  font-size: 12px;
  font-weight: 700;
}

.assistant-shell .check-field {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  box-shadow: var(--shadow-inset);
}

.assistant-shell .check-field input {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  margin-top: 2px;
  accent-color: var(--accent);
}

.assistant-shell .check-copy {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.assistant-shell .check-copy strong {
  color: var(--text);
  font-size: 13px;
  line-height: 1.35;
}

.assistant-shell .check-copy small {
  color: var(--text-soft);
  font-size: 12px;
  line-height: 1.45;
}

.assistant-shell .wide-field {
  min-width: 0;
}

.assistant-shell .model-picker {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
}

.assistant-shell .model-picker input {
  min-width: 0;
}

.assistant-shell .model-select {
  margin-top: 6px;
}

.assistant-shell .headers-input,
.assistant-shell .persona-input {
  min-height: 82px;
  font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
}

.assistant-shell .native-options-input {
  min-height: 96px;
}

.assistant-shell .persona-input {
  min-height: 108px;
}

.assistant-shell .skill-input {
  min-height: 150px;
}

.assistant-shell .panel-actions,
.assistant-shell .skill-tools {
  align-items: center;
  flex-wrap: wrap;
  margin-top: 12px;
}

.assistant-shell .compact {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 7px 14px;
  font-size: 12px;
}

.assistant-shell .chat-panel {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-radius: var(--radius-sm);
  box-shadow: none;
  background: var(--surface);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

.assistant-shell .history-panel {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
  background: var(--surface);
}

.assistant-shell .history-head {
  flex-shrink: 0;
}

.assistant-shell .history-list {
  min-height: 0;
  overflow-y: auto;
  display: grid;
  gap: 8px;
  padding-right: 4px;
}

.assistant-shell .history-row {
  display: grid;
  gap: 4px;
  width: 100%;
  min-height: 76px;
  padding: 11px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  color: var(--text);
  text-align: left;
  box-shadow: var(--shadow-inset);
}

.assistant-shell .history-row.active {
  border-color: var(--border-strong);
  background: var(--accent-soft);
}

.assistant-shell .history-title,
.assistant-shell .history-snippet,
.assistant-shell .history-meta {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.assistant-shell .history-title {
  font-size: 14px;
  font-weight: 800;
}

.assistant-shell .history-snippet {
  color: var(--text);
  font-size: 13px;
}

.assistant-shell .history-meta,
.assistant-shell .history-empty {
  color: var(--text-soft);
  font-size: 12px;
  font-weight: 700;
}

.assistant-shell .history-empty {
  display: grid;
  place-items: center;
  min-height: 220px;
  text-align: center;
}

.assistant-shell .chat-stage {
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

.assistant-shell .messages {
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

.assistant-shell .empty-chat {
  margin: auto;
  text-align: center;
  color: var(--text-soft);
  max-width: 380px;
  display: grid;
  gap: 6px;
  padding: 28px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-2);
  box-shadow: var(--shadow-inset);
}

.assistant-shell .empty-title {
  color: var(--text);
  font-weight: 800;
}

.assistant-shell .message {
  position: relative;
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

.assistant-shell .message.user {
  align-self: flex-end;
  background: var(--accent-soft);
}

.assistant-shell .message.assistant,
.assistant-shell .message.system {
  align-self: flex-start;
}

.assistant-shell .message.system {
  border-color: var(--border-strong);
}

.assistant-shell .message-role {
  font-size: 12px;
  font-weight: 800;
  color: var(--text-soft);
}

.assistant-shell .message-content {
  display: block;
  margin-top: 5px;
  color: var(--text);
  font-size: 14px;
  line-height: 1.7;
  max-width: 100%;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.assistant-shell .message-paragraph,
.assistant-shell .message-list {
  margin: 0 0 8px;
}

.assistant-shell .message-paragraph:last-child,
.assistant-shell .message-list:last-child {
  margin-bottom: 0;
}

.assistant-shell .message-list {
  padding-left: 18px;
}

.assistant-shell .message-list li + li {
  margin-top: 3px;
}

.assistant-shell .tool-results {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}

.assistant-shell summary {
  cursor: pointer;
  color: var(--text-soft);
  font-size: 13px;
  font-weight: 700;
}

.assistant-shell pre {
  max-height: 180px;
  margin: 8px 0 0;
  overflow: auto;
  padding: 10px;
  border-radius: var(--radius-xs);
  background: var(--surface);
  color: var(--text);
  font-size: 12px;
}

.assistant-shell .pending-card {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid color-mix(in srgb, var(--danger) 38%, transparent);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--danger) 8%, transparent);
}

.assistant-shell .pending-head strong {
  color: var(--pri-high);
}

.assistant-shell .danger-dot {
  width: 12px;
  height: 12px;
  margin-top: 5px;
  border-radius: 50%;
  background: var(--pri-high);
  box-shadow: 0 0 0 5px color-mix(in srgb, var(--danger) 12%, transparent);
  flex-shrink: 0;
}

.assistant-shell .pending-summary {
  color: var(--text);
  font-weight: 600;
}

.assistant-shell .pending-preview {
  margin: 10px 0 0;
  padding-left: 18px;
  color: var(--text);
  font-size: 13px;
  line-height: 1.6;
}

.assistant-shell .pending-actions {
  justify-content: flex-end;
  margin-top: 10px;
}

.assistant-shell .composer {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.assistant-shell .composer-input {
  min-width: 0;
}

.assistant-shell .composer textarea {
  width: 100%;
  min-height: 58px;
  max-height: 104px;
  resize: none;
  overflow-y: auto;
}

.assistant-shell .upload-hint {
  margin-top: 5px;
  color: var(--text-soft);
  font-size: 12px;
  font-weight: 700;
}

.assistant-shell .attachment-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 7px;
}

.assistant-shell .attachment-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  padding: 5px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  background: var(--surface-2);
  color: var(--text);
  font-size: 12px;
  font-weight: 700;
  overflow-wrap: anywhere;
}

.assistant-shell .attachment-chip button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 22px;
  width: 22px;
  padding: 0;
  border-radius: var(--radius-pill);
  font-size: 11px;
  box-shadow: none;
  flex-shrink: 0;
}

.assistant-shell .composer-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.assistant-shell .composer-file-actions {
  display: flex;
  gap: 8px;
  min-width: 0;
}

.assistant-shell .composer-file-actions button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-width: 70px;
}

.assistant-shell .send-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: 82px;
  flex-shrink: 0;
}

@media (max-width: 980px) {
  .assistant-shell .assistant-settings {
    grid-template-columns: 1fr;
  }

  .assistant-shell .chat-panel {
    min-height: 0;
  }
}

@media (max-width: 640px) {
  .assistant-shell .panel-title .muted,
  .assistant-shell .chat-head .muted {
    display: none;
  }

  .assistant-shell .panel-actions,
  .assistant-shell .model-picker,
  .assistant-shell .composer {
    width: 100%;
    grid-template-columns: 1fr;
  }

  .assistant-shell .composer-toolbar {
    align-items: stretch;
  }

  .assistant-shell .composer-file-actions {
    flex: 1;
  }

  .assistant-shell .composer-file-actions button,
  .assistant-shell .send-action {
    flex: 1;
    min-width: 0;
  }

  .assistant-shell .composer button {
    width: 100%;
    min-width: 0;
  }

  .assistant-shell .message {
    width: fit-content;
  }
}

/* 悬浮窗窄窗：双助手分段控件拉满并均分两项，与右侧视图 tab 等宽对齐 */
.assistant-shell.float-mode .head-switches .seg-control {
  flex: 1 1 0;
  display: flex;
  min-width: 0;
}

.assistant-shell.float-mode .head-switches .seg-item {
  flex: 1 1 0;
  justify-content: center;
  padding: 5px 6px;
}
</style>
