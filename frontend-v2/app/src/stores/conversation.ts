/** Window selection, durable drafts and history; each async reply has a view owner. */
import { defineStore } from 'pinia'
import { watch } from 'vue'
import type { AttachmentMeta, ConversationMessage, ConversationSummary } from '../api/ai'
import { getConversationMessages, listConversations, uploadAttachment } from '../api/ai'
import type { SteerAccepted } from '../api/contracts/events'
import { steerConversation } from '../api/steer'
import { getConversationState, getWorkspace, putWorkspace, type ConversationState, type Draft } from '../api/sessions'
import { setSteerAcceptedListener, useRunStore } from './run'
import type { UserAnswer } from '../api/userInput'

/** 待发队列的 localStorage 键前缀（按会话 id 隔离；'new' 表示尚未落库的新会话，与草稿同口径）。 */
const QUEUE_KEY_PREFIX = 'zhishi:queued-messages:'

/** 发送选项。排队场景仅保留文本：附件/计划等一次性意图不随队列入队。 */
interface SendMessageOptions {
  attachmentIds?: number[]
  planMode?: boolean
  brainstormMode?: boolean
  researchProjectId?: number
}

/** 运行中插话的乐观条目：POST 受理前可撤回；凭 token 与 SteerAccepted 事件对账。 */
export interface SteerEntry {
  /** 前端自生成随机串：steer 请求与 steer_accepted 事件的对账键 */
  token: string
  text: string
  /** steer 响应里的 run id；null = POST 尚未返回（可撤回窗口） */
  runId: string | null
  /** steer_accepted 回填的落库行 id；null = 尚未确认注入（run 结束后需回退补发） */
  messageId: number | null
}

/** 在途 steer POST 的 AbortController（token → controller；非响应式，撤回/切换会话时中断）。 */
const steerAborts = new Map<string, AbortController>()

