const { contextBridge, ipcRenderer } = require('electron')
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
