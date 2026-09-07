const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('zhishiUpdates', {
  state: () => ipcRenderer.invoke('updates:state'),
  check: () => ipcRenderer.invoke('updates:check'),
  downloadAndInstall: () => ipcRenderer.invoke('updates:download-install'),
  install: () => ipcRenderer.invoke('updates:install'),
  openReleases: () => ipcRenderer.invoke('updates:open-releases'),
  onChanged: callback => {
    const listener = (_event, state) => callback(state)
    ipcRenderer.on('updates:changed', listener)
    return () => ipcRenderer.removeListener('updates:changed', listener)
  },
  onPrepare: callback => {
    const listener = async (_event, token) => {
      try {
        await callback()
        ipcRenderer.send('updates:prepared', { token, ok: true })
      } catch (error) {
        ipcRenderer.send('updates:prepared', { token, ok: false, error: error?.message || '草稿保存失败' })
      }
    }
    ipcRenderer.on('updates:prepare', listener)
    return () => ipcRenderer.removeListener('updates:prepare', listener)
  },
})


contextBridge.exposeInMainWorld('zhishiDesktop', {
  preferences: () => ipcRenderer.invoke('desktop:preferences'),
  updatePreferences: patch => ipcRenderer.invoke('desktop:update-preferences', patch),
  onPreferencesChanged: callback => {
    const listener = (_event, state) => callback(state)
    ipcRenderer.on('desktop:preferences-changed', listener)
    return () => ipcRenderer.removeListener('desktop:preferences-changed', listener)
  },
})