/** 生成插话对账 token（crypto.randomUUID 优先；后端限 64 字符内）。 */
function newSteerToken(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  } catch { /* 非安全上下文等，走回退 */ }
  return `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}

/** 读取落盘队列（脏数据一律视为空）；存储不可用返回 null。 */
function readStoredQueue(key: string): string[] | null {
  try {
    if (typeof localStorage === 'undefined') return null
    const raw = localStorage.getItem(key)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return null
    return parsed.filter((x): x is string => typeof x === 'string')
  } catch { return null }
}

/** 会话切换后补删已送达的队首消息（防下次回到该会话时重复发送）。 */
function dropStoredMessage(cid: number | null, message: string): void {
  try {
    if (typeof localStorage === 'undefined') return
    const key = QUEUE_KEY_PREFIX + String(cid ?? 'new')
    const rest = readStoredQueue(key) ?? []
    const index = rest.indexOf(message)
    if (index === -1) return
    rest.splice(index, 1)
    if (rest.length) localStorage.setItem(key, JSON.stringify(rest))
    else localStorage.removeItem(key)
  } catch { /* 存储不可用时忽略 */ }
}

export const useConversationStore = defineStore('conversation', {
  state: () => ({
    brainstormModes: {} as Record<string, boolean>,
    questionDrafts: {} as Record<string, Record<string, UserAnswer>>,
    conversations: [] as ConversationSummary[], activeId: null as number | null,
    messages: [] as ConversationMessage[], loading: false, error: null as string | null,
    draftText: '', draftAttachments: [] as AttachmentMeta[], drafts: {} as Record<string, Draft>,
    sentEchoAttachments: [] as AttachmentMeta[], uploading: false, pendingUploads: 0,
    sending: false, viewVersion: 0, initialized: false, initializing: false,
    surface: typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('widget') === '1' ? 'widget' : 'main',
    workspaceRevision: 0, savingWorkspace: false, workspaceDirty: false,
    persistenceError: null as string | null,
    sessionState: null as ConversationState | null, syncing: false,
    /** 当前会话的待发队列：run 进行中入队的消息，run 正常收敛后自动依次续发。 */
    queuedMessages: [] as string[],
    /**
     * 运行中插话（steering）的乐观条目：本地 run 活跃时发送的消息先挂这里（QueueBar
     * 显示「待注入」），POST /steer 受理后等 steer_accepted 凭 token 确认（变「已注入」）。
     * 仅存内存、随会话切换清空——已确认的消息后端已落库，未确认的由 run 终态收敛回退补发。
     */
    steerEntries: [] as SteerEntry[],
    /** 队列续发的 run 终态监听只挂一次（随 pinia 实例存活，见 armQueueDispatch）。 */
    queueDispatchArmed: false,
    /** 防止 watcher 触发与队内循环重入导致同一条消息重复发送。 */
    queueDispatching: false,
  }),
  getters: {
    activeBrainstormMode(s): boolean {
      const key = String(s.activeId ?? 'new')
      if (key in s.brainstormModes) return s.brainstormModes[key]!
      const lastUser = [...s.messages].reverse().find(message => message.role === 'user')
      return lastUser?.display?.brainstorm_mode === true
    },
    activeTitle(s): string { return s.conversations.find(c => c.id === s.activeId)?.title ?? (s.activeId === null ? '新对话' : `会话 ${s.activeId}`) },
    attachmentIds(s): number[] { return s.draftAttachments.map(a => a.id) },
    remoteRunId(s): string | null { return s.sessionState?.conversation_id === s.activeId ? s.sessionState.active_run_id : null },
  },
  actions: {
    setBrainstormMode(value: boolean): void { this.brainstormModes[String(this.activeId ?? 'new')] = value },
    async initialize(): Promise<void> {
      if (this.initialized || this.initializing) return
      this.initializing = true
      this.armQueueDispatch()
      const version = this.viewVersion
      try {
        const saved = await getWorkspace(this.surface)
        this.workspaceRevision = saved.revision
        if (version === this.viewVersion && !this.sending && !this.draftText && !this.draftAttachments.length) {
          this.drafts = saved.state.drafts
          this.questionDrafts = saved.state.question_drafts ?? {}
          this.loadDraft(null)
          this.loadQueue()
          if (saved.state.active_id !== null) await this.select(saved.state.active_id)
        }
        this.initialized = true
      } catch (e) { this.persistenceError = `窗口恢复失败：${e instanceof Error ? e.message : String(e)}` }
      finally { this.initializing = false }
      await this.refresh()
      await this.syncState()
    },
    rememberDraft(): void {
      const key = String(this.activeId ?? 'new')
      if (this.draftText || this.draftAttachments.length) this.drafts[key] = { text: this.draftText, attachments: this.draftAttachments.map(a => ({ id: a.id, name: a.name })) }
      else delete this.drafts[key]
    },
    loadDraft(cid: number | null): void {
      const draft = this.drafts[String(cid ?? 'new')]
      this.draftText = draft?.text ?? ''
      this.draftAttachments = draft?.attachments.map(a => ({ ...a })) ?? []
    },
    saveDraft(): void {
      this.rememberDraft()
      if (!this.initialized) return
      this.workspaceDirty = true
      void this.flushWorkspace()
    },
    saveQuestionDraft(id: number, answers: Record<string, UserAnswer> | null): void {
      if (answers) this.questionDrafts[String(id)] = JSON.parse(JSON.stringify(answers))
      else delete this.questionDrafts[String(id)]
      if (!this.initialized) return
      this.workspaceDirty = true
      void this.flushWorkspace()
    },
    async flushWorkspace(): Promise<void> {
      if (this.savingWorkspace || !this.initialized) return
      this.savingWorkspace = true
      try {
        while (this.workspaceDirty) {
          this.workspaceDirty = false
          const state = JSON.parse(JSON.stringify({ active_id: this.activeId, drafts: this.drafts, question_drafts: this.questionDrafts }))
          const saved = await putWorkspace(this.surface, { revision: this.workspaceRevision, state })
          this.workspaceRevision = saved.revision
          this.persistenceError = null
        }
      } catch (e) {
        this.persistenceError = `草稿尚未保存：${e instanceof Error ? e.message : String(e)}`
        this.workspaceDirty = true
      } finally { this.savingWorkspace = false }
    },
    async refresh(): Promise<void> {
      try { this.conversations = await listConversations() }
      catch (e) { this.error = e instanceof Error ? e.message : '会话列表加载失败' }
    },
    async select(id: number): Promise<void> {
      const version = ++this.viewVersion
      this.loading = true
      this.error = null
      this.armQueueDispatch()
      try {
        const messages = await getConversationMessages(id)
        if (this.viewVersion !== version) return
        this.rememberDraft()
        this.persistQueue() // 旧会话队列先落盘
        this.clearSteerEntries() // 插话乐观条目归属旧会话视图，切换即清（在途 POST 一并中断）
        this.activeId = id
        this.messages = messages
        this.sessionState = null
        this.loadQueue() // 载入目标会话的待发队列
        this.loadDraft(id)
        this.pendingUploads = 0
        this.uploading = false
        this.sentEchoAttachments = []
        const run = useRunStore()
        if (!run.hasLiveStream() && !this.sending) run.reset(id)
        this.saveDraft()
      } catch (e) { if (this.viewVersion === version) this.error = e instanceof Error ? e.message : '会话加载失败，当前消息仍保留' }
      finally { if (this.viewVersion === version) this.loading = false }
      if (this.initialized && this.viewVersion === version) await this.syncState()
    },
    startNew(): void {
      const run = useRunStore()
      if (run.hasLiveStream() || this.sending) return
      delete this.brainstormModes.new
      this.rememberDraft()
      this.persistQueue()
      this.clearSteerEntries()
      this.viewVersion++
      run.reset(null)
      this.activeId = null
      this.error = null
      this.loading = false
      this.messages = []
      this.sessionState = null
      this.pendingUploads = 0
      this.uploading = false
      this.loadDraft(null)
      this.loadQueue()
      this.sentEchoAttachments = []
      this.saveDraft()
    },
    stageSentEcho(attachments: AttachmentMeta[]): void { this.sentEchoAttachments = attachments.map(a => ({ id: a.id, name: a.name })) },
    attachFromRun(cid: number): void {
      if (this.activeId === cid) return
      this.persistQueue()
      this.clearSteerEntries()
      this.activeId = cid
      this.messages = []
      this.sessionState = null
      this.loadQueue()
      this.saveDraft()
      void this.refresh()
    },
    async syncState(): Promise<void> {
      const cid = this.activeId, version = this.viewVersion, run = useRunStore()
      if (cid === null || this.syncing || this.loading || this.sending || run.hasLiveStream()) return
      this.syncing = true
      try {
        const state = await getConversationState(cid)
        const messages = await getConversationMessages(cid)
        if (this.activeId !== cid || this.viewVersion !== version || this.sending || run.hasLiveStream()) return
        this.messages = messages
        this.dedupeSteered()
        this.sessionState = state
        run.restoreState(state)
      } catch (e) { if (this.activeId === cid && this.viewVersion === version) this.error = e instanceof Error ? e.message : '会话同步失败' }
      finally { this.syncing = false }
    },
    async sendMessage(message: string, opts: SendMessageOptions = {}): Promise<void> {
      const run = useRunStore()
      this.armQueueDispatch()
      if (this.sending) return // 发送进行中：维持原行为（静默忽略，不重复入队）
      if (run.isActive && run.conversationId === this.activeId && this.activeId !== null) {
        // 本地 run 活跃：运行中插话（steering）——下一次工具调用结束后的模型请求前注入当轮，
        // 模型即席消化；409（run 恰好已结束）/异常时在 steerMessage 内回退常规发送
        await this.steerMessage(message)
        return
      }
      if (run.isActive || this.remoteRunId) {
        // 无本地流反馈的排队场景（远端窗口的 run / 新会话）：维持 v1 队列，run 收敛后自动续发
        // （远端 run 的 steer_accepted 事件到不了本窗口，无法对账，不能走插话路径）
        this.enqueueMessage(message)
        return
      }
      await this.dispatchMessage(message, opts)
    },
    /** 实际发送（原 sendMessage 主体）。返回服务端是否受理（onConversationStarted 确认接收）。 */
    async dispatchMessage(message: string, opts: SendMessageOptions = {}): Promise<boolean> {
      const run = useRunStore()
      const version = this.viewVersion, conversationId = this.activeId
      // 直发路径 opts.attachmentIds 即整个附件盘（与原行为一致）；排队续发传 []，不动用户的附件盘
      const attachments = this.draftAttachments
        .filter(a => !opts.attachmentIds || opts.attachmentIds.includes(a.id))
        .map(a => ({ ...a }))
      this.sending = true
      this.error = null
      let accepted = false
      try {
        if (conversationId !== null) {
          const history = await getConversationMessages(conversationId)
          if (this.viewVersion !== version) return false
          this.messages = history
          this.dedupeSteered() // 插话落库行已进历史：移除对应乐观条目，避免与正式消息重复
        }
        this.stageSentEcho(attachments)
        await run.sendMessage(message, { ...opts, conversationId, onConversationStarted: id => {
          this.brainstormModes[String(id)] = opts.brainstormMode ?? false
          if (conversationId === null) delete this.brainstormModes.new
          accepted = true
          if (this.viewVersion === version) {
            if (this.draftText.trim() === message) this.draftText = ''
            this.draftAttachments = this.draftAttachments.filter(a => !attachments.some(sent => sent.id === a.id))
            delete this.drafts[String(conversationId ?? 'new')]
            this.attachFromRun(id)
            this.saveDraft()
          } else {
            // A late acceptance belongs to its original view; retain any unsent edits.
            const draft = this.drafts[String(conversationId ?? 'new')]
            if (draft?.text.trim() === message) delete this.drafts[String(conversationId ?? 'new')]
            this.saveDraft()
          }
        } })
        if (!accepted) run.sentMessage = null
      } catch (e) { if (this.viewVersion === version) this.error = e instanceof Error ? e.message : '发送失败' }
      finally { this.sending = false }
      if (this.initialized) { await this.syncState(); void this.refresh() }
      return accepted
    },
    /** 挂载 run 终态监听与插话对账（幂等）：busy → 空闲收敛时回退补发未注入的插话并续发队列。 */
    armQueueDispatch(): void {
      if (this.queueDispatchArmed) return
      this.queueDispatchArmed = true
      const run = useRunStore()
      setSteerAcceptedListener(ev => this.onSteerAccepted(ev))
      watch(
        () => [run.isActive, run.phase, this.remoteRunId] as const,
        (cur, prev) => {
          const wasBusy = prev[0] || !!prev[2]
          const isBusy = cur[0] || !!cur[2]
          if (!wasBusy || isBusy) return
          if (cur[1] === 'cancelled') {
            // 用户主动叫停：未注入的插话转常规待发队列（原样保留由用户处置），不自动续发
            this.parkUnconfirmedSteers()
            return
          }
          // 正常收敛与错误收敛都回退：未确认注入的插话模型从没见过，必须作为普通消息补发
          void this.settleSteerQueue()
        },
      )
    },
    /** 运行中插话：乐观条目（待注入）+ 立即清草稿 + POST steer。
     * 409（run 恰好已结束）/网络异常 → 移除条目并回退常规发送。 */
    async steerMessage(message: string): Promise<void> {
      const run = useRunStore()
      const text = message.trim()
      if (!text) return
      const cid = this.activeId
      if (cid === null) { this.enqueueMessage(text); return }
      const token = newSteerToken()
      const entry: SteerEntry = { token, text, runId: null, messageId: null }
      this.steerEntries.push(entry)
      // 插话成功即清输入框草稿；等值守卫保证程序化调用（如黑板「让 AI 修复」）不动草稿
      if (this.draftText.trim() === text) {
        this.draftText = ''
        this.saveDraft()
      }
      const abort = new AbortController()
      steerAborts.set(token, abort)
      try {
        const out = await steerConversation(cid, { text, token }, abort.signal)
        entry.runId = out.run_id // 已受理：进注入队列，不可再撤回；等 steer_accepted 确认
      } catch {
        steerAborts.delete(token)
        if (entry.messageId !== null) return // SSE 先于响应确认了受理：条目保留，无需回退
        const index = this.steerEntries.indexOf(entry)
        if (index !== -1) this.steerEntries.splice(index, 1)
        else return // 已被移除（撤回/切换/终态收敛接管）：命运归移除方，不重复回退
        if (abort.signal.aborted) return // 用户撤回：静默丢弃，不回退发送
        // 回退常规发送：run 仍活跃/直发占用中 → v1 队列（下次收敛自动续发）；空闲 → 直发。
        // 不再回到 steerMessage：本地活跃态与服务端 409 持续背离时会无限循环。
        if (this.sending || run.isActive || this.remoteRunId || this.activeId === null) this.enqueueMessage(text)
        else await this.dispatchMessage(text, { attachmentIds: [] })
      } finally {
        steerAborts.delete(token)
      }
    },
    /** steer_accepted 对账：凭 token 把条目标记为已注入（messageId 即落库 user 行 id）。 */
    onSteerAccepted(ev: SteerAccepted): void {
      if (!ev.token) return
      const entry = this.steerEntries.find(e => e.token === ev.token)
      if (!entry) return
      entry.messageId = ev.message_id
      this.dedupeSteered()
    },
    /** 已确认插话的落库行进入消息列表后移除乐观条目（正式 user 行取而代之，避免重复显示）。 */
    dedupeSteered(): void {
      if (!this.steerEntries.length || !this.messages.length) return
      this.steerEntries = this.steerEntries.filter(e =>
        e.messageId === null || !this.messages.some(m => m.id === e.messageId))
    },
    /** 撤回尚未受理的插话（QueueBar × 按钮）：中断在途 POST 并移除条目。
     * POST 已受理（或 SSE 已确认）后不可撤回——AI 一定会看到它，撤回会造成 UI 与模型认知不一致。 */
    withdrawSteer(token: string): void {
      const entry = this.steerEntries.find(e => e.token === token)
      if (!entry || entry.runId !== null || entry.messageId !== null) return
      steerAborts.get(token)?.abort()
      steerAborts.delete(token)
      const index = this.steerEntries.indexOf(entry)
      if (index !== -1) this.steerEntries.splice(index, 1)
    },
    /** 切换会话/新开会话：清空插话乐观条目并中断在途 POST（消息归属旧会话，不跨会话回退发送）。 */
    clearSteerEntries(): void {
      for (const abort of steerAborts.values()) abort.abort()
      steerAborts.clear()
      this.steerEntries = []
    },
    /** run 被用户取消收敛：未注入的插话转常规待发队列（原样保留由用户处置，不自动续发）。 */
    parkUnconfirmedSteers(): void {
      const unconfirmed = this.steerEntries.filter(e => e.messageId === null)
      if (!unconfirmed.length) return
      this.steerEntries = this.steerEntries.filter(e => e.messageId !== null)
      for (const entry of unconfirmed) this.queuedMessages.push(entry.text)
      this.persistQueue()
    },
    /**
     * run 终态收敛（正常/错误）：未确认注入的插话回退为普通消息补发。
     * 先把乐观条目从「待注入」列表移除避免双显；直发失败或已有新 run 在跑则转 v1 队列。
     * 已确认的条目等落库行进历史后由 dedupeSteered/reconcileSteered 移除。
     */
    async settleSteerQueue(): Promise<void> {
      if (this.steerEntries.length) {
        const run = useRunStore()
        const unconfirmed = this.steerEntries.filter(e => e.messageId === null)
        this.steerEntries = this.steerEntries.filter(e => e.messageId !== null)
        for (const entry of unconfirmed) {
          if (this.sending || run.isActive || this.remoteRunId || this.activeId === null) {
            this.queuedMessages.push(entry.text) // 已有新 run 在跑/直发占用：转队列，下次收敛续发
            continue
          }
          const accepted = await this.dispatchMessage(entry.text, { attachmentIds: [] })
          if (!accepted) this.queuedMessages.push(entry.text) // 未送达：转队列条目等下次收敛重试
        }
        if (this.queuedMessages.length) this.persistQueue()
      }
      await this.dispatchQueue()
      await this.reconcileSteered()
    },
    /** 拉当前会话历史并对账：已确认插话的落库行出现后移除乐观条目。拉取失败保留条目等下次刷新。 */
    async reconcileSteered(): Promise<void> {
      const cid = this.activeId
      if (cid === null || !this.steerEntries.some(e => e.messageId !== null)) return
      const version = this.viewVersion
      try {
        const messages = await getConversationMessages(cid)
        if (this.activeId !== cid || this.viewVersion !== version) return
        this.messages = messages
        this.dedupeSteered()
      } catch { /* 拉取失败：乐观条目原样保留 */ }
    },
    /** run 活跃时的入队口径：仅收非空文本并立即落盘。 */
    enqueueMessage(message: string): void {
      const text = message.trim()
      if (!text) return
      this.queuedMessages.push(text)
      // 排队成功即清输入框草稿；等值守卫保证程序化入队（如黑板「让 AI 修复」）不动草稿
      if (this.draftText.trim() === text) {
        this.draftText = ''
        this.saveDraft()
      }
      this.persistQueue()
    },
    /** 删除队列中单条待发消息（QueueBar 的 × 按钮）；越界索引不动作。 */
    removeQueuedMessage(index: number): void {
      if (index < 0 || index >= this.queuedMessages.length) return
      this.queuedMessages.splice(index, 1)
      this.persistQueue()
    },
    /** 当前会话队列落盘；空队列清键避免残留。 */
    persistQueue(): void {
      const key = QUEUE_KEY_PREFIX + String(this.activeId ?? 'new')
      try {
        if (typeof localStorage === 'undefined') return
        if (this.queuedMessages.length) localStorage.setItem(key, JSON.stringify(this.queuedMessages))
        else localStorage.removeItem(key)
      } catch { /* 存储不可用（隐私模式等）：队列退化为仅内存 */ }
    },
    /** 载入当前会话的落盘队列（切换会话/恢复窗口时调用，与草稿同节奏）。 */
    loadQueue(): void {
      this.queuedMessages = readStoredQueue(QUEUE_KEY_PREFIX + String(this.activeId ?? 'new')) ?? []
    },
    /**
     * 依次发完当前会话队列：每条走原发送逻辑并等流收敛后再发下一条。
     * error/cancelled 收敛、切换会话或某条未送达（网络/409）即停，剩余消息原样保留。
     */
    async dispatchQueue(): Promise<void> {
      if (this.queueDispatching) return
      this.queueDispatching = true
      try {
        const run = useRunStore()
        const cid = this.activeId
        while (
          this.activeId === cid && this.queuedMessages.length > 0 && !this.sending &&
          !run.isActive && !run.hasLiveStream() && !this.remoteRunId &&
          run.phase !== 'error' && run.phase !== 'cancelled'
        ) {
          const message = this.queuedMessages[0]
          const accepted = await this.dispatchMessage(message, { attachmentIds: [] })
          if (this.activeId !== cid) {
            // 视图已切走：内存队列已是新会话的；已送达的这条从旧会话落盘队列补删防重复
            if (accepted) dropStoredMessage(cid, message)
            return
          }
          if (!accepted) return // 未送达：保留队首，等下次收敛再试
          this.queuedMessages.shift()
          this.persistQueue()
        }
      } finally { this.queueDispatching = false }
    },
    async uploadAttachment(file: File): Promise<void> {
      const version = this.viewVersion
      this.pendingUploads++
      this.uploading = true
      this.error = null
      try {
        const r = await uploadAttachment(file)
        if (this.viewVersion === version) { this.draftAttachments.push({ id: r.file_id, name: r.name }); this.saveDraft() }
      } catch (e) { if (this.viewVersion === version) this.error = e instanceof Error ? e.message : '附件上传失败' }
      finally { if (this.viewVersion === version) { this.pendingUploads--; this.uploading = this.pendingUploads > 0 } }
    },
    removeAttachment(id: number): void { this.draftAttachments = this.draftAttachments.filter(a => a.id !== id); this.saveDraft() },
    clearAttachments(): void { this.draftAttachments = []; this.saveDraft() },
  },
})
