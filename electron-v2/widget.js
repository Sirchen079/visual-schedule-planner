const fs = require('fs')
const path = require('path')

function localDay(now = new Date()) {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

function fitBounds(saved, area, collapsed = false) {
  const width = Math.min(collapsed ? 352 : 440, area.width)
  const height = Math.min(collapsed ? 78 : 680, area.height)
  const x = Number.isFinite(saved?.x) ? saved.x : area.x + area.width - width - 24
  const y = Number.isFinite(saved?.y) ? saved.y : area.y + 48
  return { width, height,
    x: Math.round(Math.max(area.x, Math.min(x, area.x + area.width - width))),
    y: Math.round(Math.max(area.y, Math.min(y, area.y + area.height - height))) }
}

function todaySnapshot(day, schedule, tasks) {
  const active = tasks.filter(t => t.status !== 'done')
  const ids = new Set(active.map(t => t.id))
  const items = schedule.items.filter(i => i.kind !== 'task' || ids.has(i.task_id))
  const scheduled = new Set(items.filter(i => i.kind === 'task').map(i => i.task_id))
  const due = active.filter(t => !scheduled.has(t.id) && t.due_date && t.due_date.slice(0, 10) <= day)
    .sort((a, b) => a.due_date.localeCompare(b.due_date) || a.id - b.id)
  return { day, items, due, count: items.length + due.length }
}

function createWidget({ electron, request, showMainWindow, baseUrl, stateDir, onVisibility = () => {} }) {
  const { BrowserWindow, ipcMain, screen, globalShortcut } = electron
  const stateFile = path.join(stateDir, 'widget.json')
  let state = { visible: true, pinned: true, collapsed: false }
  try {
    const saved = JSON.parse(fs.readFileSync(stateFile, 'utf8'))
    for (const key of ['visible', 'pinned', 'collapsed']) {
      if (typeof saved[key] === 'boolean') state[key] = saved[key]
    }
    if (Number.isFinite(saved.x) && Number.isFinite(saved.y)) {
      state.x = saved.x; state.y = saved.y
    }
  } catch (_) { /* first launch / corrupt preferences: use reachable defaults */ }
  let win = null
  let saveTimer = null
  let disposed = false
  const changeListeners = new Set()
  const origin = new URL(baseUrl).origin
  if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(origin)) throw new Error('悬浮窗仅连接本次本机后端')
  const url = origin + '/?widget=1#/'
  const channels = ['widget:state', 'widget:open-main', 'widget:snapshot', 'widget:create-task', 'widget:complete-task', 'widget:control']
  function persist(value) {
    fs.mkdirSync(stateDir, { recursive: true })
    fs.writeFileSync(stateFile + '.tmp', JSON.stringify(value))
    fs.renameSync(stateFile + '.tmp', stateFile)
  }
  function save() {
    clearTimeout(saveTimer)
    try {
      persist(state)
    } catch (e) { console.warn('[widget] 无法保存偏好：', e.message) }
  }
  function changed() {
    if (win && !win.isDestroyed()) win.webContents.send?.('widget:changed', { pinned: state.pinned, collapsed: state.collapsed })
    for (const callback of changeListeners) callback()
  }
  function bounds() {
    const area = Number.isFinite(state.x) && Number.isFinite(state.y)
      ? screen.getDisplayNearestPoint({ x: Math.round(state.x), y: Math.round(state.y) }).workArea
      : screen.getPrimaryDisplay().workArea
    return fitBounds(state, area, state.collapsed)
  }
  function rememberPosition() {
    if (!win || win.isDestroyed()) return
    const b = win.getBounds()
    state.x = b.x; state.y = b.y
    clearTimeout(saveTimer)
    saveTimer = setTimeout(save, 250)
  }
  function adjust() {
    if (!win || win.isDestroyed()) return
    win.setBounds(bounds())
    rememberPosition()
  }
  function show() {
    if (disposed) return
    if (!win) {
      win = new BrowserWindow({ ...bounds(), title: '知时 · 随身秘书',
        frame: false, transparent: true, backgroundColor: '#00000000',
        show: false, resizable: false, maximizable: false, fullscreenable: false,
        skipTaskbar: true, alwaysOnTop: state.pinned,
        webPreferences: { preload: path.join(__dirname, 'widget-preload.js'),
          contextIsolation: true, nodeIntegration: false, sandbox: true } })
      win.webContents.setWindowOpenHandler(({ url }) => {
        if (/^https?:/i.test(url)) electron.shell.openExternal(url)
        return { action: 'deny' }
      })
      win.webContents.on('will-navigate', e => e.preventDefault())
      win.on('move', rememberPosition)
      win.on('close', e => { if (!disposed) { e.preventDefault(); hide() } })
      win.once('ready-to-show', () => { if (state.visible && !disposed) win.showInactive() })
      win.loadURL(url)
    } else {
      adjust()
      win.showInactive()
    }
    state.visible = true
    save()
    onVisibility(true)
    changed()
  }
  function hide() {
    if (win && !win.isDestroyed()) win.hide()
    state.visible = false
    save()
    onVisibility(false)
    changed()
  }
  function toggle() { state.visible ? hide() : show() }
  function trustedUrl(value) {
    try { const u = new URL(value); return u.origin === origin && u.pathname === '/' && u.searchParams.get('widget') === '1' }
    catch { return false }
  }
  function guard(event) {
    if (!win || event.sender !== win.webContents || event.senderFrame !== win.webContents.mainFrame ||
        !trustedUrl(event.senderFrame.url)) throw new Error('不允许的悬浮窗请求')
  }
  function handle(channel, fn) {
    ipcMain.handle(channel, async (event, payload) => { guard(event); return fn(payload) })
  }
  handle('widget:state', () => ({ pinned: state.pinned, collapsed: state.collapsed }))
  handle('widget:open-main', target => {
    if (typeof target !== 'string' || !target.startsWith('/') || target.startsWith('//') || target.includes('\\') || target.length > 2000) throw new Error('无效的应用页面')
    showMainWindow(target)
    return { pinned: state.pinned, collapsed: state.collapsed }
  })
  handle('widget:snapshot', async () => {
    const day = localDay()
    const [schedule, tasks] = await Promise.all([
      request(`/api/schedule/day?date=${day}`), request('/api/tasks')])
    return { ...todaySnapshot(day, schedule, tasks), pinned: state.pinned, collapsed: state.collapsed }
  })
  handle('widget:create-task', async payload => {
    const title = typeof payload?.title === 'string' ? payload.title.trim() : ''
    if (!title || title.length > 200) throw new Error('请填写 1–200 字的任务')
    // Quick capture stores the literal title; intent interpretation remains in the AI conversation.
    return request('/api/tasks', 'POST', { title, due_date: `${localDay()}T00:00:00` })
  })
  handle('widget:complete-task', async id => {
    if (!Number.isSafeInteger(id) || id < 1) throw new Error('任务编号无效')
    return request(`/api/tasks/${id}`, 'PATCH', { status: 'done' })
  })
  handle('widget:control', action => {
    if (action === 'hide') hide()
    else if (action === 'main') showMainWindow()
    else if (action === 'pin') { state.pinned = !state.pinned; win.setAlwaysOnTop(state.pinned); save(); changed() }
    else if (action === 'collapse') { state.collapsed = !state.collapsed; adjust(); save(); changed() }
    else throw new Error('未知操作')
    return { pinned: state.pinned, collapsed: state.collapsed }
  })
  screen.on('display-removed', adjust)
  screen.on('display-metrics-changed', adjust)
  const shortcut = 'CommandOrControl+Alt+Z'
  const registered = globalShortcut.register(shortcut, toggle)
  if (!registered) console.warn('[widget] Ctrl+Alt+Z 已被占用，可从托盘开关悬浮窗')
  if (state.visible) show()
  function preferences() { return { visible: state.visible, pinned: state.pinned, collapsed: state.collapsed, shortcutRegistered: registered } }
  function setPreferences(patch) {
    if (!patch || typeof patch !== 'object' || Array.isArray(patch) ||
        Object.entries(patch).some(([key,value]) => !['visible','pinned','collapsed','resetPosition'].includes(key) || typeof value !== 'boolean')) throw new Error('无效的悬浮窗设置')
    const next = { ...state }
    for (const key of ['visible','pinned','collapsed']) if (key in patch) next[key] = patch[key]
    if (patch.resetPosition) { delete next.x; delete next.y }
    // Persist before changing the window, so the settings page can report failed writes accurately.
    persist(next)
    state = next
    if (win && !win.isDestroyed()) { win.setAlwaysOnTop(state.pinned); adjust() }
    if (state.visible) show(); else hide()
    return preferences()
  }
  return { show, hide, toggle, preferences, setPreferences,
    onChange(callback) { changeListeners.add(callback); return () => changeListeners.delete(callback) },
    isVisible: () => state.visible, getWindow: () => win,
    dispose() {
      disposed = true
      rememberPosition(); save()
      if (registered) globalShortcut.unregister(shortcut)
      screen.removeListener('display-removed', adjust)
      screen.removeListener('display-metrics-changed', adjust)
      for (const channel of channels) ipcMain.removeHandler(channel)
      changeListeners.clear()
      if (win && !win.isDestroyed()) win.destroy()
      win = null
    } }
}

module.exports = { createWidget, localDay, fitBounds, todaySnapshot }
