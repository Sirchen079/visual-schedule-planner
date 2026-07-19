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
  // 应用设置：前端保存后通知主进程更新内存缓存
  notifySettingsChanged: (patch) => ipcRenderer.send('settings:changed', patch),
  onSettingsChanged: (cb) => ipcRenderer.on('settings:changed', (_e, patch) => cb(patch)),
  // 关闭询问：主进程请求前端弹框选择，前端回传 minimize / quit
  onAskClose: (cb) => ipcRenderer.on('ask-close', () => cb()),
  answerClose: (choice) => ipcRenderer.send('close:answer', choice),
  // 悬浮窗尺寸切换（按钮态 <-> 面板态）与被收起通知
  floatSetSize: (w, h) => ipcRenderer.send('float:set-size', w, h),
  onFloatCollapse: (cb) => ipcRenderer.on('float:collapse', () => cb()),
  // 悬浮窗拖动（按钮态前端区分点击/拖动后触发，主进程按光标位置移动窗口）
  floatDragStart: () => ipcRenderer.send('float:drag-start'),
  floatDragMove: () => ipcRenderer.send('float:drag-move'),
  // 全局快速捕获小窗：请求隐藏自身
  captureClose: () => ipcRenderer.send('capture:close'),
  // 系统级空闲秒数（任意窗口操作都算活跃，覆盖后台工作场景）
  getSystemIdleTime: () => ipcRenderer.invoke('system:idle'),
})
