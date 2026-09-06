const fs = require('fs')
const path = require('path')

function createDesktopSettings({ ipcMain, getMainWindow, widget, baseUrl, stateDir }) {
  const stateFile = path.join(stateDir, 'desktop.json')
  const origin = new URL(baseUrl).origin
  let notifications = true
  try { const saved = JSON.parse(fs.readFileSync(stateFile, 'utf8')); if (typeof saved.notifications === 'boolean') notifications = saved.notifications } catch (_) {}
  const snapshot = () => ({ ...widget.preferences(), notifications })
  function guard(event) {
    const win = getMainWindow()
    if (!win || win.isDestroyed() || event.sender !== win.webContents || event.senderFrame !== win.webContents.mainFrame) throw new Error('不允许的桌面设置请求')
    const url = new URL(event.senderFrame.url)
    if (url.origin !== origin || url.pathname !== '/' || url.searchParams.has('widget')) throw new Error('不允许的桌面设置请求')
  }
  function broadcast() {
    const win = getMainWindow()
    if (win && !win.isDestroyed()) win.webContents.send('desktop:preferences-changed', snapshot())
  }
  ipcMain.handle('desktop:preferences', event => { guard(event); return snapshot() })
  ipcMain.handle('desktop:update-preferences', (event, patch) => {
    guard(event)
    if (!patch || typeof patch !== 'object' || Array.isArray(patch) || Object.keys(patch).length !== 1 ||
        Object.entries(patch).some(([key,value]) => !['visible','pinned','collapsed','resetPosition','notifications'].includes(key) || typeof value !== 'boolean')) throw new Error('请每次修改一项有效设置')
    if ('notifications' in patch) {
      fs.mkdirSync(stateDir, { recursive: true })
      fs.writeFileSync(stateFile + '.tmp', JSON.stringify({ notifications: patch.notifications }))
      fs.renameSync(stateFile + '.tmp', stateFile)
      notifications = patch.notifications
      broadcast()
    } else widget.setPreferences(patch)
    return snapshot()
  })
  const unsubscribe = widget.onChange(broadcast)
  return { snapshot, dispose() {
    unsubscribe()
    ipcMain.removeHandler('desktop:preferences')
    ipcMain.removeHandler('desktop:update-preferences')
  } }
}

module.exports = { createDesktopSettings }
