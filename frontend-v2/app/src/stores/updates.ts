import { defineStore } from 'pinia'
import { useConversationStore } from './conversation'
import { useRunStore } from './run'

export interface UpdateState {
  status: 'idle' | 'unavailable' | 'checking' | 'available' | 'downloading' | 'downloaded' | 'preparing' | 'installing' | 'error'
  currentVersion: string
  version: string
  percent: number
  error: string
  checkedAt: string | null
  releasesUrl: string
}

export const useUpdatesStore = defineStore('updates', {
  state: () => ({ state: null as UpdateState | null, initialized: false, dismissedVersion: '', actionError: '' }),
  getters: {
    locking: s => s.state?.status === 'preparing' || s.state?.status === 'installing',
    showBanner: s => !!s.state?.version && ['available', 'downloading', 'downloaded', 'error'].includes(s.state.status) && s.dismissedVersion !== s.state.version,
  },
  actions: {
    async initialize() {
      const bridge = window.zhishiUpdates
      if (!bridge || this.initialized) return
      this.initialized = true
      bridge.onChanged(state => { this.state = state })
      bridge.onPrepare(async () => {
        const conversation = useConversationStore(), run = useRunStore()
        if (run.hasLiveStream() || conversation.sending || conversation.uploading || conversation.pendingUploads) throw new Error('消息或附件仍在处理，请完成后再安装。')
        const deadline = Date.now() + 8000
        if (!conversation.initialized && !conversation.initializing) await conversation.initialize()
        while (conversation.initializing && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 25))
        if (!conversation.initialized) throw new Error('会话尚未恢复，暂时不能安装更新。')
        conversation.rememberDraft()
        conversation.workspaceDirty = true
        while (Date.now() < deadline) {
          if (conversation.savingWorkspace) { await new Promise(resolve => setTimeout(resolve, 25)); continue }
          await conversation.flushWorkspace()
          if (conversation.persistenceError) throw new Error(conversation.persistenceError)
          if (!conversation.workspaceDirty && !conversation.savingWorkspace) return
        }
        throw new Error('草稿保存超时，请稍后重试。')
      })
      try { this.state = await bridge.state() }
      catch (_) { this.actionError = '暂时无法读取更新状态' }
    },
    async act(action: 'check' | 'downloadAndInstall' | 'install' | 'openReleases') {
      const bridge = window.zhishiUpdates
      if (!bridge) return
      this.actionError = ''
      this.dismissedVersion = ''
      try { await bridge[action]() }
      catch (e) { this.actionError = e instanceof Error ? e.message : '更新操作未完成，请重试' }
    },
  },
})
