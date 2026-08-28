<script setup>
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, toRaw, watch } from 'vue'
import {
  confirmAiAction,
  createAiConfig,
  createAiSkill,
  disableAiSkills,
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
  rejectAiAction,
  approveAiPlan,
  streamAiApprovePlan,
  rejectAiPlan,
  createAiGrant,
  listAiGrants,
  deleteAiGrant,
  streamAiChat,
  streamAiResume,
  cancelAiChat,
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
// 阶段 C1：会话模式 chat=正常对话；plan=计划模式（只读调研 + propose_plan 收尾）
const chatMode = ref('chat')
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
// 当前流式 agent run 的 id（meta 帧下发），用于中断链路：停止按钮调 /ai/chat/cancel
const activeRunId = ref(null)
// 运行状态行（阶段 1/2）：状态文案 + 已用秒数 + 累计 token 用量，仅 busy 期间有意义
const runStatus = ref('')
const runStartTs = ref(0)
const runElapsed = ref(0)
const runUsage = ref(null)
let runElapsedTimer = null

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
  let ordered = []

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
  const flushOrdered = () => {
    if (!ordered.length) return
    blocks.push({ type: 'ordered', items: ordered })
    ordered = []
  }
  const flushAll = () => {
    flushParagraph()
    flushList()
    flushOrdered()
  }

  for (const rawLine of lines) {
    const line = rawLine.trim()
    if (!line) {
      flushAll()
      continue
    }
    // heading：### / ## / # （# 后须有空格，避免误匹配话题标签）
    const heading = line.match(/^(#{1,3})\s+(.+)$/)
    if (heading) {
      flushAll()
      blocks.push({ type: 'heading', level: heading[1].length, lines: [tokenizeInline(heading[2])] })
      continue
    }
    // quote：> 文本
    const quoteMatch = line.match(/^>\s*(.*)$/)
    if (quoteMatch) {
      flushAll()
      blocks.push({ type: 'quote', lines: [tokenizeInline(quoteMatch[1] || '')] })
      continue
    }
    // unordered list：- 或 * 后跟空格
    const item = line.match(/^[-*]\s+(.+)$/)
    if (item) {
      flushParagraph()
      flushOrdered()
      list.push(tokenizeInline(item[1]))
      continue
    }
    // ordered list：1. / 2. 后跟空格
    const orderedItem = line.match(/^\d+[.)]\s+(.+)$/)
    if (orderedItem) {
      flushParagraph()
      flushList()
      ordered.push(tokenizeInline(orderedItem[1]))
      continue
    }
    // 普通段落行
    flushList()
    flushOrdered()
    paragraph.push(tokenizeInline(line))
  }

  flushAll()
  return blocks
}

// 行内 Markdown tokenize：把单行拆成 segments 数组，供模板用 v-for + {{ }} 渲染（不用 v-html）。
// 支持：**bold** / `code` / [text](url)。未匹配的文本作为 text segment。
function tokenizeInline(text) {
  const segments = []
  // 合并正则：按出现顺序匹配三种语法
  const regex = /(\*\*([^*]+)\*\*)|(`([^`]+)`)|(\[([^\]]+)\]\(([^)\s]+)\))/g
  let lastIndex = 0
  let match
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: 'text', text: text.slice(lastIndex, match.index) })
    }
    if (match[1]) {
      segments.push({ type: 'bold', text: match[2] })
    } else if (match[3]) {
      segments.push({ type: 'code', text: match[4] })
    } else if (match[5]) {
      segments.push({ type: 'link', text: match[6], href: match[7] })
    }
    lastIndex = regex.lastIndex
  }
  if (lastIndex < text.length) {
    segments.push({ type: 'text', text: text.slice(lastIndex) })
  }
  // 单段纯文本时返回字符串，兼容「无格式」快路径
  if (segments.length === 1 && segments[0].type === 'text') return segments[0].text
  return segments.length ? segments : text
}

function createMessage(message) {
  // meta 在后端是 JSON 字符串或对象（AIMessage.meta）；统一解析成对象，方便 AssistantMessage 读取 usage/elapsed
  let meta = message?.meta
  if (typeof meta === 'string') {
    try { meta = meta ? JSON.parse(meta) : {} } catch { meta = {} }
  }
  meta = meta || {}
  return {
    ...message,
    meta,
    // 历史消息的思维链存在 meta.reasoning：提升到顶层，与流式期间累积的 msg.reasoning 同一位
    reasoning:
      typeof message?.reasoning === 'string' && message.reasoning
        ? message.reasoning
        : meta.reasoning || '',
    blocks: message.content?.trim() ? parseMessageBlocks(message.content) : [],
  }
}

// ---- 运行状态行（阶段 1/2）：随 SSE 事件推进文案 + 实时计时 + token 累加 ----
function startRunStatus() {
  runStatus.value = '正在思考…'
  runStartTs.value = Date.now()
  runElapsed.value = 0
  runUsage.value = null
  if (runElapsedTimer) window.clearInterval(runElapsedTimer)
  runElapsedTimer = window.setInterval(() => {
    if (runStartTs.value) runElapsed.value = Math.floor((Date.now() - runStartTs.value) / 1000)
  }, 1000)
}

function stopRunStatus() {
  if (runElapsedTimer) { window.clearInterval(runElapsedTimer); runElapsedTimer = null }
  runStatus.value = ''
  runStartTs.value = 0
}

function toolFriendlyName(name) {
  const n = String(name || '')
  const MAP = {
    list_tasks: '查看任务', create_task: '创建任务', list_reminders: '查看提醒',
    create_reminder: '创建提醒', list_files: '查看资料', create_note_file: '创建资料',
    create_subtask: '创建子任务', create_subtasks: '创建子任务', list_subtasks: '查看子任务',
    attach_file_to_task: '关联资料', save_attachment_to_library: '保存附件',
    list_day_schedule: '查看日程', list_month_schedule: '查看月度日程', assign_task_to_day: '安排日程',
    list_habits: '查看习惯', create_habit: '创建习惯', check_in_habit: '习惯打卡',
    list_journal_entries: '查看日记', write_journal: '写日记',
    list_goals: '查看目标', create_goal: '创建目标', update_kr_progress: '更新 KR 进度',
    start_timer: '开始计时', stop_timer: '停止计时',
    update_task: '更新任务', update_file_notes: '更新资料备注',
    auto_plan_tasks: '自动排程', bulk_assign_tasks_to_days: '批量安排日程',
  }
  if (MAP[n]) return MAP[n]
  if (n.startsWith('mcp__')) return `MCP·${n.split('__').pop() || n}`
  return n || '工具'
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
    show_reasoning: true,
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
    show_reasoning: config.show_reasoning !== false,
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
    show_reasoning: configForm.value.show_reasoning !== false,
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
  // Esc/关闭按钮只关窗，不杀请求（阶段 5 职责分离）：
  // 进行中的 agent run 由「停止」按钮显式中断；关窗后流仍在后台跑，
  // 重新打开窗口仍能看到增量。组件卸载时才 abort（onBeforeUnmount）。
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
  savePendingTokens()
  failedChatText.value = ''
  assistantMode.value = 'chat'
  notice.value = '已开始新聊天'
  nextTick(scrollMessagesToBottom)
}

async function openConversation(row) {
  // 等待期允许翻历史/切换会话查看（只读），不阻塞进行中的请求
  if (!row || uploadingFiles.value || attachingFiles.value) return
  historyLoading.value = true
  error.value = ''
  try {
    const data = await getAiConversation(row.id)
    conversationId.value = data.id
    messages.value = (data.messages || []).map(createMessage)
    chatAttachments.value = []
    // 恢复该会话持久化的 token，只保留仍处于 pending/confirmed 态的 action
    const activeActionIds = []
    for (const msg of data.messages || []) {
      for (const act of msg.pending_actions || []) {
        if (act.status === 'pending' || act.status === 'confirmed') activeActionIds.push(act.id)
      }
    }
    pendingTokens.value = loadPendingTokens(activeActionIds)
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

async function disableSkills() {
  busy.value = true
  error.value = ''
  try {
    await disableAiSkills()
    activeSkillId.value = null
    selectedSkillId.value = null
    await load()
  } catch (err) {
    error.value = err.message || '停用失败'
  } finally {
    busy.value = false
  }
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
    // 后端 enable_skill 已写 active_skill_id，无需再调 updateAiConfig（FIX-8 去重复写入）
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

  // 阶段 FU-2.1：抽出共享 SSE 消费核心，approve_plan 复跑也复用同一套 onEvent 渲染。
  // runAgentStream 返回 { ok, assistantIndex }；调用方负责前置消息 push 与失败回滚。
  const ok = await runAgentStream(({ signal, onEvent }) => streamAiChat(
    {
      conversation_id: conversationId.value,
      message: cleanText,
      attachments: attachments.map((file) => ({ id: file.id })),
      mode: chatMode.value,
    },
    { signal, onEvent },
  ))

  if (!ok) {
    // 失败：移除用户消息占位、恢复输入
    messages.value.splice(messageIndex, 1)
    if (restoreToInput && !input.value.trim()) input.value = text || ''
    if (restoreToInput) failedChatText.value = text || ''
    return false
  }
  failedChatText.value = ''
  return true
}

// 阶段 FU-2.1：共享 SSE 消费核心——创建 assistant 占位、消费事件流、done 落稳。
// streamFn: (opts) => Promise；opts = { signal, onEvent }。
// 返回 true=成功落稳，false=失败/中断（调用方按需回滚用户消息）。
async function runAgentStream(streamFn) {
  const controller = new AbortController()
  chatAbortController.value = controller
  // 流式：push 占位 assistant 消息，text_delta 追加（节流渲染），tool 卡片增量，
  // done 帧权威替换为最终 reply/tool_results/pending_actions。
  const placeholder = createMessage({
    role: 'assistant',
    content: '',
    streaming: true,
    tool_results: [],
    pending_actions: [],
  })
  const assistantIndex = messages.value.push(placeholder) - 1
  let streamBuffer = ''
  let reasoningBuffer = ''
  let pendingRenderTimer = null
  const flushRender = () => {
    pendingRenderTimer = null
    const msg = messages.value[assistantIndex]
    if (!msg) return
    msg.content = streamBuffer
    msg.blocks = streamBuffer.trim() ? parseMessageBlocks(streamBuffer) : []
    if (reasoningBuffer) msg.reasoning = reasoningBuffer
  }
  const scheduleRender = () => {
    if (pendingRenderTimer) return
    pendingRenderTimer = window.setTimeout(flushRender, 50)
  }
  // tool 卡片：按 call_id 聚合，tool_call_start 建卡(running)，tool_result 就地更新
  const toolCardsByCallId = new Map()
  // 流中断/出错兜底：把仍在转圈的"执行中"卡片统一标记为已中断，避免无限旋转
  const settleRunningCards = () => {
    let touched = false
    for (const card of toolCardsByCallId.values()) {
      if (card._running) {
        card._running = false
        card.result = { ok: false, error: '已中断' }
        touched = true
      }
    }
    if (touched) {
      const msg = messages.value[assistantIndex]
      if (msg) msg.tool_results = [...toolCardsByCallId.values()]
    }
  }
  // 当前 run 工具名 → 进行中的调用数（用于 pending_confirmation 时统计"等待确认 N 项"）
  let runningToolCount = 0
  let pendingConfirmCount = 0

  // 发送即启动状态行：从"正在思考…"开始，随事件推进
  startRunStatus()

  try {
    await streamFn({
      signal: controller.signal,
      onEvent: (event, data) => {
        const msg = messages.value[assistantIndex]
        if (!msg || toRaw(msg) !== placeholder) return
        if (event === 'meta') {
          if (data?.conversation_id) conversationId.value = data.conversation_id
          if (data?.run_id) activeRunId.value = data.run_id
        } else if (event === 'text_delta') {
          streamBuffer += data?.delta || ''
          scheduleRender()
          // 正文本身即反馈：清除状态行（若因 tool_call_start 设过"正在调用…"）
          runStatus.value = ''
        } else if (event === 'reasoning_delta') {
          // 思维链增量（阶段 3）：累积到独立缓冲，随 50ms 节流统一渲染（与正文同节奏）
          if (data?.delta) {
            reasoningBuffer += data.delta
            scheduleRender()
          }
        } else if (event === 'usage') {
          // token 累计（阶段 2）：provider 回了就显示，没回（null/0）保持不显示
          if (data && Number(data.total_tokens) > 0) {
            runUsage.value = {
              prompt_tokens: Number(data.prompt_tokens) || 0,
              completion_tokens: Number(data.completion_tokens) || 0,
              total_tokens: Number(data.total_tokens) || 0,
            }
          }
        } else if (event === 'tool_call_start') {
          const callId = String(data?.call_id || `tc_${toolCardsByCallId.size}`)
          // 同一 call_id 会收到两次（先 name 后 args）：已存在则更新 args，否则建卡
          const existing = toolCardsByCallId.get(callId)
          if (existing) {
            if (data?.args && Object.keys(data.args).length) existing.args = data.args
          } else {
            toolCardsByCallId.set(callId, {
              tool: data?.name || '',
              args: {},
              result: { ok: false, pending: true },
              _callId: callId,
              _running: true,
            })
            runningToolCount += 1
          }
          msg.tool_results = [...toolCardsByCallId.values()]
          // 状态行：显示正在调用的工具（仅第一帧设，args 补发帧不覆盖）
          if (data?.name) runStatus.value = `正在调用 ${toolFriendlyName(data.name)}…`
        } else if (event === 'tool_result') {
          const callId = String(data?.call_id || '')
          let card = toolCardsByCallId.get(callId)
          if (!card) {
            card = { tool: data?.name || '', args: {}, _callId: callId }
            toolCardsByCallId.set(callId, card)
          }
          if (card._running) runningToolCount = Math.max(0, runningToolCount - 1)
          card._running = false
          card.result = {
            ok: !!data?.ok,
            skipped: !!data?.skipped,
            pending: !!data?.pending,
            error: data?.error,
            preview: data?.preview,
          }
          msg.tool_results = [...toolCardsByCallId.values()]
        } else if (event === 'pending_confirmation') {
          // 危险操作等待确认：后端发 {step, actions:[...]}，数量取 actions.length（此前误读不存在的 count 字段）
          const actionCount = Array.isArray(data?.actions) ? data.actions.length : 0
          pendingConfirmCount = actionCount || pendingConfirmCount + 1
          runStatus.value = `等待你确认 ${pendingConfirmCount} 项操作…`
        } else if (event === 'plan_proposed') {
          // 阶段 C1：plan 模式 agent 提交计划卡片 → 写入当前 assistant 消息，供 PlanCard 渲染
          if (data?.plan_card) msg.plan_card = data.plan_card
        } else if (event === 'work_plan') {
          // 阶段 C2：工作清单更新 → 写入当前 assistant 消息（最后一次覆盖）
          if (Array.isArray(data?.items)) msg.work_plan = data.items
        } else if (event === 'step_finish') {
          // 一步结束、下一轮开始：若此时正文缓冲仍空，回落到"正在思考…"
          if (!streamBuffer.trim() && runningToolCount === 0) runStatus.value = '正在思考…'
        } else if (event === 'done') {
          // 权威收敛帧：替换占位为最终态
          if (pendingRenderTimer) { clearTimeout(pendingRenderTimer); pendingRenderTimer = null }
          flushRender()
          if (data?.reasoning) msg.reasoning = data.reasoning
          msg.streaming = false
          msg.content = data?.reply ?? streamBuffer
          msg.blocks = msg.content?.trim() ? parseMessageBlocks(msg.content) : []
          const finalTools = Array.isArray(data?.tool_results) && data.tool_results.length
            ? data.tool_results
            : [...toolCardsByCallId.values()].map(({ tool, args, result }) => ({ tool, args, result }))
          msg.tool_results = finalTools
          msg.pending_actions = data?.pending_actions || []
          // 定格 usage/耗时到消息 meta（阶段 2/3）：历史消息刷新后仍可见
          const meta = msg.meta || {}
          if (data?.usage) meta.usage = data.usage
          else if (runUsage.value) meta.usage = runUsage.value
          if (data?.elapsed_ms) meta.elapsed_ms = data.elapsed_ms
          else if (runStartTs.value) meta.elapsed_ms = Date.now() - runStartTs.value
          if (data?.reasoning) meta.reasoning = data.reasoning
          if (Object.keys(meta).length) msg.meta = meta
        } else if (event === 'error') {
          msg.streaming = false
          if (streamBuffer) {
            msg.content = streamBuffer
            msg.blocks = streamBuffer.trim() ? parseMessageBlocks(streamBuffer) : []
          } else {
            msg.content = data?.message || '处理失败'
            msg.blocks = parseMessageBlocks(msg.content)
          }
          if (data?.message) error.value = data.message
          settleRunningCards()
        }
      },
    })
    await scrollMessagesToBottom()
    const finalMsg = messages.value[assistantIndex]
    const domains = domainsFromToolResults(finalMsg?.tool_results || [])
    if (finalMsg?.pending_actions?.length) domains?.push?.('resume')
    emit('changed', domains)
    return true
  } catch (err) {
    // 流式中断/失败：保留已收到的增量文本，标记非 streaming
    const msg = messages.value[assistantIndex]
    settleRunningCards()
    if (msg) {
      msg.streaming = false
      if (streamBuffer) {
        msg.content = streamBuffer
        msg.blocks = streamBuffer.trim() ? parseMessageBlocks(streamBuffer) : []
      } else if (controller.signal.aborted) {
        msg.content = '（已中断）'
        msg.blocks = parseMessageBlocks('（已中断）')
      }
      // 非中断的失败：占位若已有部分内容则保留（展示错误上下文）；空占位由调用方在回滚用户消息时一并清理
    }
    if (!controller.signal.aborted) {
      error.value = apiMessage(err)
    }
    return false
  } finally {
    if (pendingRenderTimer) { clearTimeout(pendingRenderTimer); pendingRenderTimer = null }
    if (chatAbortController.value === controller) chatAbortController.value = null
    activeRunId.value = null
    stopRunStatus()
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

// 停止当前 agent run：先请求后端中断（阻止继续烧 token），再 abort fetch 流。
// 中断是安全方向（已执行的副作用不回滚，仅停止后续步骤）。
async function stopChat() {
  const runId = activeRunId.value
  // 先请求后端中断（阻止继续烧 token + 让后端落库 interrupted），再 abort fetch。
  // 顺序关键：若先 abort，服务端检测到 disconnect 会直接关闭生成器，已累积进度不落库。
  if (runId) {
    try {
      await cancelAiChat(runId)
    } catch {
      // 中断请求失败不阻塞，下面仍 abort fetch
    }
  }
  chatAbortController.value?.abort()
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
  emit('changed', ['files'])
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

// 阶段 D1：首次确认时若勾选「以后都允许」，先创建 grant（不阻断确认主流程，失败仅 toast）
async function grantAction({ toolName }) {
  try {
    await createAiGrant(toolName, '')
    notice.value = `已允许「${toolName}」类操作以后自动执行`
  } catch (err) {
    // 授权失败不阻断确认主流程
    toast?.error?.(`授权保存失败：${apiMessage(err)}`)
  }
}

async function firstConfirm(action) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const res = await confirmAiAction(action.id)
    pendingTokens.value = { ...pendingTokens.value, [action.id]: res.confirm_token }
    savePendingTokens()
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
    savePendingTokens()
    emit('changed', domainsForAction(action))
    // 确认后尝试回灌续跑（若该轮有被暂缓的 safe 工具或模型需基于确认结果继续）
    await tryResumeConversation()
  } catch (err) {
    error.value = apiMessage(err)
  } finally {
    busy.value = false
  }
}

async function rejectAction(action) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const res = await rejectAiAction(action.id)
    if (res.action) updatePendingAction(action.id, res.action)
    else updatePendingAction(action.id, { status: 'rejected' })
    const nextTokens = { ...pendingTokens.value }
    delete nextTokens[action.id]
    pendingTokens.value = nextTokens
    savePendingTokens()
    await scrollMessagesToBottom()
    // 拒绝后同样尝试续跑，让模型得知「用户拒绝了该操作」并给出收尾回复
    await tryResumeConversation()
  } catch (err) {
    error.value = apiMessage(err)
  } finally {
    busy.value = false
  }
}

// 阶段 FU-2.1：批准计划——走 SSE 流式（工具卡片/工作清单实时呈现），与聊天主流体验一致。
// 复用 runAgentStream 的 onEvent 渲染；SSE 异常时回落非流式 approveAiPlan。
// approve 后强制切回 chat 模式（计划执行本身在 chat 模式下走 confirm 闸门）。
async function approvePlan({ messageId, steps }) {
  if (busy.value) return
  chatMode.value = 'chat'
  busy.value = true
  error.value = ''
  // 推一条用户消息：标注「按已批准计划执行」，让对话流可读
  messages.value.push(createMessage({ role: 'user', content: '按已批准的计划执行' }))
  await scrollMessagesToBottom()
  const ok = await runAgentStream(({ signal, onEvent }) => streamAiApprovePlan(messageId, steps, { signal, onEvent }))
  if (!ok) {
    // 流式失败：回落非流式（降级通道，保证 approve 至少能完成）
    try {
      const res = await approveAiPlan(messageId, steps)
      messages.value.push({
        role: 'assistant',
        content: res.reply || '计划已执行',
        blocks: (res.reply || '').trim() ? parseMessageBlocks(res.reply) : [],
        tool_results: res.tool_results || [],
        pending_actions: res.pending_actions || [],
        usage: res.usage || null,
      })
      for (const action of res.pending_actions || []) {
        pendingTokens.value[action.id] = null
      }
      savePendingTokens()
      await scrollMessagesToBottom()
    } catch (err) {
      error.value = apiMessage(err)
    }
  } else {
    // 流式成功：done 帧已落稳 pending_actions，同步 pending tokens
    const last = messages.value[messages.value.length - 1]
    for (const action of last?.pending_actions || []) {
      pendingTokens.value[action.id] = null
    }
    savePendingTokens()
  }
}

// 阶段 C1：拒绝计划——标记 rejected，不执行任何步骤，回一句话。
async function rejectPlan({ messageId, reason }) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    await rejectAiPlan(messageId, reason)
    // 更新对应消息的 plan_card 状态
    const msg = messages.value.find((m) => m.id === messageId)
    if (msg?.plan_card) msg.plan_card.status = 'rejected'
    await scrollMessagesToBottom()
  } catch (err) {
    error.value = apiMessage(err)
  } finally {
    busy.value = false
  }
}

// 确认/拒绝后回灌续跑（流式）：后端若无 checkpoint 或仍有 pending 则 done 帧 resumed:false（静默），
// resumed:true 时把续跑回复作为新 assistant 气泡流式追加。失败不阻塞确认/拒绝主流程。
async function tryResumeConversation() {
  if (!conversationId.value) return
  const controller = new AbortController()
  chatAbortController.value = controller
  const placeholder = createMessage({
    role: 'assistant',
    content: '',
    streaming: true,
    tool_results: [],
    pending_actions: [],
  })
  const assistantIndex = messages.value.push(placeholder) - 1
  let streamBuffer = ''
  let reasoningBuffer = ''
  let pendingRenderTimer = null
  const flushRender = () => {
    pendingRenderTimer = null
    const msg = messages.value[assistantIndex]
    if (!msg) return
    msg.content = streamBuffer
    msg.blocks = streamBuffer.trim() ? parseMessageBlocks(streamBuffer) : []
    if (reasoningBuffer) msg.reasoning = reasoningBuffer
  }
  const scheduleRender = () => {
    if (pendingRenderTimer) return
    pendingRenderTimer = window.setTimeout(flushRender, 50)
  }
  const toolCardsByCallId = new Map()
  // 流中断/出错兜底：把仍在转圈的"执行中"卡片统一标记为已中断，避免无限旋转
  const settleRunningCards = () => {
    let touched = false
    for (const card of toolCardsByCallId.values()) {
      if (card._running) {
        card._running = false
        card.result = { ok: false, error: '已中断' }
        touched = true
      }
    }
    if (touched) {
      const msg = messages.value[assistantIndex]
      if (msg) msg.tool_results = [...toolCardsByCallId.values()]
    }
  }
  let runningToolCount = 0
  let pendingConfirmCount = 0
  startRunStatus()
  try {
    await streamAiResume(conversationId.value, {
      signal: controller.signal,
      onEvent: (event, data) => {
        const msg = messages.value[assistantIndex]
        if (!msg || toRaw(msg) !== placeholder) return
        if (event === 'meta') {
          if (data?.run_id) activeRunId.value = data.run_id
        } else if (event === 'text_delta') {
          streamBuffer += data?.delta || ''
          scheduleRender()
          runStatus.value = ''
        } else if (event === 'reasoning_delta') {
          if (data?.delta) {
            reasoningBuffer += data.delta
            scheduleRender()
          }
        } else if (event === 'usage') {
          if (data && Number(data.total_tokens) > 0) {
            runUsage.value = {
              prompt_tokens: Number(data.prompt_tokens) || 0,
              completion_tokens: Number(data.completion_tokens) || 0,
              total_tokens: Number(data.total_tokens) || 0,
            }
          }
        } else if (event === 'tool_call_start') {
          const callId = String(data?.call_id || `tc_${toolCardsByCallId.size}`)
          const existing = toolCardsByCallId.get(callId)
          if (existing) {
            if (data?.args && Object.keys(data.args).length) existing.args = data.args
          } else {
            toolCardsByCallId.set(callId, {
              tool: data?.name || '', args: {}, _callId: callId, _running: true,
              result: { ok: false, pending: true },
            })
            runningToolCount += 1
          }
          msg.tool_results = [...toolCardsByCallId.values()]
          if (data?.name) runStatus.value = `正在调用 ${toolFriendlyName(data.name)}…`
        } else if (event === 'tool_result') {
          const callId = String(data?.call_id || '')
          let card = toolCardsByCallId.get(callId)
          if (!card) {
            card = { tool: data?.name || '', args: {}, _callId: callId }
            toolCardsByCallId.set(callId, card)
          }
          if (card._running) runningToolCount = Math.max(0, runningToolCount - 1)
          card._running = false
          card.result = {
            ok: !!data?.ok, skipped: !!data?.skipped, pending: !!data?.pending,
            error: data?.error, preview: data?.preview,
          }
          msg.tool_results = [...toolCardsByCallId.values()]
        } else if (event === 'pending_confirmation') {
          const actionCount = Array.isArray(data?.actions) ? data.actions.length : 0
          pendingConfirmCount = actionCount || pendingConfirmCount + 1
          runStatus.value = `等待你确认 ${pendingConfirmCount} 项操作…`
        } else if (event === 'plan_proposed') {
          if (data?.plan_card) msg.plan_card = data.plan_card
        } else if (event === 'work_plan') {
          if (Array.isArray(data?.items)) msg.work_plan = data.items
        } else if (event === 'step_finish') {
          if (!streamBuffer.trim() && runningToolCount === 0) runStatus.value = '正在思考…'
        } else if (event === 'done') {
          // resumed:false 时静默移除占位（无续跑内容）
          if (data?.resumed === false) {
            messages.value.splice(assistantIndex, 1)
            return
          }
          if (pendingRenderTimer) { clearTimeout(pendingRenderTimer); pendingRenderTimer = null }
          flushRender()
          if (data?.reasoning) msg.reasoning = data.reasoning
          msg.streaming = false
          msg.content = data?.reply ?? streamBuffer
          msg.blocks = msg.content?.trim() ? parseMessageBlocks(msg.content) : []
          const finalTools = Array.isArray(data?.tool_results) && data.tool_results.length
            ? data.tool_results
            : [...toolCardsByCallId.values()].map(({ tool, args, result }) => ({ tool, args, result }))
          msg.tool_results = finalTools
          msg.pending_actions = data?.pending_actions || []
          const meta = msg.meta || {}
          if (data?.usage) meta.usage = data.usage
          else if (runUsage.value) meta.usage = runUsage.value
          if (data?.elapsed_ms) meta.elapsed_ms = data.elapsed_ms
          else if (runStartTs.value) meta.elapsed_ms = Date.now() - runStartTs.value
          if (data?.reasoning) meta.reasoning = data.reasoning
          if (Object.keys(meta).length) msg.meta = meta
        } else if (event === 'error') {
          msg.streaming = false
          if (streamBuffer) {
            msg.content = streamBuffer
            msg.blocks = streamBuffer.trim() ? parseMessageBlocks(streamBuffer) : []
          } else {
            msg.content = data?.message || '继续处理失败'
            msg.blocks = parseMessageBlocks(msg.content)
          }
          settleRunningCards()
        }
      },
    })
    await scrollMessagesToBottom()
    const finalMsg = messages.value[assistantIndex]
    if (finalMsg) emit('changed', domainsFromToolResults(finalMsg.tool_results || []))
  } catch (err) {
    // 续跑失败不阻塞确认/拒绝主流程：保留已收到的增量，静默标记
    const msg = messages.value[assistantIndex]
    settleRunningCards()
    if (msg) {
      msg.streaming = false
      if (!streamBuffer) {
        messages.value.splice(assistantIndex, 1)
      } else {
        msg.content = streamBuffer
        msg.blocks = streamBuffer.trim() ? parseMessageBlocks(streamBuffer) : []
      }
    }
    notice.value = `继续处理失败：${apiMessage(err)}`
  } finally {
    if (pendingRenderTimer) { clearTimeout(pendingRenderTimer); pendingRenderTimer = null }
    if (chatAbortController.value === controller) chatAbortController.value = null
    activeRunId.value = null
    stopRunStatus()
  }
}

// ---- 危险操作 → 影响域映射（用于按域刷新看板，而非全量重载）----
const ACTION_DOMAINS = {
  delete_task: ['tasks'], update_task: ['tasks'], bulk_update_tasks: ['tasks'],
  bulk_delete_tasks: ['tasks'], empty_trash: ['tasks'],
  delete_file: ['files'], update_file_notes: ['files'], bulk_delete_files: ['files'],
  attach_file_to_task: ['tasks', 'files'], detach_file_from_task: ['tasks', 'files'],
  import_web_resources: ['files'],
  update_schedule_entry: ['schedule'], delete_schedule_entry: ['schedule'],
  bulk_assign_tasks_to_days: ['schedule'], auto_plan_tasks: ['schedule'],
  create_skill: [], create_mcp_server: [], mcp_tool_call: [],
}

function domainsForAction(action) {
  return ACTION_DOMAINS[action?.action_type] || undefined
}

function domainsFromToolResults(toolResults) {
  const TOOL_DOMAINS = {
    create_task: 'tasks', list_tasks: 'tasks', create_reminder: 'tasks', list_reminders: 'tasks',
    create_subtask: 'tasks', create_subtasks: 'tasks', list_subtasks: 'tasks',
    assign_task_to_day: 'schedule', list_day_schedule: 'schedule', list_month_schedule: 'schedule',
    create_note_file: 'files', list_files: 'files', attach_file_to_task: 'files',
    save_attachment_to_library: 'files',
    check_in_habit: 'habits', create_habit: 'habits', list_habits: 'habits',
    write_journal: 'journal', list_journal_entries: 'journal',
    list_goals: 'goals', create_goal: 'goals', update_kr_progress: 'goals',
    start_timer: 'timer', stop_timer: 'timer',
  }
  const domains = new Set()
  for (const item of toolResults || []) {
    const name = String(item?.tool || '')
    const domain = TOOL_DOMAINS[name]
    if (domain) domains.add(domain)
    else if (name.startsWith('mcp__')) domains.add('files')
  }
  return domains.size ? [...domains] : undefined
}

// ---- 待确认 token 的 sessionStorage 持久化（按会话隔离，刷新不丢失）----
function pendingTokensStorageKey() {
  return `ai-pending-tokens:${conversationId.value ?? 'new'}`
}

function savePendingTokens() {
  try {
    const raw = JSON.stringify(pendingTokens.value || {})
    if (raw === '{}') sessionStorage.removeItem(pendingTokensStorageKey())
    else sessionStorage.setItem(pendingTokensStorageKey(), raw)
  } catch { /* sessionStorage 不可用时静默降级为内存态 */ }
}

function loadPendingTokens(activeActionIds) {
  try {
    const raw = sessionStorage.getItem(pendingTokensStorageKey())
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return {}
    // 过滤脏 token：只保留当前消息里仍处于 pending/confirmed 态的 action 对应 token
    const active = new Set(activeActionIds || [])
    const cleaned = {}
    for (const [id, token] of Object.entries(parsed)) {
      if (active.has(Number(id)) && token) cleaned[id] = token
    }
    return cleaned
  } catch {
    return {}
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

// notice 自动 4 秒消失；错误横幅不自动消失（避免长任务失败时提示一闪而过），仅手动关闭
let noticeTimer = null
watch(notice, (value) => {
  window.clearTimeout(noticeTimer)
  noticeTimer = null
  if (value) noticeTimer = window.setTimeout(() => { notice.value = '' }, 4000)
})

onBeforeUnmount(() => {
  chatAbortController.value?.abort()
  window.clearTimeout(noticeTimer)
  if (runElapsedTimer) { window.clearInterval(runElapsedTimer); runElapsedTimer = null }
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
        @disable-skills="disableSkills"
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
        :run-status="runStatus"
        :run-elapsed="runElapsed"
        :run-usage="runUsage"
        :chat-mode="chatMode"
        :ai-available="hasEnabledConfig"
        @send="send"
        @stop="stopChat"
        @retry="retryFailed"
        @dismiss-failed="failedChatText = ''"
        @first-confirm="firstConfirm"
        @second-confirm="secondConfirm"
        @reject="rejectAction"
        @remove-attachment="removeChatAttachment"
        @pick-chat-files="chatFileInput?.click()"
        @pick-ai-attachments="aiAttachmentInput?.click()"
        @set-mode="(m) => (chatMode = m)"
        @approve-plan="approvePlan"
        @reject-plan="rejectPlan"
        @grant-action="grantAction"
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

/* 悬浮窗独立窗口模式：填满窗口、不透明底色、header 原生拖动、隐藏全屏。
   展开尺寸已与基础壳层设计值对齐（560×680），故不再做字号/gap/padding 瘦身，
   让面板回落到与程序内展开态一致的基础样式。仅保留「窗口语境」必需的覆盖。 */
.assistant-shell.float-mode {
  position: absolute;
  inset: 0;
  right: auto;
  bottom: auto;
  width: 100%;
  height: 100%;
  padding: 14px; /* 与基础 .assistant-shell 一致 */
  /* 透明窗口下 backdrop-filter 失效，改用不透明底色，避免透出桌面 */
  background: var(--surface-solid);
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}
.assistant-shell.float-mode .assistant-head {
  -webkit-app-region: drag;
  /* 强制纵向：覆盖 @media(max-width:980px) 把 header 改成 row 的规则--
     悬浮窗展开后虽为 560px，仍恒 <980px 会误触发该 media，使「标题/收起」行
     与「助手模式切换」行挤在同一水平行而重叠。保留纵向 = 与程序内宽屏一致。 */
  flex-direction: column;
}
.assistant-shell.float-mode .head-actions,
.assistant-shell.float-mode .head-switches {
  -webkit-app-region: no-drag;
}
.assistant-shell.float-mode .fullscreen-action {
  display: none; /* 悬浮窗为独立 OS 窗口，无需窗口内全屏 */
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

.assistant-shell .message-ordered {
  margin: 0 0 8px;
  padding-left: 22px;
}

.assistant-shell .message-ordered:last-child {
  margin-bottom: 0;
}

.assistant-shell .message-heading {
  margin: 0 0 6px;
  font-weight: 800;
  line-height: 1.4;
}

.assistant-shell .message-heading.level-1 { font-size: 17px; }
.assistant-shell .message-heading.level-2 { font-size: 15px; }
.assistant-shell .message-heading.level-3 { font-size: 14px; }

.assistant-shell .message-quote {
  margin: 0 0 8px;
  padding: 4px 12px;
  border-left: 3px solid var(--border-strong);
  color: var(--text-soft);
  font-size: 13px;
}

.assistant-shell .message-quote:last-child {
  margin-bottom: 0;
}

.assistant-shell .message-content code {
  padding: 1px 5px;
  border-radius: var(--radius-xs);
  background: var(--surface-2);
  font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
  font-size: 12.5px;
}

.assistant-shell .message-content a {
  color: var(--accent-hover);
  text-decoration: underline;
  text-underline-offset: 2px;
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
</style>
