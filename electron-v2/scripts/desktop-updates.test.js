const { test } = require('node:test')
const assert = require('node:assert/strict')
const { EventEmitter } = require('node:events')
const { createDesktopUpdates, newerVersion, RELEASES_URL } = require('../desktop-updates')

function fixture(options = {}) {
  const updater = new EventEmitter(), ipc = new EventEmitter(), handlers = new Map(), calls = []
  ipc.handle = (name, fn) => handlers.set(name, fn)
  ipc.removeHandler = name => handlers.delete(name)
  updater.checkForUpdates = async () => { calls.push('check'); updater.emit('checking-for-update'); updater.emit('update-available', { version: '2.16.0' }) }
  updater.downloadUpdate = async () => { calls.push('download'); updater.emit('download-progress', { percent: 50 }); updater.emit('update-downloaded', { version: '2.16.0' }); return ['verified.exe'] }
  updater.quitAndInstall = (...args) => { calls.push(['install', ...args]) }
  const windows = [1, 2].map(id => {
    const contents = { id, mainFrame: { url: `http://127.0.0.1:3210/${id === 2 ? '?widget=1' : ''}` },
      send: (channel, value) => {
        if (channel === 'updates:prepare' && !options.noReply) queueMicrotask(() => {
          calls.push(`flush${id}`)
          ipc.emit('updates:prepared', { sender: contents, senderFrame: contents.mainFrame }, {
            token: value, ok: !options.saveFail, error: '草稿未保存',
          })
        })
      } }
    return { isDestroyed: () => false, webContents: contents }
  })
  const service = createDesktopUpdates({ updater, ipcMain: ipc, app: { isPackaged: true, getVersion: () => '2.15.0' },
    getWindows: () => windows, baseUrl: 'http://127.0.0.1:3210', prepareTimeout: 30,
    request: async (path) => { calls.push(path); if (options.busy && path.endsWith('prepare')) throw new Error('还有 AI 任务正在运行') },
    shutdown: async () => calls.push('shutdown'), openReleases: url => calls.push(url), notify: version => calls.push(`notify${version}`),
    startDelay: 100000, interval: 100000, ...options })
  const main = windows[0].webContents
  const invoke = (name, event = { sender: main, senderFrame: main.mainFrame }) => handlers.get(name)(event)
  return { service, updater, ipc, handlers, calls, invoke, windows }
}

test('only stable newer versions are offered', () => {
  assert(newerVersion('2.16.0', '2.15.0'))
  for (const value of ['2.15.0', '2.14.9', '2.16.0-beta.1', '<script>', 'v2.16.0']) assert(!newerVersion(value, '2.15.0'))
})

test('one click downloads, flushes both windows and installs after shutdown', async () => {
  const f = fixture()
  try {
    assert.equal(f.updater.autoDownload, false)
    assert.equal(f.updater.autoInstallOnAppQuit, false)
    assert.equal(f.updater.allowDowngrade, false)
    await f.service.check()
    await Promise.all([f.service.downloadAndInstall(), f.service.downloadAndInstall()])
    assert.equal(f.calls.filter(x => x === 'download').length, 1)
    assert(f.calls.indexOf('shutdown') > f.calls.indexOf('flush1'))
    assert(f.calls.indexOf('shutdown') > f.calls.indexOf('flush2'))
    assert.deepEqual(f.calls.at(-1), ['install', true, true])
  } finally { f.service.dispose() }
})

test('busy backend keeps the verified download available without closing windows', async () => {
  const f = fixture({ busy: true })
  try {
    await f.service.check(); await f.service.downloadAndInstall()
    assert.equal(f.service.snapshot().status, 'downloaded')
    assert.match(f.service.snapshot().error, /正在运行/)
    assert(!f.calls.includes('shutdown'))
    assert(!f.calls.includes('flush1'))
  } finally { f.service.dispose() }
})

for (const option of ['saveFail', 'noReply']) test(`${option} cancels the run gate and preserves the app`, async () => {
  const f = fixture({ [option]: true })
  try {
    await f.service.check(); await f.service.downloadAndInstall()
    assert.equal(f.service.snapshot().status, 'downloaded')
    assert(f.calls.includes('/ai/runtime/update-cancel'))
    assert(!f.calls.includes('shutdown'))
  } finally { f.service.dispose() }
})

