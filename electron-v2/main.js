// 知时桌面主进程
// 职责：单实例锁、以子进程拉起自包含后端（zhishi-backend.exe）、就绪探测后承载 SPA、
//       系统托盘（关闭=隐藏到托盘）、未读通知轮询、优雅退出（POST /shutdown → kill）。
// 后端进程接口：`--port N`、`GET /health`、`POST /shutdown`、
//       `ZHISHI_DATA_DIR` 定数据根；安全模型为 Host 回环白名单 + Origin 同源校验，
// 后端仅供本机桌面程序使用，依赖回环监听及 Host/Origin 校验。
const { app, BrowserWindow, Tray, Menu, Notification, dialog, shell, nativeImage } = require('electron')
const { spawn, exec } = require('child_process')
const fs = require('fs')
const path = require('path')
const net = require('net')
const http = require('http')

const APP_NAME = '知时'
const APP_ID = 'local.zhishi.v2' // 通知 toast 需要 AppUserModelId
const HEALTH_TRIES = 150 // 就绪探测：最多 150 次 × 200ms
const HEALTH_INTERVAL = 200
const SHUTDOWN_TIMEOUT = 2000 // /shutdown 2s 超时后强杀
const NOTIFY_INTERVAL = 30_000 // 未读通知轮询周期
const BG_COLOR = '#1c1815' // 窗口初始背景，与前端 --bg-app 一致。

let mainWindow = null
let widget = null
let desktopSettings = null
let tray = null
let backend = null
let backendPort = 0
let dataRoot = null
let isQuitting = false
let backendGaveUp = false // 启动失败已判定，避免 exit 事件再叠加弹框
let notifyTimer = null
let notifiedIds = new Set() // 已弹过系统通知的未读 id，防止每 30s 重复弹同一条
let backendPid = 0 // 后端子进程 PID，用于退出检测和诊断。
let smokePageLoaded = false // 自检步骤①等 did-finish-load 的事件到达标记

// 自检模式：真断言链（加载→标题→可见→关闭隐藏→退出后 PID 消失），任一步失败非零退出
const SMOKE = process.argv.includes('--smoke-quit')
// 通知实弹自检：--notify-selftest 跳过「用户正在看」守卫，强制验证系统通知弹窗链路
const NOTIFY_SELFTEST = process.argv.includes('--notify-selftest')
// 开发态强制：即便运行打包态 electron 也从仓库产物目录拉后端（调试用）
const FORCE_DEV = process.argv.includes('--dev')

// ---------- 单实例锁 ----------
// 用户数据目录可显式覆盖（测试/多开隔离用）：单实例锁按 userData 路径判定，
// 必须在 requestSingleInstanceLock 之前生效，否则打包态冒烟会与已装实例互斥。
if (process.env.ZHISHI_SHELL_USER_DATA_DIR) {
  app.setPath('userData', process.env.ZHISHI_SHELL_USER_DATA_DIR)
} else {
  // 固定且独立于产品显示名；安装目录被升级/卸载删除时不能连带用户数据。
  app.setPath('userData', path.join(app.getPath('appData'), 'ZhishiV2'))
}
const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  // 未拿到锁：仅退出，不注册 whenReady（app.quit 与 ready 存在时序竞态，必须从源头隔离）
  app.quit()
} else {
  app.on('second-instance', (_e, commandLine) => {
    // 第二实例带 --quit：让已有实例优雅退出（更新器/脚本的干净退出入口）
    if (commandLine.includes('--quit')) {
      shutdownAndQuit()
      return
    }
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.show()
      mainWindow.focus()
    }
  })
}

// ---------- 路径解析 ----------
// 后端目录：打包态 resources/zhishi-backend（extraResources 带入）；
// 开发态仓库产物 ../backend-v2/dist/zhishi-backend（app.isPackaged 路径探测，--dev 可强制）。
function backendDir() {
  if (!app.isPackaged || FORCE_DEV) {
    return path.join(__dirname, '..', 'backend-v2', 'dist', 'zhishi-backend')
  }
  return path.join(process.resourcesPath, 'zhishi-backend')
}

