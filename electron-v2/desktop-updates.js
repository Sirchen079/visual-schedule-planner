const { randomUUID } = require('crypto')

const RELEASES_URL = 'https://github.com/Sirchen079/visual-schedule-planner/releases'
const CHANNELS = ['updates:state', 'updates:check', 'updates:download-install', 'updates:install', 'updates:open-releases']

function newerVersion(candidate, current) {
  const parse = value => /^\d+\.\d+\.\d+$/.test(value || '') ? value.split('.').map(Number) : null
  const a = parse(candidate), b = parse(current)
  if (!a || !b) return false
  for (let i = 0; i < 3; i++) if (a[i] !== b[i]) return a[i] > b[i]
  return false
}

function createDesktopUpdates({ updater, ipcMain, app, getWindows, baseUrl, request,
  shutdown, openReleases, diagnosticEvent = () => {}, notify = () => {}, onInstallFailure = () => {}, enabled = app.isPackaged,
  prepareTimeout = 10000, startDelay = 20000, interval = 6 * 60 * 60 * 1000 }) {
  const origin = new URL(baseUrl).origin
  let state = { status: enabled ? 'idle' : 'unavailable', currentVersion: app.getVersion(),
    version: '', percent: 0, error: '', checkedAt: null, releasesUrl: RELEASES_URL }
  let checkPending = null, downloadPending = null, installPending = null, disposed = false
  let startupTimer, repeatTimer, notifiedVersion = ''
  let stoppedForInstall = false, recoveredInstallFailure = false
  const listeners = [], acknowledgements = new Map()
  const windows = () => getWindows().filter(win => win && !win.isDestroyed())
  const snapshot = () => ({ ...state })
  function publish(patch) {
    if (disposed) return
    state = { ...state, ...patch }
    for (const win of windows()) win.webContents.send('updates:changed', snapshot())
  }
  function guard(event) {
    const win = windows().find(win => event.sender === win.webContents)
    if (!win || event.senderFrame !== win.webContents.mainFrame) throw new Error('不允许的更新请求')
    const url = new URL(event.senderFrame.url)
    if (url.origin !== origin || url.pathname !== '/') throw new Error('不允许的更新请求')
  }
  function failure(message) { publish({ status: 'error', error: message, percent: 0 }) }
  updater.autoDownload = false
  updater.autoInstallOnAppQuit = false
  updater.allowPrerelease = false
  updater.allowDowngrade = false
  // The public feed is generated into app-update.yml by electron-builder.
  // No credentials or renderer-provided URLs are accepted here.
  function listen(name, callback) { updater.on(name, callback); listeners.push([name, callback]) }
  listen('checking-for-update', () => publish({ status: 'checking', error: '' }))
  listen('update-available', info => {
    if (!newerVersion(info.version, state.currentVersion)) {
      publish({ status: 'idle', version: '', checkedAt: new Date().toISOString() }); return
    }
    publish({ status: 'available', version: info.version, error: '', percent: 0, checkedAt: new Date().toISOString() })
    if (notifiedVersion !== info.version) { notifiedVersion = info.version; notify(info.version) }
  })
  listen('update-not-available', () => publish({ status: 'idle', version: '', error: '', checkedAt: new Date().toISOString() }))
  listen('download-progress', progress => publish({ status: 'downloading', percent: Math.max(0, Math.min(100, Number(progress.percent) || 0)) }))
  listen('update-downloaded', info => {
    if (newerVersion(info.version, state.currentVersion)) publish({ status: 'downloaded', version: info.version, percent: 100, error: '' })
    else failure('下载的版本不是更新版本，请重新检查。')
  })
  listen('error', error => {
    diagnosticEvent('update_error')
    const wasInstalling = stoppedForInstall
    const code = String(error?.code || '')
    failure(/sha|checksum|signature/i.test(code + ' ' + String(error?.message || ''))
      ? '安装包校验失败，未执行安装。请重新下载。'
      : '更新服务暂时不可用。请检查网络后重试，或打开发布页下载安装包。')
    if (wasInstalling && !recoveredInstallFailure) {
      recoveredInstallFailure = true
      onInstallFailure('安装程序未能启动，知时将重新打开。数据与草稿已经保存。')
    }
  })

  function prepareWindows() {
    const token = randomUUID()
    return Promise.all(windows().map(win => new Promise((resolve, reject) => {
      const id = `${token}:${win.webContents.id}`
      const timer = setTimeout(() => { acknowledgements.delete(id); reject(new Error('窗口尚未完成草稿保存，请稍后重试。')) }, prepareTimeout)
      acknowledgements.set(id, { resolve, reject, timer })
      win.webContents.send('updates:prepare', token)
    })))
  }
  const onPrepared = (event, payload) => {
    try { guard(event) } catch (_) { return }
    if (!payload || typeof payload.token !== 'string') return
    const id = `${payload.token}:${event.sender.id}`, pending = acknowledgements.get(id)
    if (!pending) return
    clearTimeout(pending.timer); acknowledgements.delete(id)
    if (payload.ok === true) pending.resolve()
    else pending.reject(new Error(typeof payload.error === 'string' ? payload.error.slice(0, 200) : '草稿尚未保存，请稍后重试。'))
  }
  ipcMain.on('updates:prepared', onPrepared)

  async function check() {
    if (!enabled || disposed || downloadPending || installPending || state.status === 'downloaded') return snapshot()
    if (checkPending) return checkPending
    checkPending = (async () => {
      try { await updater.checkForUpdates() }
      catch (_) { if (state.status !== 'error') failure('无法连接 GitHub 更新服务，请检查网络后重试。') }
      finally { checkPending = null }
      return snapshot()
    })()
    return checkPending
  }
  async function install() {
    if (installPending) return installPending
    if (state.status !== 'downloaded' || !enabled || disposed) return snapshot()
    installPending = (async () => {
      let locked = false
      try {
        diagnosticEvent('update_prepare')
        publish({ status: 'preparing', error: '' })
        // Claim the backend's run gate before asking both renderers to flush.
        await request('/ai/runtime/update-prepare', 'POST', {})
        locked = true
        await prepareWindows()
        publish({ status: 'installing', error: '' })
        await shutdown({ quit: false })
        stoppedForInstall = true
        diagnosticEvent('update_installer_requested')
        // Install without a wizard and relaunch after the replacement completes.
        updater.quitAndInstall(true, true)
      } catch (error) {
        diagnosticEvent('update_install_failed')
        if (stoppedForInstall && !recoveredInstallFailure) {
          recoveredInstallFailure = true
          onInstallFailure('安装程序未能启动，知时将重新打开。数据与草稿已经保存。')
        }
        if (locked) { try { await request('/ai/runtime/update-cancel', 'POST', {}) } catch (_) {} }
        publish({ status: 'downloaded', error: error?.message || '当前尚不能安装，请稍后重试。' })
      } finally { installPending = null }
      return snapshot()
    })()
    return installPending
  }
  async function downloadAndInstall() {
    if (!enabled || disposed) return snapshot()
    if (state.status === 'downloaded') return install()
    if (downloadPending) return downloadPending
    if (!['available', 'error'].includes(state.status) || !newerVersion(state.version, state.currentVersion)) return snapshot()
    downloadPending = (async () => {
      try {
        publish({ status: 'downloading', percent: 0, error: '' })
        await updater.downloadUpdate()
        if (state.status === 'downloaded') await install()
      } catch (_) { if (state.status !== 'error') failure('下载失败，可重试下载或打开发布页。') }
      finally { downloadPending = null }
      return snapshot()
    })()
    return downloadPending
  }
  const actions = { 'updates:state': snapshot, 'updates:check': check,
    'updates:download-install': downloadAndInstall, 'updates:install': install,
    'updates:open-releases': () => openReleases(RELEASES_URL) }
  for (const channel of CHANNELS) ipcMain.handle(channel, event => { guard(event); return actions[channel]() })
  if (enabled) {
    startupTimer = setTimeout(() => { void check() }, startDelay)
    repeatTimer = setInterval(() => { void check() }, interval)
    startupTimer.unref?.(); repeatTimer.unref?.()
  }
  return { snapshot, check, downloadAndInstall, install, dispose() {
    disposed = true
    clearTimeout(startupTimer); clearInterval(repeatTimer)
    for (const channel of CHANNELS) ipcMain.removeHandler(channel)
    ipcMain.removeListener('updates:prepared', onPrepared)
    for (const [name, callback] of listeners) updater.removeListener(name, callback)
    for (const pending of acknowledgements.values()) { clearTimeout(pending.timer); pending.reject(new Error('应用正在退出')) }
    acknowledgements.clear()
  } }
}

module.exports = { createDesktopUpdates, newerVersion, RELEASES_URL }
