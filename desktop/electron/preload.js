// 预加载脚本：向前端注入最小标记与受控能力。
// contextIsolation 开启，仅暴露只读信息与白名单 IPC，不放开 Node 能力。
// 注意：Electron 默认 sandbox，preload 内 require('electron').app 为 undefined；
// 故 isPackaged 改由主进程经 URL ?packaged=1 传入，前端从 location.search 读取。
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  isDesktop: true,
  platform: process.platform,
  // 开机自启：由主进程读写注册表 HKCU\Run（per-user，免管理员权限）
  getLoginItemSettings: () => ipcRenderer.invoke('login-item:get'),
  setLoginItemSettings: (openAtLogin) =>
    ipcRenderer.invoke('login-item:set', openAtLogin),
  // 独立提醒小窗控制（仅小窗内使用）
  showSelf: () => ipcRenderer.send('reminder:show'),
  closeSelf: () => ipcRenderer.send('reminder:close'),
  showMain: () => ipcRenderer.send('reminder:show-main'),
  showMainWithTask: (taskId) => ipcRenderer.send('reminder:show-main-task', taskId),
  // 主窗口监听：接收小窗「去处理」传来的 taskId
  onFocusTask: (cb) => ipcRenderer.on('focus-task', (_e, taskId) => cb(taskId)),
  // 用系统默认浏览器打开外链（如 GitHub 项目主页）
  openExternal: (url) => ipcRenderer.send('open-external', url),
})