function backendExePath() {
  return path.join(backendDir(), 'zhishi-backend.exe')
}

// 数据根：打包态 userData/data（安装/卸载不会删除）；开发态壳仓库内 dev-data/
// 开发数据与安装版数据使用独立目录。
// 环境变量 ZHISHI_SHELL_DATA_DIR 可显式覆盖（测试/多开隔离用）。
function resolveDataRoot() {
  if (process.env.ZHISHI_SHELL_DATA_DIR) {
    const explicit = process.env.ZHISHI_SHELL_DATA_DIR
    fs.mkdirSync(path.join(explicit, 'v2'), { recursive: true })
    return explicit
  }
  const portable = app.isPackaged
    ? path.join(app.getPath('userData'), 'data')
    : path.join(__dirname, 'dev-data')
  try {
    fs.mkdirSync(path.join(portable, 'v2'), { recursive: true })
    return portable
  } catch (_) {
    // 便携目录不可写（如装进受保护目录）：降级到用户数据目录，保证可用
    const fallback = path.join(app.getPath('userData'), 'data')
    fs.mkdirSync(path.join(fallback, 'v2'), { recursive: true })
    return fallback
  }
}

// ---------- 后端进程管理 ----------
// 随机空闲端口：向系统要一个 127.0.0.1 的可用端口，避免与现网 8421/旧壳 18731 冲突
function findFreePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer()
    srv.on('error', reject)
    srv.listen(0, '127.0.0.1', () => {
      const port = srv.address().port
      srv.close(() => resolve(port))
    })
  })
}

function backendLogPath() {
  return path.join(dataRoot, 'v2', 'logs', 'app.log')
}

// 启动失败/崩溃：中文对话框（含日志路径）后退出
function fatal(title, detail) {
  backendGaveUp = true
  if (backend) {
    try { backend.kill() } catch (_) { /* 已退出 */ }
    backend = null
  }
  if (SMOKE) {
    // 自检场景无人点确认框：对话框会卡死自动化，降级为 stderr + 非零退出
    console.error(`[smoke] FAIL @ 启动：${title}：${detail}（日志：${backendLogPath()}）`)
    app.exit(1)
    return
  }
  dialog.showErrorBox(APP_NAME, `${title}\n\n${detail}\n\n日志：${backendLogPath()}`)
  app.exit(1)
}

function startBackend(port) {
  const exe = backendExePath()
  if (!fs.existsSync(exe)) {
    fatal('后端程序缺失', `未找到后端可执行文件：\n${exe}`)
    return
  }
  backend = spawn(exe, ['--port', String(port)], {
    cwd: dataRoot,
    windowsHide: true,
    env: { ...process.env, ZHISHI_DATA_DIR: dataRoot },
  })
  backendPid = backend.pid
  console.log(`[shell] 后端已启动 pid=${backend.pid} port=${port} dataRoot=${dataRoot} exe=${exe}`)
  backend.stdout.on('data', (d) => process.stdout.write(d))
  backend.stderr.on('data', (d) => process.stderr.write(d))
  // spawn 失败（exe 缺失/权限不足）走 'error' 而非 'exit'，必须单独处理
  backend.on('error', (e) => fatal('无法启动后端服务', e.message))
  backend.on('exit', (code) => {
    backend = null
    if (isQuitting || backendGaveUp) return // 主动退出流程中的正常谢幕，不打扰
    fatal('后端服务异常退出', `进程退出代码：${code}`)
  })
}

