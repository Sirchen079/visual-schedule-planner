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

contextBridge.exposeInMainWorld('zhishiWidget', {
  state: () => ipcRenderer.invoke('widget:state'),
  snapshot: () => ipcRenderer.invoke('widget:snapshot'),
  createTask: title => ipcRenderer.invoke('widget:create-task', { title }),
  completeTask: id => ipcRenderer.invoke('widget:complete-task', id),
  control: action => ipcRenderer.invoke('widget:control', action),
  openMain: path => ipcRenderer.invoke('widget:open-main', path),
  onStateChanged: callback => {
    const listener = (_event, state) => callback(state)
    ipcRenderer.on('widget:changed', listener)
    return () => ipcRenderer.removeListener('widget:changed', listener)
  },
})
