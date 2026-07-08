// 知时 桌面应用主进程
// 职责：创建窗口、系统托盘、单实例锁、探测端口、以子进程守护后端。
const { app, BrowserWindow, Tray, Menu, dialog, ipcMain, screen, shell } = require('electron')
const { spawn, execFile } = require('child_process')
const path = require('path')
const net = require('net')
const http = require('http')

const APP_NAME = '知时'
const PREFERRED_PORT = 18731

let mainWindow = null
let reminderWindow = null
let tray = null
let backend = null
let isQuitting = false
let activePort = PREFERRED_PORT

// 开机自启：注册表启动命令带 --autostart，据此区分启动来源
const isAutoStart = process.argv.includes('--autostart')

// 单实例：第二个实例直接聚焦原窗口
const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', (_e, commandLine) => {
    // 第二实例若是开机自启触发（开机时已手动开着知时）：保持静默，弹小窗
    if (commandLine.includes('--autostart')) {
      if (!reminderWindow) createReminderWindow()
      return
    }
    if (mainWindow) {
      mainWindow.show()
      mainWindow.focus()
    }
  })
}

// 探测空闲端口：从 preferred 起逐个尝试
function findFreePort(start) {
  return new Promise((resolve) => {
    const srv = net.createServer()
    srv.on('error', () => resolve(findFreePort(start + 1)))
    srv.listen(start, '127.0.0.1', () => {
      const port = srv.address().port
      srv.close(() => resolve(port))
    })
  })
}

// 后端 exe 路径
// 开发：desktop/build/backend-dist/zhishi-backend/zhishi-backend.exe
// 打包：resources/zhishi-backend/zhishi-backend.exe
function backendExePath() {
  const base = app.isPackaged
    ? process.resourcesPath
    : path.join(__dirname, '..', 'build', 'backend-dist')
  return path.join(base, 'zhishi-backend', 'zhishi-backend.exe')
}

function startBackend(port) {
  const userData = app.getPath('userData') // %APPDATA%/知时
  backend = spawn(backendExePath(), ['--port', String(port)], { cwd: userData })
  backend.stdout.on('data', (d) => process.stdout.write(d))
  backend.stderr.on('data', (d) => process.stderr.write(d))
  // spawn 失败（exe 缺失/权限不足）触发 'error' 而非 'exit'，必须单独处理
  backend.on('error', (e) => {
    dialog.showErrorBox(APP_NAME, `无法启动后端服务：${e.message}`)
    app.quit()
  })
  // code 0 = 正常退出（/shutdown 或托盘退出）→ 退 app；非 0 = 崩溃，提示
  backend.on('exit', (code) => {
    if (code === 0) {
      app.quit()
    } else {
      dialog.showErrorBox(APP_NAME, `后端进程异常退出（代码 ${code}）。`)
      app.quit()
    }
  })
}

function waitForBackend(port, tries = 150) {
  return new Promise((resolve, reject) => {
    const attempt = (n) => {
      const req = http
        .get(`http://127.0.0.1:${port}/health`, (res) => {
          if (res.statusCode === 200) resolve()
          else if (n > 0) setTimeout(() => attempt(n - 1), 200)
          else reject(new Error('health non-200'))
        })
      req.on('error', () => {
        if (n > 0) setTimeout(() => attempt(n - 1), 200)
        else reject(new Error('health timeout'))
      })
    }
    attempt(tries)
  })
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 600,
    title: APP_NAME,
    icon: path.join(__dirname, '..', 'build', 'icon.ico'),
    autoHideMenuBar: true,
    // 开机自启：主窗口静默到托盘，仅留独立提醒小窗
    show: !isAutoStart,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })
  const winParams = new URLSearchParams()
  if (isAutoStart) winParams.set('autostart', '1')
  if (app.isPackaged) winParams.set('packaged', '1')
  const qs = winParams.toString()
  mainWindow.loadURL(`http://127.0.0.1:${activePort}/${qs ? '?' + qs : ''}`)
  // 关闭按钮 → 最小化到托盘（真正退出走托盘菜单）
  mainWindow.on('close', (e) => {
    if (!isQuitting) {
      e.preventDefault()
      mainWindow.hide()
    }
  })
}

function createTray() {
  tray = new Tray(path.join(__dirname, '..', 'build', 'icon-256.png'))
  tray.setToolTip(APP_NAME)
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: '显示窗口', click: () => mainWindow.show() },
      { type: 'separator' },
      { label: '退出', click: shutdownAndQuit },
    ])
  )
  tray.on('click', () => mainWindow.show())
}