// 就绪探测：轮询 /health，最多 tries × 200ms，返回实际探测次数
function waitForBackend(port, tries = HEALTH_TRIES) {
  return new Promise((resolve, reject) => {
    let n = 0
    const attempt = () => {
      n++
      const req = http.get({ hostname: '127.0.0.1', port, path: '/health', timeout: 1000 }, (res) => {
        res.resume()
        if (res.statusCode === 200) return resolve(n)
        if (n >= tries) return reject(new Error(`/health 返回 ${res.statusCode}`))
        setTimeout(attempt, HEALTH_INTERVAL)
      })
      req.on('error', () => {
        if (n >= tries) return reject(new Error('/health 探测超时（30s 内未就绪）'))
        setTimeout(attempt, HEALTH_INTERVAL)
      })
      req.on('timeout', () => req.destroy()) // 触发 error 分支统一重试
    }
    attempt()
  })
}

// 优雅退出第一步：POST /shutdown（带超时，失败不阻塞，后续强杀兜底）
function postShutdown(port, timeoutMs) {
  return new Promise((resolve) => {
    const req = http.request(
      { hostname: '127.0.0.1', port, path: '/shutdown', method: 'POST', timeout: timeoutMs },
      (res) => { res.resume(); res.on('end', resolve) }
    )
    req.on('error', () => resolve())
    req.on('timeout', () => { req.destroy(); resolve() })
    req.end()
  })
}

function getJson(p) {
  return new Promise((resolve, reject) => {
    http.get({ hostname: '127.0.0.1', port: backendPort, path: p }, (res) => {
      let raw = ''
      res.setEncoding('utf8')
      res.on('data', (d) => { raw += d })
      res.on('end', () => {
        try { resolve(JSON.parse(raw)) } catch (e) { reject(e) }
      })
    }).on('error', reject)
  })
}

// ---------- 窗口 ----------
function widgetRequest(p, method = 'GET', body) {
  return new Promise((resolve, reject) => {
    const data = body === undefined ? undefined : JSON.stringify(body)
    const req = http.request({ hostname: '127.0.0.1', port: backendPort, path: p, method,
      timeout: 8000, headers: data ? { 'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(data) } : {} }, res => {
      let raw = ''
      res.setEncoding('utf8')
      res.on('data', chunk => { raw += chunk })
      res.on('error', reject)
      res.on('end', () => {
        if (res.statusCode < 200 || res.statusCode >= 300) return reject(new Error(`服务返回 ${res.statusCode}`))
        try {
          const result = JSON.parse(raw)
          if (method !== 'GET' && mainWindow && !mainWindow.isDestroyed()) {
            mainWindow.webContents.executeJavaScript(
              "window.dispatchEvent(new Event('zhishi:tasks-changed'))").catch(() => {})
          }
          resolve(result)
        } catch (_) { reject(new Error('服务返回了无效数据')) }
      })
    })
    req.on('error', reject)
    req.on('timeout', () => req.destroy(new Error('连接超时，请稍后刷新')))
    req.end(data)
  })
}

function showMainWindow(targetPath) {
  if (!mainWindow || mainWindow.isDestroyed()) return
  if (mainWindow.isMinimized()) mainWindow.restore()
  if (typeof targetPath === 'string') {
    void mainWindow.webContents.executeJavaScript(`location.hash = ${JSON.stringify(targetPath)}`)
  }
  mainWindow.show()
  mainWindow.focus()
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 960,
    minHeight: 640,
    title: APP_NAME,
    icon: path.join(__dirname, 'assets', 'icon.png'),
    autoHideMenuBar: true,
    show: false,
    // 遮挡 UI：与前端暗色书房主题同色，加载过程无白闪
    backgroundColor: BG_COLOR,
    webPreferences: {
      preload: path.join(__dirname, 'main-preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })
  mainWindow.loadURL(`http://127.0.0.1:${backendPort}/`)
  mainWindow.once('ready-to-show', () => mainWindow.show())
  // 钉住中文标题「知时」：SPA 会把 document.title 改为「今日 · 知时」等页内标题，窗口保持壳标题
  mainWindow.on('page-title-updated', (e) => e.preventDefault())
  // 关闭按钮 = 隐藏到托盘（不退出）；真退出只有托盘菜单「退出」
  mainWindow.on('close', (e) => {
    if (isQuitting) return
    e.preventDefault()
    mainWindow.hide()
  })
  // 外链（target=_blank）一律交系统默认浏览器，不在壳内开新窗
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/i.test(url)) shell.openExternal(url)
    return { action: 'deny' }
  })
  mainWindow.webContents.on('did-finish-load', () => {
    smokePageLoaded = true
    console.log(`[shell] 页面已加载 url=http://127.0.0.1:${backendPort}/`)
  })
}

