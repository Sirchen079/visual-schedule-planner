# 开发指南

[返回首页](../README.md)

以下命令从仓库根目录执行，使用 Windows PowerShell。普通用户直接下载安装包即可。

## 从源码构建
以下命令用于 Windows PowerShell。准备 **Git、Python 3.12 和 Node.js 24（含 npm）**，首次安装依赖需要联网。源码包含前端、后端和桌面程序，需要按顺序构建。

### 1. 下载源码

```powershell
git clone https://github.com/Sirchen079/visual-schedule-planner.git
cd visual-schedule-planner
```

也可以下载源码 ZIP 并解压，然后在解压后的仓库根目录打开 PowerShell。根目录应能看到 `backend-v2`、`frontend-v2` 和 `electron-v2`。

### 2. 安装依赖

```powershell
python -m venv backend-v2/.venv
backend-v2/.venv/Scripts/python.exe -m pip install -r backend-v2/requirements-lock.txt
backend-v2/.venv/Scripts/python.exe -m pip install -e "./backend-v2[dev]"
npm --prefix frontend-v2/app ci
npm --prefix electron-v2 ci
```

如果系统找不到 `python`，先确认 Python 已加入 PATH，或使用 `py -3.12` 代替第一行的 `python`。这些命令直接调用虚拟环境里的 Python，无须执行激活脚本。

### 3. 构建并启动

```powershell
npm --prefix frontend-v2/app run build
backend-v2/.venv/Scripts/python.exe backend-v2/scripts/build.py
npm --prefix electron-v2 start
```

前端构建后由后端托管；后端构建脚本会启动临时实例，检查健康接口与正常退出。首次构建可能需要几分钟，等待命令成功结束后再执行下一条。完成后也可以双击根目录的 `start.bat` 启动。

### 4. 生成 Windows 安装包

完成上述构建后，在仓库根目录执行：

```powershell
npm --prefix electron-v2 run dist
```

安装包输出到 `electron-v2/dist/zhishi-Setup-2.18.0.exe`。构建产物、数据库和密钥不应提交到仓库。

发布新版本时，须将同一次构建生成的安装包、`.blockmap` 和 `latest.yml` 一起上传到相应 GitHub Release，再发布该版本。自动更新检查的是 Release，不是分支提交。开发预览不自动更新，也不携带 GitHub 凭据。

## 本地开发

在第一个 PowerShell 窗口启动后端：

```powershell
cd backend-v2
.venv/Scripts/python.exe -m zhishi.server.app --port 8421
```

另开一个 PowerShell 窗口，在仓库根目录启动前端：

```powershell
npm --prefix frontend-v2/app run dev
```

打开终端显示的本地地址，通常为 `http://localhost:5173`。Vite 将接口代理到 `127.0.0.1:8421`，保留原 Host，以通过后端的同源校验。不要将开发服务器或后端暴露到公网。

桌面模式使用构建后的后端与前端。修改前端后重新执行前端构建，修改 Python 后重新运行后端构建脚本，再启动 Electron。

## 代码结构

- `backend-v2/src/zhishi/domain/`：领域模型、校验和业务服务。
- `backend-v2/src/zhishi/agent/`：模型运行、工具、权限、上下文与会话保存。
- `backend-v2/src/zhishi/adapters/`：模型目录、文件解析、联网与 MCP 适配。
- `backend-v2/src/zhishi/server/`：FastAPI 应用、路由及 SSE 接口。
- `frontend-v2/app/src/`：Vue 视图、组件、Pinia 状态和 API 客户端。
- `electron-v2/`：后端进程管理、窗口、托盘、通知与系统交互。

业务数据以领域服务为入口，路由负责传输和响应校验。前端 REST 与 SSE 类型从后端定义生成。

## 运行测试

```powershell
Push-Location backend-v2
.venv/Scripts/python.exe -m pytest
Pop-Location
npm --prefix frontend-v2/app test
npm --prefix frontend-v2/app run build
npm --prefix electron-v2 test
```

后端测试使用临时数据库、合成文件和模型替身。桌面测试检查进程配置、悬浮窗与设置逻辑；后端打包脚本另含进程启动和退出检查。Electron 中的自检入口使用隔离数据目录，供本地打包诊断使用。

## 更新接口类型

改动响应模型或 SSE 事件定义后，重新导出并提交生成文件：

```powershell
Push-Location backend-v2
.venv/Scripts/python.exe scripts/export_contracts.py
Pop-Location
Copy-Item backend-v2/docs/contracts/events.d.ts frontend-v2/app/src/api/contracts/events.d.ts
node backend-v2/scripts/generate_rest_contract.mjs
npm --prefix frontend-v2/app run build
```

OpenAPI、事件 JSON Schema 和事件 TypeScript 定义位于 `backend-v2/docs/contracts/`。生成文件中的说明来自后端模型，修改说明时也应重新生成，避免两端不一致。

## 提交约定

只提交源码、必要的用户与开发文档、依赖锁和可复用测试。不要提交真实数据库、附件、日志、备份、凭据、个人路径、会话记录或临时实验产物。复现问题使用合成数据，注释说明行为、边界和原因。

当前源码不提供 1.x 数据导入工具；数据库启动时的补列逻辑仅处理当前数据模型的结构升级。
