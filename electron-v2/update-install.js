'use strict'

// electron-updater schedules app.quit before its asynchronous spawn can fail.
// Keep the process alive until that launch attempt has an outcome, so errors
// can still reach the application's recovery handler.
function installWithLaunchGuard(updater, app) {
  return new Promise((resolve, reject) => {
    const originalSpawn = updater.spawnLog
    if (typeof originalSpawn !== 'function') {
      reject(new Error('更新组件缺少安装启动接口，请手动运行安装包。'))
      return
    }
    let pending = true, quitRequested = false, attempted = false
    const beforeQuit = event => {
      if (pending) { quitRequested = true; event.preventDefault() }
    }
    const cleanup = () => {
      updater.spawnLog = originalSpawn
      updater.removeListener('error', onError)
      app.removeListener('before-quit', beforeQuit)
    }
    const onError = error => {
      if (!pending) return
      pending = false
      cleanup()
      updater.quitAndInstallCalled = false
      reject(error)
    }
    app.on('before-quit', beforeQuit)
    // Restore normal quit handling before an existing error listener relaunches.
    updater.prependListener('error', onError)
    updater.spawnLog = async function (...args) {
      attempted = true
      try {
        const result = await originalSpawn.apply(this, args)
        if (pending) {
          pending = false
          cleanup()
          if (quitRequested) app.quit()
          resolve()
        }
        return result
      } catch (error) {
        // Windows policy rejection can surface as UNKNOWN. Elevating the same
        // blocked file cannot resolve it and hides failure behind a helper PID.
        if (error?.code === 'UNKNOWN') {
          const launchError = new Error('Windows 未能启动安装程序，可能被应用控制策略阻止。')
          launchError.code = 'ERR_INSTALLER_LAUNCH'
          launchError.cause = error
          throw launchError
        }
        throw error
      }
    }
    try {
      // Retain the interactive installer used by 2.15.0 through 2.21.0.
      updater.quitAndInstall(false, true)
      if (!attempted) onError(new Error('安装程序没有启动，请重新下载或手动运行安装包。'))
    } catch (error) { onError(error) }
  })
}

module.exports = { installWithLaunchGuard }
