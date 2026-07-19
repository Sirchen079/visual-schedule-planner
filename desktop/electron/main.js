// 知时 桌面应用主进程
// 职责：创建窗口、系统托盘、单实例锁、探测端口、以子进程守护后端。
const { app, BrowserWindow, Tray, Menu, dialog, ipcMain, screen, shell, globalShortcut, powerMonitor } = require('electron')
const { spawn, execFile, spawnSync } = require('child_process')
const fs = require('fs')
const path = require('path')
const net = require('net')
const http = require('http')

const APP_NAME = '知时'
const PREFERRED_PORT = 18731

let mainWindow = null
let reminderWindow = null
let captureWindow = null
let tray = null
let backend = null
let isQuitting = false
let activePort = PREFERRED_PORT
// 应用设置缓存（后端为唯一真相源）：close_button_behavior、assistant_float_enabled
let appSettings = {
  assistant_float_enabled: 'false',
  close_button_behavior: 'minimize',
}
// 悬浮窗：主窗口最小化到托盘时显示，打开主窗口时隐藏
let assistantFloat = null
let mainEverShown = false // 主窗口是否曾显示过；开机自启从未 show，不误触发悬浮窗
const FLOAT_BUTTON = { width: 60, height: 60 }
const FLOAT_PANEL = { width: 380, height: 600 }

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

// 安装根目录（知时.exe 所在目录）下的 data/：便携式数据跟随软件，避免塞满 C 盘 AppData
function dataDir() {
  return path.join(path.dirname(app.getPath('exe')), 'data')
}

// 旧版（v1.2.1 之前）数据位置：%APPDATA%\知时\data
function legacyDataDir() {
  return path.join(app.getPath('appData'), '知时', 'data')
}

// 迁移完成哨兵：robocopy 整体成功后才写入，避免 app.db 先被复制（partial）时被误判为已迁移
function migrationMarker(target) {
  return path.join(target, '.migrated')
}

// 程序文件夹下的"迁移前备份"：保留最近一次更新前的完整数据快照，便于回退/恢复
function migrationBackupDir() {
  return path.join(path.dirname(app.getPath('exe')), 'migration-backup')
}

// 迁移日志：开机自启不弹框时也能留下成功/失败记录，便于排查
function logMigration(message) {
  try {
    fs.appendFileSync(
      path.join(path.dirname(app.getPath('exe')), 'migration.log'),
      `${message}\n`
    )
  } catch (_) {
    // 日志写入失败不影响启动
  }
}

// robocopy 包装：/R:1 /W:1 文件被锁时快速失败，避免默认百万次重试卡死主进程；
// 保留文件/目录列表（不传 /NFL /NDL）以便失败时诊断具体文件。
function runRobocopy(src, dst) {
  return spawnSync('robocopy', [src, dst, '/E', '/R:1', '/W:1', '/NJH', '/NJS', '/NP'], {
    windowsHide: true,
    encoding: 'utf8',
  })
}

// 把 robocopy 失败输出摘要附进错误信息，便于诊断哪个文件/为何失败
function robocopyHint(r) {
  const out = (r.stdout || '').trim()
  if (!out) return ''
  return `\n${out.split(/\r?\n/).slice(-10).join('\n')}`
}

// 准备数据目录：若旧版数据仍在 AppData 则迁移到软件目录，返回最终应使用的目录。
// 目标不可写或迁移失败时回退到旧目录，保证数据可读、不丢失。
function prepareDataDir() {
  // 开发模式（非打包）不干预数据目录，后端自行解析（python 开发=data/，打包 exe=APPDATA）
  if (!app.isPackaged) return null
  const target = dataDir()
  const legacy = legacyDataDir()
  // 已迁移完成（哨兵存在）：直接用便携目录
  if (fs.existsSync(migrationMarker(target))) return target
  // 确保目标目录存在；创建失败（如装到只读目录）则降级到旧目录，避免启动崩溃
  try {
    fs.mkdirSync(target, { recursive: true })
  } catch (e) {
    logMigration(`目标目录不可写，降级到旧目录: ${e.message}`)
    return legacy
  }
  // 旧目录无数据库：无历史数据，在新位置初始化即可
  if (!fs.existsSync(path.join(legacy, 'app.db'))) return target
  try {
    migrateLegacyData(legacy, target)
    // 整体成功才写哨兵，防止 partial 拷贝（app.db 先到）被误判为已迁移
    fs.writeFileSync(migrationMarker(target), new Date().toISOString())
    logMigration(`迁移成功: ${legacy} -> ${target}`)
    if (!isAutoStart) {
      dialog.showMessageBoxSync({
        type: 'info',
        title: APP_NAME,
        message: '数据已迁移到软件目录',
        detail: `历史数据已从\n${legacy}\n迁移到\n${target}\n\n更新前的数据已备份至软件目录下的 migration-backup 文件夹，C 盘旧数据已清除。`,
      })
    }
    return target
  } catch (e) {
    logMigration(`迁移失败，回退旧目录: ${e.message}`)
    if (!isAutoStart) {
      dialog.showErrorBox(
        APP_NAME,
        `数据迁移失败，将暂时继续使用旧目录：\n${legacy}\n\n${e.message}`
      )
    }
    return legacy
  }
}

