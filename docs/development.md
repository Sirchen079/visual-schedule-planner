# 开发指南

[返回首页](../README.md)

完整桌面构建步骤见首页。以下命令均从仓库根目录执行，默认已经安装 Python 和 npm 依赖。

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

后端测试使用临时数据库和模型替身。个人课表附件不发布，少数依赖这些附件的测试会跳过；合成样本仍覆盖导入流程。桌面测试检查进程配置、悬浮窗与设置逻辑；后端打包脚本另含进程启动和退出检查。Electron 中的自检入口使用隔离数据目录，供本地打包诊断使用。

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