// ---------- 托盘 ----------
function createTray() {
  let icon = nativeImage.createFromPath(path.join(__dirname, 'assets', 'tray.png'))
  if (icon.isEmpty()) {
    console.warn('[shell] 托盘图标缺失（assets/tray.png），使用空图标兜底')
    icon = nativeImage.createEmpty()
  }
  tray = new Tray(icon)
  tray.setToolTip(APP_NAME)
  updateTrayMenu()
  tray.on('click', showMainWindow)
  console.log('[shell] 托盘已创建')
}

function updateTrayMenu() {
  if (!tray) return
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: '显示主窗', click: showMainWindow },
    { label: '桌面悬浮窗', type: 'checkbox', checked: widget?.isVisible() ?? true,
      click: () => widget?.toggle() },
    { label: '悬浮窗与功能设置', click: () => showMainWindow('/settings?section=desktop') },
    { type: 'separator' },
    { label: '退出', click: () => shutdownAndQuit() },
  ]))
}

// ---------- 通知轮询 ----------
// 每 30s GET /api/notifications/unread；count>0 且（窗口隐藏或失焦）时弹系统通知，
// 标题取最新一条未读；点击通知聚焦主窗。已读判定交给前端，本壳只负责提醒：
// 弹过的 id 记入 notifiedIds，避免同一条未读每 30s 重复打扰。
async function pollNotifications() {
  try {
    if (desktopSettings && !desktopSettings.snapshot().notifications) return
    const unread = await getJson('/api/notifications/unread')
    if (!unread || !(unread.count > 0)) {
      notifiedIds.clear() // 已清零：重置提醒记忆，后续新未读可再次提醒
      return
    }
    const userLooking =
      mainWindow && !mainWindow.isDestroyed() && mainWindow.isVisible() && mainWindow.isFocused()
    if (!NOTIFY_SELFTEST && userLooking) {
      return // 用户正在看，不打扰（也不标记，转后台后仍会提醒）
    }
    const list = await getJson('/api/notifications?limit=50')
    const unreadItems = (Array.isArray(list) ? list : [])
      .filter((n) => n && n.read_at == null && !notifiedIds.has(n.id))
    if (!unreadItems.length) return
    // 最新一条：remind_at 降序，其次 id 降序
    unreadItems.sort((a, b) =>
      String(b.remind_at || '').localeCompare(String(a.remind_at || '')) || (b.id - a.id)
    )
    const latest = unreadItems[0]
    for (const n of unreadItems) {
      notifiedIds.add(n.id)
      if (notifiedIds.size > 500) notifiedIds = new Set([...notifiedIds].slice(-200))
    }
    const toast = new Notification({
      title: latest.title || APP_NAME,
      body: (latest.body || '') + (unreadItems.length > 1 ? `\n另有 ${unreadItems.length - 1} 条新通知，请在通知中心查看。` : ''),
      icon: path.join(__dirname, 'assets', 'icon.png'),
      silent: false,
    })
    toast.on('click', () => {
      const target = latest.target_path || (Number.isSafeInteger(latest.task_id) && latest.task_id > 0 ? `/board?task=${latest.task_id}` : '')
      const internal = /^\/ledger\?bill=[1-9]\d*$/.test(target) || /^\/calendar\?date=\d{4}-\d{2}-\d{2}&event=[1-9]\d*$/.test(target) || /^\/board\?task=[1-9]\d*$/.test(target) || /^\/research\?project=[1-9]\d*(?:&followup=[1-9]\d*)?$/.test(target)
      showMainWindow(internal ? target : undefined)
    })
    toast.on('show', () => console.log('[shell] Notification show 事件已触发（系统已展示 toast）'))
    toast.on('failed', (_e, error) => console.error(`[shell] Notification 展示失败：${error}`))
    toast.show()
    console.log(`[shell] 已弹系统通知：${latest.title}（未读 ${unread.count} 条）`)
  } catch (_) {
    // 后端未就绪/瞬时失败：静默等下一轮
  }
}