// 把"更新前"数据留一份到程序文件夹下的备份目录（仅保留最近一次）。
// 备份失败不阻断迁移（数据已进 target），仅据此决定是否清 C 盘。
function saveMigrationBackup(legacy) {
  const backup = migrationBackupDir()
  // 仅保留最近一次：先清空旧备份
  try {
    fs.rmSync(backup, { recursive: true, force: true })
  } catch (_) {
    // 旧备份不存在或清理失败，继续重建
  }
  fs.mkdirSync(backup, { recursive: true })
  const r = runRobocopy(legacy, backup)
  if (r.status == null || r.status >= 8) {
    logMigration(`迁移前备份失败（robocopy ${r.status}），保留 C 盘旧数据兜底`)
    return false
  }
  return true
}

// 用 robocopy 把旧数据迁移到新目录，并把"更新前"数据备份到程序文件夹下；
// 备份成功后才清除 C 盘旧数据（数据安全优先于磁盘清理）。
// 不用 fs.cpSync：它在中文路径 + 大目录下会触发段错误（见打包脚本同类教训）。
function migrateLegacyData(legacy, target) {
  fs.mkdirSync(target, { recursive: true })
  const r = runRobocopy(legacy, target)
  // robocopy 退出码 0–7 均为成功；>=8 才是错误
  if (r.status == null || r.status >= 8) {
    throw new Error(`数据复制失败（robocopy 退出码 ${r.status}）${robocopyHint(r)}`)
  }
  if (!fs.existsSync(path.join(target, 'app.db'))) {
    throw new Error('复制完成后未在目标目录找到 app.db')
  }
  // 先留一份"更新前"备份；备份成功才清除 C 盘旧数据
  if (saveMigrationBackup(legacy)) {
    try {
      fs.rmSync(legacy, { recursive: true, force: true })
    } catch (_) {
      // 删除失败不视为迁移失败（旧目录残留仅占空间，用户可手动清理）
    }
  }
}

