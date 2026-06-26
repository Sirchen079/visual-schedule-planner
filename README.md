# 可视化日程安排记录

把一团乱麻的事情理顺，缓解焦虑和灾难性思维。

一个本地单机的可视化日程管理工具：看板、总览、日历、时间轴、资料库一体，
配合标签、子任务、提醒、自动备份与回收站，专注于「数据不丢、随时可控」。

## 功能特性

**任务管理**
- 看板：新建、编辑、拖拽改状态、删除任务
- 子任务：拆分大任务为小步，勾选后按完成率自动计算进度
- 提醒：即将到期 / 逾期任务，铃铛角标 + 浏览器通知
- 数据校验：优先级与状态受控、进度与状态自动联动、上传有大小上限

**多视图**
- 总览：今日到期、本周截止、逾期、完成率
- 日历：月视图，按截止日落格，按标签颜色着色（无标签则按优先级）
- 时间轴：甘特式横向条（开始 → 结束日期），直观对比并行与冲突

**资料与组织**
- 资料库：上传任意文件、搜索、图片 / PDF 预览、删除
- 任务关联资料：任务弹窗中添加 / 移除相关资料
- 标签分类：任务打标签（科研 / 导师 / 杂事…），按名称自动配色，日历按颜色区分

**数据安全**
- 自动备份：每天备份数据库，关闭服务时再备一份，默认保留最近 7 份
- 回收站：任务与文件删除后保留 30 天可恢复，支持彻底清除与一键撤销
- 明 / 暗主题切换

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.11+、FastAPI、SQLAlchemy 2、SQLite、Uvicorn |
| 前端 | Vue 3、Vite、vuedraggable |
| 测试 | pytest |

生产模式下，由后端 FastAPI 在单一端口同时提供 API 与前端界面（托管 `frontend/dist`）。

## 项目结构

```
可视化日程安排记录/
├── backend/              # FastAPI 后端
│   ├── app/              # 应用代码（main、models、routers、services、config）
│   ├── tests/            # pytest 测试
│   └── requirements.txt
├── frontend/             # Vue 3 前端
│   ├── src/              # 源码（views、components、api、composables）
│   └── dist/             # 构建产物（已入库，供后端托管，普通使用无需 Node）
├── data/                 # 运行数据（已被 git 忽略，不会上传）
│   ├── app.db            # SQLite 主库
│   ├── files/            # 上传的资料
│   └── backup/           # 自动备份
├── docs/                 # 文档与参考资料
└── start.bat             # Windows 一键启动脚本
```

## 环境要求

- **Python 3.11+**（后端运行必需）
- **Windows**：开箱即用，双击 `start.bat` 即可
- **Node.js**：仅在参与前端开发时需要（普通使用可跳过，`frontend/dist` 已随仓库提供）

## 快速开始（普通使用）

### 1. 安装后端依赖（首次）

在 PowerShell 中进入项目根目录，创建虚拟环境并安装依赖：

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

### 2. 启动

双击 `start.bat`，服务启动后会自动打开浏览器，访问地址：

```
http://127.0.0.1:18731
```

### 3. 关闭

- 推荐：点击网页右上角的「关闭服务」按钮（退出前会再备份一次数据库）
- 或直接关闭启动时弹出的「日程安排-服务」命令行窗口

## 开发指南

开发时前后端分别启动：后端跑在 `18731`，前端 Vite 开发服务器跑在 `5173`，
通过代理把 `/tasks`、`/files`、`/shutdown` 转发到后端。

```powershell
# 终端 1：启动后端（在项目根目录）
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 18731 --app-dir backend

# 终端 2：启动前端（在 frontend 目录，首次需先 npm install）
cd frontend
npm install
npm run dev
```

开发期间访问 `http://localhost:5173`。

### 构建前端

修改前端后，构建产物会输出到 `frontend/dist`，供后端托管：

```powershell
cd frontend
npm run build
```

### 运行测试

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests -v
```

## 配置

应用配置位于 `backend/app/config.py`，可通过项目根目录下的 `.env` 文件或带 `APP_` 前缀的环境变量覆盖：

| 配置项 | 环境变量 | 默认值 | 说明 |
| --- | --- | --- | --- |
| 监听地址 | `APP_HOST` | `127.0.0.1` | 服务绑定地址 |
| 端口 | `APP_PORT` | `18731` | 服务端口（修改后需同步改 `start.bat` 与 `frontend/vite.config.js`） |
| 备份保留份数 | `APP_BACKUP_KEEP` | `7` | 自动备份保留的份数 |
| 回收站保留天数 | `APP_TRASH_RETAIN_DAYS` | `30` | 删除内容可恢复的天数 |
| 单文件上传上限 | `APP_MAX_UPLOAD_MB` | `100` | 单个上传文件大小上限（MB） |

示例 `.env`：

```env
APP_PORT=18731
APP_BACKUP_KEEP=14
```

## 数据与备份

- 所有运行数据都在 `data/` 目录下，已被 git 忽略，**不会上传到任何远程仓库**。
- 数据库为 `data/app.db`（SQLite），上传的资料在 `data/files/`，自动备份在 `data/backup/`。
- 每天首次启动自动备份一份，关闭服务时再备份一份，默认保留最近 7 份。
- 误删的任务 / 文件先进回收站，保留 30 天可恢复。
- 整体迁移或冷备份：复制整个 `data/` 文件夹即可。

## 许可证

本项目基于 [MIT License](LICENSE) 开源，可自由使用、修改与分发，请保留原始版权与许可声明。
