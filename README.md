# 可视化日程安排记录

把一团乱麻的事情理顺，缓解焦虑和灾难性思维。

一个本地单机的可视化日程管理工具：看板、总览、日历、时间轴、资料库一体，
配合 AI 助手、标签、子任务、提醒、自动备份与回收站，专注于「数据不丢、随时可控」。

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

**知时助手**
- 悬浮式 AI 助手：点击展开对话，也可全屏使用
- 模型接入：支持 OpenAI Chat Completions、OpenAI Responses、Claude Messages 三种接口模式
- 自定义服务：支持 API Key、自定义 Base URL、完整请求 URL、额外请求头与 HTTP Proxy
- 模型列表：可从当前配置一键获取模型列表，减少手动填写模型 ID
- 对话式管理：通过自然语言查看、创建、规划任务，整理资料，生成提醒与时间安排
- 多模态对话：可把图片、PDF、Word、Excel、PPT 和文本文件作为本轮对话附件交给 AI 分析
- 对话上传资料：可在助手对话框直接上传文件到资料库，上传后交给助手整理和关联任务
- 当前状态：对话时会提供当前日期、时间、星期、时区、任务统计、逾期与近期提醒
- 人设与 Skill：内置幕僚型默认人设，可单独配置助手人设，也可导入自定义 Skill 规则
- 安全确认：删除、批量修改、清空回收站等危险操作必须经过两次确认后才会执行

**数据安全**
- 自动备份：每天备份数据库，关闭服务时再备一份，默认保留最近 7 份
- 回收站：任务与文件删除后保留 30 天可恢复，支持彻底清除与一键撤销
- AI 密钥：只保存在本机后端数据库中，接口返回配置时会自动脱敏
- 明 / 暗主题切换

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.11+、FastAPI、SQLAlchemy 2、SQLite、Uvicorn、httpx |
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
通过代理把 `/tasks`、`/files`、`/reminders`、`/ai`、`/shutdown` 转发到后端。

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
| AI 对话附件上限 | `APP_MAX_AI_ATTACHMENT_MB` | `50` | 上传给 AI 看的单个附件大小上限（MB） |
| AI 图片识图上限 | `APP_MAX_AI_INLINE_IMAGE_MB` | `12` | 发送给模型识图的单张图片上限（MB） |
| AI 文档文本上限 | `APP_MAX_AI_TEXT_CHARS` | `120000` | PDF / Office / 文本解析后传给模型的字符上限 |

示例 `.env`：

```env
APP_PORT=18731
APP_BACKUP_KEEP=14
```

## AI 助手配置

进入应用后点击右下角「知时助手」，在「设置」中新增或启用模型配置。

支持的 Provider：

| Provider | 接口格式 | 默认路径 |
| --- | --- | --- |
| OpenAI Chat | Chat Completions | `/v1/chat/completions` |
| OpenAI Responses | Responses API | `/v1/responses` |
| Claude Messages | Messages API | `/v1/messages` |

URL 填写规则：

- 填写 **Base URL**：后端按 Provider 自动拼接默认路径。
- 填写 **Full URL**：后端直接请求该完整地址。
- 可使用官方接口，也可使用兼容上述格式的第三方或本地代理接口。
- 如需代理访问，可填写 **HTTP Proxy**，例如 `http://127.0.0.1:7890`。

AI 能直接执行创建任务、创建提醒、保存资料笔记等低风险操作。修改已有任务、删除、批量操作、清空回收站等高风险操作会生成确认卡片，必须两次点击确认后才执行。

对话框有两个文件入口：

- **看文件**：文件只作为本轮对话附件交给 AI 分析。图片会按多模态图片传给模型；PDF、Word、Excel、PPT 和常见文本文件会在本机解析为文本后传给模型。
- **入库**：文件保存到本地资料库，并交给 AI 判断是否需要关联已有任务或创建新任务。

AI 可以在分析对话附件后调用工具，把附件保存到资料库并关联任务。文件解析在本机完成，不依赖第三方文件解析服务。

自定义 Skill 支持导入 `.md` / `.txt` 文本，用于补充工作规则、任务拆解方式、资料整理习惯等。Skill 不会作为代码执行，也不能绕过系统安全规则。

## 数据与备份

- 所有运行数据都在 `data/` 目录下，已被 git 忽略，**不会上传到任何远程仓库**。
- 数据库为 `data/app.db`（SQLite），上传的资料在 `data/files/`，自动备份在 `data/backup/`。
- 每天首次启动自动备份一份，关闭服务时再备份一份，默认保留最近 7 份。
- 误删的任务 / 文件先进回收站，保留 30 天可恢复。
- 整体迁移或冷备份：复制整个 `data/` 文件夹即可。

## 许可证

本项目基于 [MIT License](LICENSE) 开源，可自由使用、修改与分发，请保留原始版权与许可声明。
