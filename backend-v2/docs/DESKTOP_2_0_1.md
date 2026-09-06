# 知时 v2.0.1 桌面修复 · 2026-09-05

本次响应用户追加的图标四角与悬浮窗问题。完整私人秘书目标仍进行中，见 [迭代路线](PRIVATE_SECRETARY_ROADMAP.md)。

## 安装包

`E:\知时\backend-v2\release\desktop-2.0.1\zhishi-v2-Setup-2.0.1.exe`

- 大小：137267777 字节。
- SHA256：`93ae2e212de670d6a74ac783fc03c1a29b7460588d16a1498589a4a1b9dde8b7`。
- 桌面版本 2.0.1；后端运行代码未变，`/health` 的 API 版本仍为 2.0.0。
- 既有 2.0.0 安装包保留。本批没有替用户覆盖安装，也没有操作旧版或真实资料目录。

## 已实现

- 桌面图标、托盘图标及应用内标识的高光按圆角裁切，导出透明背景；ICO 包含七档尺寸。
- 首次启动显示悬浮窗；显示今日固定日程、未完成排期、今日截止及逾期待办。
- 快速记下保存为今日待办；勾选完成写入同一个 v2 数据库，并通知主界面刷新。
- 拖动顶部移动、收起/展开、切换置顶、隐藏，托盘「桌面悬浮窗」或 Ctrl+Alt+Z 唤回。
- 记住位置、可见性、置顶及收起偏好；显示器移除或工作区变化时重新限制在可见区域内。
- 「打开知时」进入主界面使用 AI 对话、附件与规划。悬浮窗快速记下不执行自然语言规划。
- 修复显式指定新数据目录却没有创建目录导致的启动失败。

## 实际证据

- 前端 `vue-tsc -b && vite build` 通过；240 tests / 18 files 通过。
- 桌面壳 7 tests 通过，覆盖旧数据路径隔离以及悬浮窗几何、筛选去重、IPC 来源/参数校验、偏好恢复和资源清理。
- PNG 四角 alpha=0；ICO 七档：16、24、32、48、64、128、256。
- 开发态真实 Electron 自检：`release/widget-check-20260905-221721/stdout.log`。
- 打包态真实 Electron 自检：`release/widget-check-20260905-222309/stdout.log`。
- 两次均验证真实 preload → IPC → 打包后端：表单新增任务，列表出现，点击完成，数据库状态变为 done；收起高度、实际置顶状态、隐藏和唤回；主窗关闭到托盘；退出后本次后端 PID 消失。
- 包内 10 个运行文件/图标与源码逐字节相同；前端产物逐文件哈希相同。打包器裁去 package.json 开发配置，保留版本 2.0.1、main.js 入口。
- 打包态截图：`release/widget-check-20260905-222309/widget.png`。
- 重现：`scripts/verify_widget.ps1`，也可传 `-Executable <win-unpacked\知时 v2.exe>`；脚本每次使用全新隔离资料目录。

## 验证边界

本批验证了打包程序，未重新执行 NSIS 安装/卸载或在现有用户安装上升级。多屏移除恢复和重启偏好有自动测试，未冒称完成物理拔屏或跨重启人工走查。系统快捷键如被其他应用占用，托盘入口仍可用。本批没有调用真实模型；不将桌面修复作为总体私人秘书目标已完成的证据。

## 源码归属

- `E:\知时\electron-v2`：main.js、widget.js、widget-preload.js、widget-renderer.js、widget.html、widget.css、assets/icon.svg/png/ico、assets/tray.png、scripts/gen-icon.js、scripts/widget.test.js、scripts/main.test.js、package.json 与 lock。
- `E:\知时\frontend-v2\app`：src/App.vue（标识裁切、跨窗口任务刷新），public/favicon.svg。
- 当前后端仓库：复验脚本与本批文档；frontend/dist 和 release 为构建产物，不入版本控制。