function startNotifyPolling() {
  setTimeout(pollNotifications, 5000) // 首轮错开启动高峰
  notifyTimer = setInterval(pollNotifications, NOTIFY_INTERVAL)
}

function stopNotifyPolling() {
  if (notifyTimer) {
    clearInterval(notifyTimer)
    notifyTimer = null
  }
}

// ---------- 优雅退出 ----------
// 先 POST /shutdown（2s 超时）让后端备份落盘，等其自行退出；超时兜底 kill，最后 app.quit。
// 托盘「退出」与 before-quit（系统关机等）统一走此路径。
// opts.quit=false：自检模式复用同一关闭链（销毁托盘/窗口→/shutdown→等后端退出）但先不退出进程，
// 留给调用方做 OS 级断言后显式退出，保证退出码语义确定。
async function shutdownAndQuit(opts = {}) {
  if (isQuitting) return
  isQuitting = true
  stopNotifyPolling()
  if (desktopSettings) { desktopSettings.dispose(); desktopSettings = null }
  if (widget) { widget.dispose(); widget = null }
  if (tray) { tray.destroy(); tray = null }
  if (mainWindow && !mainWindow.isDestroyed()) { mainWindow.destroy(); mainWindow = null }
  if (backend && backendPort) {
    console.log(`[shell] 优雅退出：POST /shutdown -> 127.0.0.1:${backendPort}`)
    await postShutdown(backendPort, SHUTDOWN_TIMEOUT)
    await new Promise((resolve) => {
      const t = setTimeout(() => {
        console.log('[shell] 后端未在超时内退出，强杀兜底')
        try { backend.kill() } catch (_) { /* 已退出 */ }
        resolve()
      }, SHUTDOWN_TIMEOUT)
      if (backend) {
        backend.once('exit', () => { clearTimeout(t); resolve() })
      } else {
        clearTimeout(t)
        resolve()
      }
    })
  }
  console.log('[shell] 退出完成')
  if (opts.quit === false) return
  app.quit()
}

// before-quit 钩子：任何退出来源（系统关机/登出、app.quit）都先走优雅关闭
app.on('before-quit', (e) => {
  if (!isQuitting) {
    e.preventDefault()
    shutdownAndQuit()
  }
})

// 关闭按钮只是隐藏到托盘，窗口永不因 close 而清零；托盘常驻，退出统一走托盘/before-quit
app.on('window-all-closed', () => { /* 保持托盘常驻，不自动退出 */ })

// ---------- 自检模式（--smoke-quit） ----------
// 真断言链：任一步失败打印「FAIL @ 步骤N」并以退出码 1 退出；全部通过打印 SMOKE PASS 退出码 0。
// ① 等 did-finish-load（30s 超时）② 页面标题含「知时」③ 窗口可见
// ④ 触发 close → 断言隐藏到托盘且进程仍存活 ⑤ 托盘同款优雅退出 → tasklist 断言本次后端 PID 消失。
const SMOKE_LOAD_TIMEOUT = 30_000

function smokePass(step, msg) {
  console.log(`[smoke] 步骤${step} 通过：${msg}`)
}

async function smokeFail(step, detail) {
  console.error(`[smoke] FAIL @ 步骤${step}：${detail}`)
  // 失败也要清场：复用优雅退出链关掉后端，避免遗留孤儿进程污染下一次运行
  try { await shutdownAndQuit({ quit: false }) } catch (_) { /* 尽力而为 */ }
  app.exit(1)
}

