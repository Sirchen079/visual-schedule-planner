const test = require('node:test')
const assert = require('node:assert/strict')
const { EventEmitter } = require('node:events')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { createWidget, fitBounds, todaySnapshot, localDay } = require('../widget')
test('bounds recover unplugged monitors, negative coordinates and collapsed size', () => {
  assert.deepEqual(fitBounds({ x: 2500, y: 2000 }, { x: 0, y: 0, width: 1280, height: 720 }),
    { x: 840, y: 40, width: 440, height: 680 })
  assert.equal(fitBounds({ x: -1500, y: 20 }, { x: -1920, y: 0, width: 1920, height: 1080 }).x, -1500)
  assert.equal(fitBounds({}, { x: 0, y: 0, width: 320, height: 400 }, true).height, 78)
})
test('today includes events, scheduled tasks and overdue tasks once; excludes completed', () => {
  const data = todaySnapshot('2026-09-05', { items: [
    { kind: 'event', event_id: 1 }, { kind: 'task', task_id: 1 }, { kind: 'task', task_id: 2 }] }, [
    { id: 1, status: 'todo', due_date: '2026-09-05T00:00:00' },
    { id: 2, status: 'done' }, { id: 3, status: 'todo', due_date: '2026-09-01T00:00:00' },
    { id: 4, status: 'todo', due_date: '2026-09-06T00:00:00' }])
  assert.equal(data.count, 3)
  assert.deepEqual(data.due.map(t => t.id), [3])
  assert.equal(localDay(new Date(2026, 8, 5, 0, 1)), '2026-09-05')
})
test('IPC sender/arguments checked; preferences persist; resources cleaned up', async t => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), 'zhishi-widget-'))
  t.after(() => fs.rmSync(stateDir, { recursive: true, force: true }))
  const handlers = new Map(); const requests = []
  class Window extends EventEmitter {
    constructor(options) {
      super(); this.options = options; this.b = options; this.destroyed = false
      this.webContents = new EventEmitter()
      this.webContents.setWindowOpenHandler = () => {}
      this.webContents.mainFrame = {}
    }
    loadURL(url) { this.webContents.mainFrame.url = url }
    getBounds() { return this.b }
    setBounds(b) { this.b = b }
    showInactive() {}
    hide() {}
    setAlwaysOnTop(pinned) { this.pinned = pinned }
    isDestroyed() { return this.destroyed }
    destroy() { this.destroyed = true }
  }
  const screen = new EventEmitter()
  screen.getPrimaryDisplay = screen.getDisplayNearestPoint = () => ({ workArea: { x: 0, y: 0, width: 1280, height: 720 } })
  let unregisters = 0
  const electron = { BrowserWindow: Window, screen,
    ipcMain: { handle: (k, v) => handlers.set(k, v), removeHandler: k => handlers.delete(k) },
    globalShortcut: { register: () => true, unregister: () => unregisters++ } }
  const options = { electron, stateDir, baseUrl:'http://127.0.0.1:8421', showMainWindow() {}, request: async (...args) => { requests.push(args); return {} } }
  const widget = createWidget(options)
  let changed = 0
  const unsubscribe = widget.onChange(() => changed++)
  const win = widget.getWindow()
  const event = { sender: win.webContents, senderFrame: win.webContents.mainFrame }
  await assert.rejects(handlers.get('widget:create-task')({ sender: {} }, { title: 'x' }), /不允许/)
  await assert.rejects(handlers.get('widget:state')({sender:win.webContents,senderFrame:{url:'http://127.0.0.1:8421/?widget=1'}}), /不允许/)
  const allowedUrl = win.webContents.mainFrame.url
  win.webContents.mainFrame.url = 'https://example.org/?widget=1'
  await assert.rejects(handlers.get('widget:state')(event), /不允许/)
  win.webContents.mainFrame.url = allowedUrl
  assert.deepEqual(await handlers.get('widget:state')(event),{pinned:true,collapsed:false})
  await assert.rejects(handlers.get('widget:open-main')(event,'//example.org'),/无效/)
  await assert.rejects(handlers.get('widget:open-main')(event,'https://example.org'),/无效/)
  await assert.rejects(handlers.get('widget:create-task')(event, { title: ' ' }), /1–200/)
  await assert.rejects(handlers.get('widget:complete-task')(event, '../shutdown'), /无效/)
  await handlers.get('widget:create-task')(event, { title: ' 测试待办 ' })
  assert.equal(requests[0][0], '/api/tasks'); assert.equal(requests[0][2].title, '测试待办')
  await handlers.get('widget:complete-task')(event, 42)
  assert.deepEqual(requests[1], ['/api/tasks/42', 'PATCH', { status: 'done' }])
  await handlers.get('widget:control')(event, 'collapse'); assert.equal(win.b.height, 78)
  await handlers.get('widget:control')(event, 'pin'); assert.equal(win.pinned, false)
  assert.throws(() => widget.setPreferences({visible:'false'}), /无效/)
  widget.setPreferences({collapsed:false})
  assert.equal(win.b.height,680)
  widget.setPreferences({collapsed:true})
  assert.equal(win.b.height,78)
  widget.setPreferences({resetPosition:true})
  assert.equal(win.b.x,904)
  assert(changed >= 4)
  unsubscribe()
  widget.hide(); widget.dispose()
  assert.equal(handlers.size, 0); assert.equal(unregisters, 1)
  assert.equal(screen.listenerCount('display-removed'), 0); assert.equal(win.destroyed, true)
  const next = createWidget(options)
  assert.equal(next.isVisible(), false); assert.equal(next.getWindow(), null)
  next.show(); assert.equal(next.getWindow().b.height, 78)
  assert.equal(next.getWindow().options.alwaysOnTop, false)
  next.dispose()
})
