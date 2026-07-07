# 知时 · 桌面应用打包

把 FastAPI + Vue3 项目封装为 Windows 桌面应用并生成安装包。

## 架构

- **Electron 主进程** (`electron/main.js`)：创建窗口、系统托盘、单实例锁，
  并以子进程方式拉起后端 `zhishi-backend.exe`。
- **后端**：PyInstaller 打包（onedir），内含 `frontend/dist` 静态资源，
  FastAPI 单端口同时提供 API 与界面。
- **数据**：用户数据写入 `%APPDATA%\知时\data\`，卸载不删除。

## 前置

- Python 3.11+（后端 venv）
- Node.js 18+（前端构建与 Electron 打包）

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

# 4. 安装 Electron 依赖并打包安装包
npm install
npm run dist
```

产物：`desktop\release\知时 Setup 1.0.0.exe`

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
- 单实例锁：重复启动会聚焦已有窗口。

## 退出语义

- 关闭主窗口 → 最小化到系统托盘（后台常驻）。
- 托盘菜单「退出」→ 调 `/shutdown` 备份并落盘后退出。
- 前端原有「关闭服务」按钮在桌面模式下等效于退出整个应用。
