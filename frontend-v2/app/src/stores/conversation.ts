/** Window selection, durable drafts and history; each async reply has a view owner. */
import { defineStore } from 'pinia'
import { watch } from 'vue'
import type { AttachmentMeta, ConversationMessage, ConversationSummary } from '../api/ai'
import { getConversationMessages, listConversations, uploadAttachment } from '../api/ai'
import { getConversationState, getWorkspace, putWorkspace, type ConversationState, type Draft } from '../api/sessions'
import { useRunStore } from './run'
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
        this.sessionState = state
        run.restoreState(state)
      } catch (e) { if (this.activeId === cid && this.viewVersion === version) this.error = e instanceof Error ? e.message : '会话同步失败' }
      finally { this.syncing = false }
    },
    async sendMessage(message: string, opts: SendMessageOptions = {}): Promise<void> {
      const run = useRunStore()
      this.armQueueDispatch()
      if (this.sending) return // 发送进行中：维持原行为（静默忽略，不重复入队）
      if (run.isActive || this.remoteRunId) {
        // run 活跃：不再静默丢弃，改为入队（QueueBar 即时可见），run 正常收敛后自动续发
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
    /** 挂载 run 终态监听（幂等）：busy → 空闲且非 error/cancelled 收敛时自动续发队列。 */
    armQueueDispatch(): void {
      if (this.queueDispatchArmed) return
      this.queueDispatchArmed = true
      const run = useRunStore()
      watch(
        () => [run.isActive, run.phase, this.remoteRunId] as const,
        (cur, prev) => {
          const wasBusy = prev[0] || !!prev[2]
          const isBusy = cur[0] || !!cur[2]
          if (!wasBusy || isBusy) return
          // error/cancelled 收敛不续发，队列原样保留（QueueBar 仍可见，由用户处置）
          if (cur[1] === 'error' || cur[1] === 'cancelled') return
          void this.dispatchQueue()
        },
      )
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
