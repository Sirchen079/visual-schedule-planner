/** Window selection, durable drafts and history; each async reply has a view owner. */
import { defineStore } from 'pinia'
import type { AttachmentMeta, ConversationMessage, ConversationSummary } from '../api/ai'
import { getConversationMessages, listConversations, uploadAttachment } from '../api/ai'
import { getConversationState, getWorkspace, putWorkspace, type ConversationState, type Draft } from '../api/sessions'
import { useRunStore } from './run'

export const useConversationStore = defineStore('conversation', {
  state: () => ({
    conversations: [] as ConversationSummary[], activeId: null as number | null,
    messages: [] as ConversationMessage[], loading: false, error: null as string | null,
    draftText: '', draftAttachments: [] as AttachmentMeta[], drafts: {} as Record<string, Draft>,
    sentEchoAttachments: [] as AttachmentMeta[], uploading: false, pendingUploads: 0,
    sending: false, viewVersion: 0, initialized: false, initializing: false,
    surface: typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('widget') === '1' ? 'widget' : 'main',
    workspaceRevision: 0, savingWorkspace: false, workspaceDirty: false,
    persistenceError: null as string | null,
    sessionState: null as ConversationState | null, syncing: false,
  }),
  getters: {
    activeTitle(s): string { return s.conversations.find(c => c.id === s.activeId)?.title ?? (s.activeId === null ? '新对话' : `会话 ${s.activeId}`) },
    attachmentIds(s): number[] { return s.draftAttachments.map(a => a.id) },
    remoteRunId(s): string | null { return s.sessionState?.conversation_id === s.activeId ? s.sessionState.active_run_id : null },
  },
  actions: {
    async initialize(): Promise<void> {
      if (this.initialized || this.initializing) return
      this.initializing = true
      const version = this.viewVersion
      try {
        const saved = await getWorkspace(this.surface)
        this.workspaceRevision = saved.revision
        if (version === this.viewVersion && !this.sending && !this.draftText && !this.draftAttachments.length) {
          this.drafts = saved.state.drafts
          this.loadDraft(null)
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
    async flushWorkspace(): Promise<void> {
      if (this.savingWorkspace || !this.initialized) return
      this.savingWorkspace = true
      try {
        while (this.workspaceDirty) {
          this.workspaceDirty = false
          const state = JSON.parse(JSON.stringify({ active_id: this.activeId, drafts: this.drafts }))
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
      try {
        const messages = await getConversationMessages(id)
        if (this.viewVersion !== version) return
        this.rememberDraft()
        this.activeId = id
        this.messages = messages
        this.sessionState = null
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
      this.rememberDraft()
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
      this.sentEchoAttachments = []
      this.saveDraft()
    },
    stageSentEcho(attachments: AttachmentMeta[]): void { this.sentEchoAttachments = attachments.map(a => ({ id: a.id, name: a.name })) },
    attachFromRun(cid: number): void {
      if (this.activeId === cid) return
      this.activeId = cid
      this.messages = []
      this.sessionState = null
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
    async sendMessage(message: string, opts: { attachmentIds?: number[]; planMode?: boolean; researchProjectId?: number } = {}): Promise<void> {
      const run = useRunStore()
      if (run.isActive || this.sending || this.remoteRunId) return
      const version = this.viewVersion, conversationId = this.activeId
      const attachments = this.draftAttachments.map(a => ({ ...a }))
      this.sending = true
      this.error = null
      let accepted = false
      try {
        if (conversationId !== null) {
          const history = await getConversationMessages(conversationId)
          if (this.viewVersion !== version) return
          this.messages = history
        }
        this.stageSentEcho(attachments)
        await run.sendMessage(message, { ...opts, conversationId, onConversationStarted: id => {
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