// OS 级断言：tasklist 查询 PID 是否仍存在；查询失败按「仍存活」保守处理（宁可误报失败）
function isPidAlive(pid) {
  return new Promise((resolve) => {
    exec(`tasklist /FI "PID eq ${pid}" /FO CSV /NH`, { windowsHide: true }, (err, stdout) => {
      if (err) return resolve(true)
      resolve(stdout.includes(String(pid)))
    })
  })
}

async function runSmoke() {
  // ① 等 did-finish-load（runSmoke 与 loadURL 同一 tick 启动，监听事件即可覆盖全部情形）
  try {
    await new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error(`${SMOKE_LOAD_TIMEOUT / 1000}s 内未收到 did-finish-load`)),
        SMOKE_LOAD_TIMEOUT
      )
      const done = () => { clearTimeout(timer); resolve() }
      if (smokePageLoaded) return done()
      mainWindow.webContents.once('did-finish-load', done)
    })
    smokePass(1, 'did-finish-load 已到达')
  } catch (e) {
    return smokeFail(1, e.message)
  }

  // ② 页面标题含「知时」（SPA 可能把 document.title 改成「今日 · 知时」等，含「知时」即过）
  let pageTitle = ''
  try {
    pageTitle = await mainWindow.webContents.executeJavaScript('document.title')
  } catch (e) {
    return smokeFail(2, `executeJavaScript 失败：${e.message}`)
  }
  if (!pageTitle.includes(APP_NAME)) {
    return smokeFail(2, `页面标题不含「${APP_NAME}」，实际 document.title="${pageTitle}"`)
  }
  smokePass(2, `页面标题含「${APP_NAME}」："${pageTitle}"（窗口标题="${mainWindow.getTitle()}"）`)

  // 不只检查 HTML 标题：JS 必须成功挂载真实应用。
  let mounted = false
  for (let i = 0; i < 100 && !mounted; i++) {
    mounted = await mainWindow.webContents.executeJavaScript(
      'Boolean(document.querySelector("#app .app-shell"))')
    if (!mounted) await new Promise((r) => setTimeout(r, 100))
  }
  if (!mounted) return smokeFail(2, 'SPA 未挂载（#app .app-shell 缺失）')
  smokePass(2, 'SPA 已挂载，前端 JS 已实际执行')

  const stateMode = process.env.ZHISHI_SMOKE_STATE
  if (stateMode) {
    if (!process.env.ZHISHI_SHELL_USER_DATA_DIR || !['seed', 'check'].includes(stateMode)) {
      return smokeFail(2, '持久化自检必须显式设置隔离 userData，且模式为 seed/check')
    }
    try {
      if (stateMode === 'seed') {
        await mainWindow.webContents.executeJavaScript(`(async () => {
          const s = await fetch('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'},
            body:JSON.stringify({settings:{'ui.theme':'light'}})});
          if (!s.ok) throw new Error('settings: '+s.status);
          const t = await fetch('/api/tasks', {method:'POST', headers:{'Content-Type':'application/json'},
            body:JSON.stringify({title:'release-persistence-check'})});
          if (!t.ok) throw new Error('task: '+t.status);
        })()`)
      } else {
        let restored = false
        for (let i = 0; i < 100 && !restored; i++) {
          restored = await mainWindow.webContents.executeJavaScript(
            'document.documentElement.dataset.theme === "light"')
          if (!restored) await new Promise((r) => setTimeout(r, 100))
        }
        if (!restored) throw new Error('新端口未恢复浅色主题')
        await mainWindow.webContents.executeJavaScript(`(async () => {
          const r = await fetch('/api/tasks');
          if (!r.ok || !(await r.json()).some(t=>t.title==='release-persistence-check'))
            throw new Error('重启后任务未保留');
        })()`)
      }
      smokePass(2, '隔离持久化 ' + stateMode + ' 通过，port=' + backendPort)
    } catch (e) { return smokeFail(2, e.message) }
  }
  if (process.env.ZHISHI_SMOKE_SCREENSHOT) {
    const shot = await mainWindow.webContents.capturePage()
    fs.writeFileSync(process.env.ZHISHI_SMOKE_SCREENSHOT, shot.toPNG())
  }

  // ③ 窗口可见（ready-to-show 显示；留最多 5s 余量后断言）
  let visible = false
  for (let i = 0; i < 50 && !visible; i++) {
    visible = mainWindow.isVisible()
    if (!visible) await new Promise((r) => setTimeout(r, 100))
  }
  if (!visible) return smokeFail(3, '窗口 5s 内未进入可见状态（isVisible=false）')
  smokePass(3, '窗口可见 isVisible=true')
  if (NOTIFY_SELFTEST) {
    try {
      if (!Notification.isSupported()) throw new Error('当前系统不支持原生通知')
      const toast = new Notification({ title: '知时安装验收', body: '隔离测试通知，无需操作。', silent: true })
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => { toast.close(); reject(new Error('通知 show 事件超时')) }, 10000)
        toast.once('show', () => { clearTimeout(timer); resolve() })
        toast.once('failed', (_event, error) => { clearTimeout(timer); reject(new Error(String(error))) })
        toast.show()
      })
      smokePass(3, '原生通知 show 事件通过（可见呈现仍受系统通知策略影响）')
      toast.close()
    } catch (e) { return smokeFail(3, e.message) }
  }

  if (process.argv.includes('--widget-selftest')) {
    try { await runWidgetSmoke() } catch (e) { return smokeFail('悬浮窗', e.message) }
  }
  if (process.argv.includes('--settings-selftest')) {
    try { await require('./settings-selftest').run({ mainWindow, widget, getJson }) }
    catch (e) { return smokeFail('设置', e.message) }
  }

  // ④ 触发 close：应被拦截并隐藏到托盘，窗口不销毁、app 进程仍存活
  mainWindow.close()
  await new Promise((r) => setTimeout(r, 500))
  if (mainWindow.isDestroyed()) return smokeFail(4, 'close 后窗口被销毁（应隐藏到托盘而非销毁）')
  if (mainWindow.isVisible()) return smokeFail(4, 'close 后窗口仍可见（应已隐藏到托盘）')
  if (!tray) return smokeFail(4, '托盘对象缺失（藏托盘语义不成立）')
  if (!app.isReady()) return smokeFail(4, 'app 未处于 ready 状态（进程存活语义不成立）')
  smokePass(4, 'close 后 isVisible=false，窗口未销毁，进程存活，托盘在位')

  // ⑤ 托盘「退出」同款路径优雅退出：/shutdown → 等后端自行退出，再 OS 级断言 PID 消失
  if (!(backendPid > 0)) return smokeFail(5, '启动时未记录到后端子进程 PID')
  console.log(`[smoke] 步骤5 开始：触发托盘同款优雅退出（本次 backend pid=${backendPid}）…`)
  await shutdownAndQuit({ quit: false })
  if (await isPidAlive(backendPid)) {
    return smokeFail(5, `tasklist 仍可见本次 backend pid=${backendPid}，后端进程未随壳退出`)
  }
  smokePass(5, `tasklist 断言通过：本次 backend pid=${backendPid} 已消失，app 即将退出`)
  console.log('SMOKE PASS')
  app.exit(0)
}