// 独立提醒小窗：开机自启时承载 DDL 提醒（主窗口此时隐藏在托盘）
function createReminderWindow() {
  const { workArea } = screen.getPrimaryDisplay()
  const w = 420
  const h = 580
  reminderWindow = new BrowserWindow({
    width: w,
    height: h,
    x: workArea.x + workArea.width - w - 16,
    y: workArea.y + workArea.height - h - 16,
    frame: false,
    resizable: false,
    maximizable: false,
    minimizable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    show: false,
    icon: path.join(__dirname, '..', 'build', 'icon.ico'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })
  const reminderParams = new URLSearchParams({ view: 'reminder' })
  if (app.isPackaged) reminderParams.set('packaged', '1')
  reminderWindow.loadURL(`http://127.0.0.1:${activePort}/?${reminderParams}`)
  reminderWindow.on('closed', () => {
    reminderWindow = null
  })
}

// 小窗 → 主进程：显示自身 / 关闭自身 / 唤出主窗口
ipcMain.on('reminder:show', () => {
  if (reminderWindow) reminderWindow.showInactive()
})
ipcMain.on('reminder:close', () => {
  if (reminderWindow) reminderWindow.close()
})
ipcMain.on('reminder:show-main', () => {
  if (mainWindow) {
    mainWindow.show()
    mainWindow.focus()
  }
  if (reminderWindow) reminderWindow.close()
})
ipcMain.on('reminder:show-main-task', (_e, taskId) => {
  if (mainWindow) {
    mainWindow.show()
    mainWindow.focus()
    // 通知主窗口渲染进程打开对应任务（App.vue 的 onFocusTask 监听）
    mainWindow.webContents.send('focus-task', taskId)
  }
  if (reminderWindow) reminderWindow.close()
})

// 外链：用系统默认浏览器打开，避免在 Electron 内开新窗口
ipcMain.on('open-external', (_e, url) => {
  shell.openExternal(url)
})

async function shutdownAndQuit() {
  if (isQuitting) return
  isQuitting = true
  // 调 /shutdown 让后端备份+落盘；后端 exit(0) 会触发 app.quit()
  try {
    await fetch(`http://127.0.0.1:${activePort}/shutdown`, { method: 'POST' })
  } catch (_) {
    // 忽略：进程可能已退出
  }
  // 2s 兜底：若后端未自行退出则强制结束并退出
  setTimeout(() => {
    if (backend) backend.kill()
    app.quit()
  }, 2000)
}

// 开机自启：自管 HKCU\Run 下的固定条目，键名用 ASCII 规避 getLoginItemSettings 在中文 exe
// 路径下的读取误报。读写都直接操作注册表，注册表即唯一真相——即便应用外被禁用（如任务管理器
// 关闭启动项），下次读取也能如实反映为关。开发模式拒绝：开发版 electron 路径会污染注册表，
// 且开机启动到错误进程。
const RUN_KEY = 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run'
const RUN_NAME = 'ZhiShi_AutoStart'

function runPowerShell(script, env = {}) {
  return new Promise((resolve) => {
    execFile(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-Command', script],
      { windowsHide: true, maxBuffer: 1 << 20, env: { ...process.env, ...env } },
      (_err, stdout) => resolve((stdout || '').trim())
    )
  })
}

// 仅判断固定键是否存在（不比较 exe 路径），稳定可靠
async function readAutostart() {
  const out = await runPowerShell(
    `$p = Get-ItemProperty -Path '${RUN_KEY}' -Name '${RUN_NAME}' -ErrorAction SilentlyContinue; if ($null -ne $p -and $p.${RUN_NAME}) { 'on' } else { 'off' }`
  )
  return out === 'on'
}

// exe 路径经环境变量传入，避开命令行引号转义；值形如 "C:\...\知时.exe" --autostart
async function writeAutostart(on) {
  if (!on) {
    await runPowerShell(
      `Remove-ItemProperty -Path '${RUN_KEY}' -Name '${RUN_NAME}' -ErrorAction SilentlyContinue`
    )
    return
  }
  await runPowerShell(
    `$v = '"' + $env:ZHISHI_EXE + '" --autostart'; New-ItemProperty -Path '${RUN_KEY}' -Name '${RUN_NAME}' -Value $v -PropertyType String -Force | Out-Null`,
    { ZHISHI_EXE: app.getPath('exe') }
  )
}

ipcMain.handle('login-item:get', async () => {
  if (!app.isPackaged) return false
  return await readAutostart()
})
ipcMain.handle('login-item:set', async (_e, openAtLogin) => {
  if (!app.isPackaged) return false
  await writeAutostart(openAtLogin)
  return await readAutostart()
})

app.whenReady().then(async () => {
  activePort = await findFreePort(PREFERRED_PORT)
  startBackend(activePort)
  try {
    await waitForBackend(activePort)
  } catch (e) {
    dialog.showErrorBox(APP_NAME, `后端服务启动失败：${e.message}`)
    app.quit()
    return
  }
  createWindow()
  createTray()
  // 开机自启：主窗口已静默到托盘，弹出独立提醒小窗
  if (isAutoStart) createReminderWindow()
})

// 系统关机/登出前尽量走干净退出（备份 + 落盘）
app.on('before-quit', (e) => {
  if (!isQuitting && backend) {
    e.preventDefault()
    shutdownAndQuit()
  }
})
