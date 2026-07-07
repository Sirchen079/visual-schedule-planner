// 知时 桌面应用主进程
// 职责：创建窗口、系统托盘、单实例锁、探测端口、以子进程守护后端。
const { app, BrowserWindow, Tray, Menu, dialog } = require('electron')
const { spawn } = require('child_process')
const path = require('path')
const net = require('net')
const http = require('http')

const APP_NAME = '知时'
const PREFERRED_PORT = 18731

let mainWindow = null
let tray = null
let backend = null
let isQuitting = false
let activePort = PREFERRED_PORT

// 单实例：第二个实例直接聚焦原窗口
const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
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
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })
  mainWindow.loadURL(`http://127.0.0.1:${activePort}/`)
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
})

// 系统关机/登出前尽量走干净退出（备份 + 落盘）
app.on('before-quit', (e) => {
  if (!isQuitting && backend) {
    e.preventDefault()
    shutdownAndQuit()
  }
})
