# 知时 · 桌面应用打包

把 FastAPI + Vue3 项目封装为 Windows 桌面应用并生成安装包。

## 架构

- **Electron 主进程** (`electron/main.js`)：创建主窗口与系统托盘、单实例锁，
  以子进程方式拉起后端 `zhishi-backend.exe`；并实现开机自启（注册表 + `--autostart`
  参数区分启动来源）与独立的 DDL 提醒小窗（加载 `?view=reminder`）。
- **后端**：PyInstaller 打包（onedir），内含 `frontend/dist` 静态资源，
  FastAPI 单端口同时提供 API 与界面。
- **数据**：用户数据写入 `%APPDATA%\知时\data\`，卸载不删除。

## 前置

- Python 3.11+（后端 venv）
- Node.js 18+（前端构建与 Electron 打包）
- Inno Setup 6（编译安装包，默认路径 `D:\Inno Setup 6\ISCC.exe`）

## 一键打包

在项目根目录：

```powershell
# 1. 创建后端 venv 并安装依赖（首次，使用清华 PyPI 源）
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r backend\requirements.txt pyinstaller pillow

# 2. 生成应用图标（首次 / 图标源变更时）
python desktop\scripts\build-icon.py

# 3. 构建前端 + 打包后端 + 复制产物
cd desktop
node scripts\build-backend.js

# 4. 安装 Electron 依赖并打包（产出 win-unpacked）
npm install
npm run dist

# 5. 编译安装包（需 Inno Setup 6）
"D:\Inno Setup 6\ISCC.exe" installer\zhishi.iss
```

产物：`desktop\release-inno\知时 Setup.exe`（解压即用版：`desktop\release\win-unpacked\知时.exe`）

## 开发调试

```powershell
# 后端（开发模式，数据写仓库根 data/）
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 18731 --app-dir backend

# Electron（需先跑过 build-backend.js 产出 desktop\build\backend-dist\）
cd desktop
npm install
npm start
```

## 图标

`build/icon.ico`（多尺寸）与 `build/icon-256.png`（托盘）由 `scripts/build-icon.py`
从 `frontend/public/favicon.svg` 生成。替换图标源后重新运行该脚本与 `npm run dist`。

## 端口与单实例

- 默认监听 `127.0.0.1:18731`，被占用时自动顺延到下一空闲端口。
- 单实例锁：再次启动时，若新实例带 `--autostart`（开机自启触发），已有实例弹出 DDL 提醒小窗；否则聚焦已有主窗口。

## 启动与退出语义

- 手动启动：主窗口正常显示，并在窗口内弹出当日 DDL 提醒。
- 开机自启（`--autostart`）：主窗口静默到托盘（`show:false`），仅弹出独立的 DDL 提醒小窗。
- 关闭主窗口 → 最小化到系统托盘（后台常驻）。
- 托盘菜单「退出」→ 调 `/shutdown` 备份并落盘后退出。
- 前端原有「关闭服务」按钮在桌面模式下等效于退出整个应用。

## 升级与卸载保护（Inno Setup）

安装器在复制文件前（`PrepareToInstall`）与卸载开始时（`InitializeUninstall`）会先
`POST /shutdown` 优雅关闭正在运行的知时（触发后端备份 + 落盘），再用 `taskkill` 兜底强杀，
并配合 `CloseApplications=force` 作为第二道防线，避免文件占用导致安装/卸载失败。
用户数据位于 `%APPDATA%\知时\`，升级覆盖与卸载均不删除。
