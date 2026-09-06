const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('zhishiDesktop', {
  preferences: () => ipcRenderer.invoke('desktop:preferences'),
  updatePreferences: patch => ipcRenderer.invoke('desktop:update-preferences', patch),
  onPreferencesChanged: callback => {
    const listener = (_event, state) => callback(state)
    ipcRenderer.on('desktop:preferences-changed', listener)
    return () => ipcRenderer.removeListener('desktop:preferences-changed', listener)
  },
})