async function runWidgetSmoke() {
  if (!process.env.ZHISHI_SHELL_USER_DATA_DIR || !process.env.ZHISHI_SHELL_DATA_DIR) {
    throw new Error('悬浮窗自检必须显式隔离 userData 和数据库')
  }
  widget.show()
  const win = widget.getWindow()
  const js = code => win.webContents.executeJavaScript(code)
  let ready = false
  for (let i = 0; i < 100; i++) {
    if (!win.webContents.isLoading() && await js('Boolean(window.zhishiWidget && document.querySelector(".widget-chat textarea"))')) { ready = true; break }
    await new Promise(r => setTimeout(r, 100))
  }
  if (!ready) throw new Error('悬浮对话未加载')
  const initial = await js('window.zhishiWidget.state()')
  if (initial.collapsed) await js('document.getElementById("widget-collapse").click()')
  if (!initial.pinned) await js('document.getElementById("widget-pin").click()')
  await new Promise(r => setTimeout(r, 150))
  const draft = '明天安排20分钟阅读'
  await js(`(() => { const e=document.querySelector('textarea'); e.value=${JSON.stringify(draft)}; e.dispatchEvent(new Event('input',{bubbles:true})) })()`)
  if (!await js('Boolean(document.querySelector(".widget-chat .send:not([disabled])") && document.querySelector("input[type=file]"))')) throw new Error('对话发送或附件入口缺失')
  if (process.env.ZHISHI_WIDGET_SCREENSHOT) fs.writeFileSync(process.env.ZHISHI_WIDGET_SCREENSHOT, (await win.webContents.capturePage()).toPNG())
  await js('document.getElementById("widget-collapse").click()')
  await new Promise(r => setTimeout(r, 100))
  if (win.getBounds().height !== 78) throw new Error('收起高度错误')
  await js('document.getElementById("widget-collapse").click()')
  await new Promise(r => setTimeout(r, 100))
  if (await js('document.querySelector("textarea").value') !== draft) throw new Error('收起丢失对话草稿')
  await js('document.getElementById("widget-pin").click()')
  await new Promise(r => setTimeout(r, 100))
  if (win.isAlwaysOnTop()) throw new Error('取消置顶失败')
  await js('document.getElementById("widget-pin").click()')
  await new Promise(r => setTimeout(r, 100))
  if (!win.isAlwaysOnTop()) throw new Error('置顶失败')
  await js('window.zhishiWidget.openMain("/calendar")')
  await new Promise(r => setTimeout(r, 100))
  if (!await mainWindow.webContents.executeJavaScript('location.hash.includes("/calendar")')) throw new Error('主窗跳转失败')
  widget.hide()
  if (win.isVisible()) throw new Error('隐藏失败')
  widget.show()
  if (!win.isVisible()) throw new Error('重新唤回失败')
  smokePass('悬浮窗', '真实悬浮对话、附件与发送入口、草稿保留、收起、置顶、隐藏唤回、主窗跳转均通过')
}