test('checksum failure never starts installation and can retry download', async () => {
  const f = fixture()
  try {
    await f.service.check()
    f.updater.downloadUpdate = async () => { const error = Object.assign(new Error('sha512 checksum mismatch'), { code: 'ERR_UPDATER_CHECKSUM_MISMATCH' }); f.updater.emit('error', error); throw error }
    await f.service.downloadAndInstall()
    assert.equal(f.service.snapshot().status, 'error')
    assert.match(f.service.snapshot().error, /校验失败/)
    assert(!f.calls.includes('shutdown'))
    await f.service.install()
    assert(!f.calls.includes('shutdown'))
  } finally { f.service.dispose() }
})

test('checks share one request; same version notifies once; old feed cannot downgrade', async () => {
  const f = fixture()
  try {
    await Promise.all([f.service.check(), f.service.check()])
    assert.equal(f.calls.filter(x => x === 'check').length, 1)
    await f.service.check()
    assert.equal(f.calls.filter(x => x === 'notify2.16.0').length, 1)
    f.updater.emit('update-available', { version: '1.3.0' })
    await f.service.downloadAndInstall()
    assert.equal(f.service.snapshot().status, 'idle')
    assert(!f.calls.includes('download'))
  } finally { f.service.dispose() }
})

test('only trusted main frames can invoke updater, and release URL is fixed', async () => {
  const f = fixture()
  try {
    assert.throws(() => f.invoke('updates:check', { sender: {}, senderFrame: {} }), /不允许/)
    const contents = f.windows[0].webContents
    assert.throws(() => f.invoke('updates:check', { sender: contents, senderFrame: { url: contents.mainFrame.url } }), /不允许/)
    contents.mainFrame.url = 'https://outside.example/'
    assert.throws(() => f.invoke('updates:check'), /不允许/)
    contents.mainFrame.url = 'http://127.0.0.1:3210/'
    await f.invoke('updates:open-releases')
    assert.equal(f.calls.at(-1), RELEASES_URL)
  } finally { f.service.dispose(); assert.equal(f.handlers.size, 0) }
})

test('development builds never contact the update feed', async () => {
  const f = fixture({ enabled: false })
  try {
    await f.service.check(); await f.service.downloadAndInstall()
    assert.equal(f.service.snapshot().status, 'unavailable')
    assert.deepEqual(f.calls, [])
  } finally { f.service.dispose() }
})

test('an installer launch error after shutdown recovers the application once', async () => {
  const recovered = []
  const f = fixture({ onInstallFailure: message => recovered.push(message) })
  try {
    f.updater.quitAndInstall = () => { f.updater.emit('error', new Error('installer spawn failed')); f.updater.emit('error', new Error('same error again')) }
    await f.service.check(); await f.service.downloadAndInstall()
    assert.equal(recovered.length, 1)
    assert.match(recovered[0], /重新打开/)
    assert(f.calls.includes('shutdown'))
  } finally { f.service.dispose() }
})

test('a backend that cannot exit cancels installation and reports the failure', async () => {
  const f = fixture({ shutdown: async () => { throw new Error('后端进程尚未退出，已停止安装') } })
  try {
    await f.service.check(); await f.service.downloadAndInstall()
    assert.equal(f.service.snapshot().status, 'downloaded')
    assert.match(f.service.snapshot().error, /后端进程尚未退出/)
    assert(f.calls.includes('/ai/runtime/update-cancel'))
    assert(!f.calls.some(value => Array.isArray(value) && value[0] === 'install'))
  } finally { f.service.dispose() }
})


test('update diagnostics identify preparation and installer request in order', async () => {
  const recorded = []
  const f = fixture({ diagnosticEvent: event => recorded.push(event) })
  try {
    await f.service.check(); await f.service.downloadAndInstall()
    assert.deepEqual(recorded, ['update_prepare', 'update_installer_requested'])
  } finally { f.service.dispose() }
})