function startBackend(port, dataDirPath) {
  const opts = { cwd: dataDirPath || app.getPath('userData') }
  // 打包模式：便携数据目录经 ZHISHI_DATA_DIR 传给后端作为唯一数据根
  if (dataDirPath) opts.env = { ...process.env, ZHISHI_DATA_DIR: dataDirPath }
  backend = spawn(backendExePath(), ['--port', String(port)], opts)
  backend.stdout.on('data', (d) => process.stdout.write(d))
  backend.stderr.on('data', (d) => process.stderr.write(d))
  // spawn 失败（exe 缺失/权限不足）触发 'error' 而非 'exit'，必须单独处理
  backend.on('error', (e) => {
    dialog.showErrorBox(APP_NAME, `无法启动后端服务：${e.message}`)
    app.quit()
  })
  // code 0 = 正常退出（/shutdown 或托盘退出）-> 退 app；非 0 = 崩溃，提示
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

// 拉取应用设置到内存缓存：close 行为与悬浮窗开关由此即时读取
async function loadAppSettings() {
  try {
    const res = await fetch(`http://127.0.0.1:${activePort}/settings`)
    if (res.ok) appSettings = { ...appSettings, ...(await res.json()) }
  } catch (_) {
    // 拉取失败按默认值继续，不阻断启动
  }
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
  // 关闭按钮行为由应用设置决定：最小化到托盘 / 退出知时 / 每次询问
  mainWindow.on('close', (e) => {
    if (isQuitting) return
    e.preventDefault()
    const behavior = appSettings.close_button_behavior || 'minimize'
    if (behavior === 'quit') {
      shutdownAndQuit()
    } else if (behavior === 'ask') {
      if (mainWindow.webContents && !mainWindow.webContents.isDestroyed()) {
        mainWindow.webContents.send('ask-close')
      }
    } else {
      mainWindow.hide()
    }
  })
  // 非自启模式窗口创建即显示，直接置 mainEverShown，避免 show 事件时序竞态
  // （show 事件可能在监听器注册前触发）导致后续 hide 误判、悬浮窗不弹
  if (!isAutoStart) mainEverShown = true
  // 主窗口显隐联动悬浮窗：显示时隐藏悬浮窗，最小化时显示悬浮窗
  mainWindow.on('show', () => {
    mainEverShown = true
    hideAssistantFloat()
  })
  mainWindow.on('hide', () => {
    if (mainEverShown) showAssistantFloat()
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

// 全局快速捕获小窗：Ctrl+Shift+A 随时唤出，输入一句话回车即建任务。
// 初始隐藏（懒创建，首次按快捷键时才建窗），失焦自动隐藏，保持「随手唤出、随手消失」。
const CAPTURE_WIN = { width: 420, height: 260 }
function createCaptureWindow() {
  const { workArea } = screen.getPrimaryDisplay()
  captureWindow = new BrowserWindow({
    width: CAPTURE_WIN.width,
    height: CAPTURE_WIN.height,
    // 横向居中、偏上 1/4，贴近常见启动器（Spotlight/Alfred）的唤出位置
    x: workArea.x + Math.round((workArea.width - CAPTURE_WIN.width) / 2),
    y: workArea.y + Math.round(workArea.height / 4),
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
  const captureParams = new URLSearchParams({ view: 'capture' })
  if (app.isPackaged) captureParams.set('packaged', '1')
  captureWindow.loadURL(`http://127.0.0.1:${activePort}/?${captureParams}`)
  captureWindow.on('closed', () => {
    captureWindow = null
  })
  // 失焦自动隐藏（点击别处即收起），下次快捷键再唤出
  captureWindow.on('blur', () => {
    if (captureWindow && !captureWindow.isDestroyed() && captureWindow.isVisible()) {
      captureWindow.hide()
    }
  })
}

// 快捷键切换显隐：窗口不存在/已销毁则重建；隐藏则 show+focus，显示则 hide
function toggleCaptureWindow() {
  if (!captureWindow || captureWindow.isDestroyed()) {
    captureWindow = null
    createCaptureWindow()
  }
  if (!captureWindow) return
  if (captureWindow.isVisible()) {
    captureWindow.hide()
  } else {
    captureWindow.show()
    captureWindow.focus()
  }
}

// 知时助手悬浮窗：主窗口最小化到托盘时的替代入口。按钮态 <-> 面板态同一窗口 resize。
function createAssistantFloat() {
  if (assistantFloat) return
  const { workArea } = screen.getPrimaryDisplay()
  assistantFloat = new BrowserWindow({
    width: FLOAT_BUTTON.width,
    height: FLOAT_BUTTON.height,
    x: workArea.x + workArea.width - FLOAT_BUTTON.width - 16,
    y: workArea.y + workArea.height - FLOAT_BUTTON.height - 16,
    frame: false,
    resizable: false,
    maximizable: false,
    minimizable: false,
    skipTaskbar: true,
    alwaysOnTop: false, // 不置顶，避免影响游戏、观影
    transparent: true, // 透明背景，呈现圆形悬浮球
    backgroundColor: '#00000000', // 配合 transparent，Windows 下确保透明生效
    show: false,
    icon: path.join(__dirname, '..', 'build', 'icon.ico'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })
  const params = new URLSearchParams({ view: 'assistant' })
  if (app.isPackaged) params.set('packaged', '1')
  assistantFloat.loadURL(`http://127.0.0.1:${activePort}/?${params}`)
  assistantFloat.on('closed', () => {
    assistantFloat = null
  })
}

// 显示悬浮窗：仅当开关开启且主窗口曾显示过（开机自启不触发）
function showAssistantFloat() {
  if (appSettings.assistant_float_enabled !== 'true') return
  if (!mainEverShown) return
  if (!assistantFloat) createAssistantFloat()
  if (assistantFloat && !assistantFloat.isVisible()) assistantFloat.showInactive()
}

// 隐藏悬浮窗并通知前端切回按钮态
function hideAssistantFloat() {
  if (!assistantFloat) return
  if (assistantFloat.webContents && !assistantFloat.webContents.isDestroyed()) {
    assistantFloat.webContents.send('float:collapse')
  }
  if (assistantFloat.isVisible()) assistantFloat.hide()
}

function destroyAssistantFloat() {
  if (assistantFloat) {
    assistantFloat.destroy()
    assistantFloat = null
  }
}

// 小窗 -> 主进程：显示自身 / 关闭自身 / 唤出主窗口
ipcMain.on('reminder:show', () => {
  if (reminderWindow) reminderWindow.showInactive()
})
// 捕获小窗：前端 Esc / 空内容 Ctrl+Enter 时请求隐藏自身
ipcMain.on('capture:close', () => {
  if (captureWindow && !captureWindow.isDestroyed() && captureWindow.isVisible()) {
    captureWindow.hide()
  }
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

// 应用设置：前端保存后通知主进程更新内存缓存（后端为唯一真相源）
ipcMain.on('settings:changed', (_e, patch) => {
  if (!patch || typeof patch !== 'object') return
  const prevFloat = appSettings.assistant_float_enabled === 'true'
  appSettings = { ...appSettings, ...patch }
  const nextFloat = appSettings.assistant_float_enabled === 'true'
  if (prevFloat === nextFloat) return
  // 悬浮窗开关变化
  if (nextFloat) {
    // 开启：若主窗口当前不可见，立即显示悬浮窗
    if (mainWindow && !mainWindow.isVisible()) showAssistantFloat()
  } else {
    destroyAssistantFloat()
  }
})

// 关闭询问：前端回传用户选择（minimize / quit）
ipcMain.on('close:answer', (_e, choice) => {
  if (choice === 'quit') {
    shutdownAndQuit()
  } else if (mainWindow) {
    mainWindow.hide()
  }
})

// 悬浮窗尺寸切换：按钮态 <-> 面板态，保持右下角锚点并钳制在屏幕工作区内
ipcMain.on('float:set-size', (_e, w, h) => {
  if (!assistantFloat) return
  const width = Math.max(FLOAT_BUTTON.width, Number(w) || FLOAT_BUTTON.width)
  const height = Math.max(FLOAT_BUTTON.height, Number(h) || FLOAT_BUTTON.height)
  const bounds = assistantFloat.getBounds()
  const { workArea } = screen.getPrimaryDisplay()
  const x = Math.min(
    Math.max(workArea.x, bounds.x + bounds.width - width),
    workArea.x + workArea.width - width
  )
  const y = Math.min(
    Math.max(workArea.y, bounds.y + bounds.height - height),
    workArea.y + workArea.height - height
  )
  assistantFloat.setBounds({ x, y, width, height })
})

// 悬浮窗拖动：前端 pointerdown/move 触发，主进程按光标位置移动窗口
let floatDragOffset = null
ipcMain.on('float:drag-start', () => {
  if (!assistantFloat) return
  const cursor = screen.getCursorScreenPoint()
  const bounds = assistantFloat.getBounds()
  floatDragOffset = { dx: cursor.x - bounds.x, dy: cursor.y - bounds.y }
})
ipcMain.on('float:drag-move', () => {
  if (!assistantFloat || !floatDragOffset) return
  const cursor = screen.getCursorScreenPoint()
  assistantFloat.setPosition(
    Math.round(cursor.x - floatDragOffset.dx),
    Math.round(cursor.y - floatDragOffset.dy)
  )
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
// 路径下的读取误报。读写都直接操作注册表，注册表即唯一真相--即便应用外被禁用（如任务管理器
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

// 系统级空闲时间（秒）：用户在任意窗口操作都算活跃，知时在后台也能感知。
// 用于看板「连续工作」判定——避免窗口级事件检测把后台工作误判为离开。
ipcMain.handle('system:idle', async () => {
  try {
    return powerMonitor.getSystemIdleTime()
  } catch (_) {
    return 0
  }
})

app.whenReady().then(async () => {
  activePort = await findFreePort(PREFERRED_PORT)
  // 先准备数据目录（必要时从 AppData 迁移到软件目录），再启动后端
  const resolvedDataDir = prepareDataDir()
  startBackend(activePort, resolvedDataDir)
  try {
    await waitForBackend(activePort)
  } catch (e) {
    dialog.showErrorBox(APP_NAME, `后端服务启动失败：${e.message}`)
    app.quit()
    return
  }
  await loadAppSettings()
  createWindow()
  createTray()
  // 全局快速捕获：Ctrl+Shift+A 唤出/收起小窗，自启与手动启动都生效
  globalShortcut.register('Control+Shift+A', toggleCaptureWindow)
  // 开机自启：主窗口已静默到托盘，弹出独立提醒小窗
  if (isAutoStart) createReminderWindow()
}).catch((e) => {
  // 兜底：启动流程任何未捕获异常都给出提示而非静默闪退
  dialog.showErrorBox(APP_NAME, `启动失败：${e && e.message ? e.message : e}`)
  app.quit()
})

// 系统关机/登出前尽量走干净退出（备份 + 落盘）
app.on('before-quit', (e) => {
  if (!isQuitting && backend) {
    e.preventDefault()
    shutdownAndQuit()
  }
})

// 退出前注销全局快捷键，避免残留占用 Ctrl+Shift+A
app.on('will-quit', () => {
  globalShortcut.unregisterAll()
})
