// 预加载脚本：向前端注入最小标记，供其判断是否运行在桌面壳内。
// contextIsolation 开启，仅暴露只读信息，不放开 Node 能力。
const { contextBridge } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  isDesktop: true,
  platform: process.platform,
})