// ---------- 启动（仅持有单实例锁的实例执行） ----------
if (gotLock) {
  app.whenReady().then(async () => {
    app.setAppUserModelId(APP_ID)
    dataRoot = resolveDataRoot()
    let port
    try {
      port = await findFreePort()
    } catch (e) {
      return fatal('端口探测失败', e.message)
    }
    backendPort = port
    startBackend(port)
    let tries
    try {
      tries = await waitForBackend(port)
    } catch (e) {
      return fatal('后端服务启动失败', e.message)
    }
    console.log(`[shell] /health 就绪（第 ${tries} 次探测）`)
    createWindow()
    createTray()
    widget = require('./widget').createWidget({ electron: require('electron'),
      request: widgetRequest, showMainWindow, baseUrl: `http://127.0.0.1:${backendPort}`, stateDir: app.getPath('userData'),
      onVisibility: () => updateTrayMenu() })
    desktopSettings = require('./desktop-settings').createDesktopSettings({ ipcMain: require('electron').ipcMain,
      getMainWindow: () => mainWindow, widget, baseUrl: `http://127.0.0.1:${backendPort}`, stateDir: app.getPath('userData') })
    updateTrayMenu()
    startNotifyPolling()
    if (SMOKE) {
      runSmoke().catch(async (e) => {
        // 自检失败不弹对话框（自动化场景无人点确认）：打印失败步骤后清场非零退出
        console.error(`[smoke] FAIL @ 未预期异常：${e && e.stack ? e.stack : e}`)
        try { await shutdownAndQuit({ quit: false }) } catch (_) { /* 尽力而为 */ }
        app.exit(1)
      })
    }
  }).catch((e) => {
    dialog.showErrorBox(APP_NAME, `启动失败：${e && e.message ? e.message : e}`)
    app.exit(1)
  })
}
