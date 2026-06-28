# 可视化日程安排记录

可视化日程安排记录是一个本地优先的个人日程、任务和资料管理工具。项目以 FastAPI、SQLite 和 Vue 3 构建，提供看板、总览、日历、时间轴、资料库、提醒、回收站、自动备份和 AI 助手能力。生产模式下，后端在单一端口同时提供 API 与前端静态资源，适合在个人 Windows 环境中直接运行。

## 功能概览

### 任务与日程

- 看板任务：支持创建、编辑、拖拽变更状态、软删除与回收站恢复。
- 子任务：支持将任务拆分为可勾选的小步骤，并按完成率更新进度。
- 提醒：基于任务 `due_date` 提供即将到期和逾期提醒。
- 多视图：提供总览、日历和时间轴视图，用于查看截止日期、任务进度和并行安排。
- 标签：支持按标签组织任务，日历视图可按标签颜色显示任务。

### 资料库

- 本地资料库：支持上传文件、搜索、图片预览、PDF 预览、删除和恢复。
- 任务资料关联：任务详情中可以添加或移除相关资料。
- 链接资料：AI 可在用户确认后把联网搜索得到的网页、论文页面、课程或视频教程保存为链接资料。
- 视频资料：视频教程保存为 `video` 类型链接，点击资料或任务关联项会跳转到原始视频页面。

### AI 助手

- 悬浮式助手界面：支持展开对话、全屏使用、拖动悬浮窗、查看历史会话和开始新会话。
- 模型接入：支持 OpenAI Chat Completions、OpenAI Responses 和 Claude Messages 三种接口模式。
- 自定义接入：支持 API Key、自定义 Base URL、完整请求 URL、额外请求头和 HTTP Proxy。
- 模型列表：支持从当前配置一键获取模型列表，减少手动填写模型 ID。
- 人设与 Skill：助手人设和 Skill 分离，内置默认幕僚型人设，并支持导入自定义 Skill。
- 受控 Agent 模式：复杂请求会在后端最多连续工作 5 轮，模型可以查看状态、执行低风险工具、读取结果并继续规划。
- 多模态文件对话：支持将图片、PDF、Word、Excel、PPT 和常见文本文件作为本轮对话附件交给 AI 分析。
- 资料入库：对话中可上传文件到资料库，也可让 AI 将对话附件保存到资料库并关联任务。
- 原生联网搜索：支持使用模型服务商或兼容接口提供的原生联网搜索能力。
- 搜索增强：开启后，系统会提示模型优先使用原生联网能力检索相关资料，再结合本地任务状态进行规划。
- 安全确认：修改既有对象、删除、批量操作、清空回收站、导入联网资料等操作需要确认；高风险操作保留两次确认机制。

### 数据安全

- 本地数据：运行数据默认保存在 `data/` 目录中，并被 Git 忽略。
- 自动备份：启动时按天备份数据库，关闭服务时再执行一次备份，默认保留最近 7 份。
- 回收站：任务和文件删除后先进入回收站，默认保留 30 天。
- 密钥保护：AI API Key 只保存在本机后端数据库中，接口返回配置时会脱敏。
- 备份脱敏：备份数据库时会清理 AI 配置中的 API Key 和敏感请求头。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 后端 | Python 3.11+、FastAPI、SQLAlchemy 2、SQLite、Uvicorn、httpx |
| 前端 | Vue 3、Vite、vuedraggable |
| AI 接入 | OpenAI Chat Completions、OpenAI Responses、Claude Messages 兼容接口 |
| 测试 | pytest |

## 项目结构

```text
.
├── backend/
│   ├── app/              # FastAPI 应用代码
│   ├── tests/            # 后端测试
│   └── requirements.txt  # 后端依赖
├── frontend/
│   ├── src/              # Vue 前端源码
│   └── dist/             # 前端构建产物，供后端生产托管
├── data/                 # 本地运行数据，默认不提交
│   ├── app.db            # SQLite 主库
│   ├── files/            # 上传资料
│   ├── ai_attachments/   # AI 对话附件缓存
│   └── backup/           # 自动备份
├── docs/                 # 项目文档
└── start.bat             # Windows 启动脚本
```

## 环境要求

- Python 3.11 或更高版本。
- Windows 环境下可通过 `start.bat` 启动。
- Node.js 仅在前端开发或重新构建 `frontend/dist` 时需要。

## 快速开始

### 1. 安装后端依赖

首次使用时，在项目根目录执行：

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

### 2. 启动应用

双击 `start.bat`。服务启动后会打开浏览器，默认访问地址为：

```text
http://127.0.0.1:18731
```

### 3. 关闭服务

推荐在网页右上角点击“关闭服务”。该操作会在退出前执行一次数据库备份。也可以直接关闭启动时打开的服务窗口。

## 开发指南

### 后端开发

```powershell
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 18731 --app-dir backend
```

### 前端开发

```powershell
cd frontend
npm install
npm run dev
```

开发服务器默认运行在：

```text
http://localhost:5173
```

前端开发服务器会通过 Vite 代理访问后端 API。

### 构建前端

```powershell
cd frontend
npm run build
```

构建结果输出到 `frontend/dist`。生产模式下，FastAPI 会托管该目录。

### 运行测试

```powershell
python -m pytest backend\tests -q
```

如果 Windows 临时目录权限异常，可以指定独立的临时目录：

```powershell
python -m pytest backend\tests -q --basetemp .pytest-run
```

## 配置

应用配置位于 `backend/app/config.py`，可通过项目根目录下的 `.env` 文件或带 `APP_` 前缀的环境变量覆盖。

| 配置项 | 环境变量 | 默认值 | 说明 |
| --- | --- | --- | --- |
| 监听地址 | `APP_HOST` | `127.0.0.1` | 服务绑定地址 |
| 端口 | `APP_PORT` | `18731` | 服务端口 |
| 备份保留份数 | `APP_BACKUP_KEEP` | `7` | 自动备份保留数量 |
| 回收站保留天数 | `APP_TRASH_RETAIN_DAYS` | `30` | 删除内容可恢复天数 |
| 单文件上传上限 | `APP_MAX_UPLOAD_MB` | `100` | 资料库单文件上传上限 |
| AI 对话附件上限 | `APP_MAX_AI_ATTACHMENT_MB` | `50` | AI 对话附件单文件上限 |
| AI 图片识图上限 | `APP_MAX_AI_INLINE_IMAGE_MB` | `12` | 发送给多模态模型的单张图片上限 |
| AI 文档文本上限 | `APP_MAX_AI_TEXT_CHARS` | `120000` | 文档解析后传给模型的文本上限 |

示例：

```env
APP_PORT=18731
APP_BACKUP_KEEP=14
```

## AI 助手配置

在应用右下角打开“知时助手”，进入“设置”后新增或启用模型配置。

| Provider | 接口格式 | 默认路径 |
| --- | --- | --- |
| OpenAI Chat | Chat Completions | `/v1/chat/completions` |
| OpenAI Responses | Responses API | `/v1/responses` |
| Claude Messages | Messages API | `/v1/messages` |

URL 规则：

- 填写 Base URL 时，后端按 Provider 自动拼接默认路径。
- 填写 Full URL 时，后端直接请求该完整地址。
- 可以使用官方接口，也可以使用兼容上述格式的第三方或本地代理接口。
- 如需 HTTP 代理，可填写 `http://127.0.0.1:7890` 这类 Proxy URL。

联网搜索：

- 开启“模型原生联网搜索”后，后端会把联网参数随聊天请求发送给模型接口。
- 默认参数会按 Provider 生成：OpenAI Chat 使用 `web_search_options`，OpenAI Responses 使用 `web_search_preview` 工具，Claude Messages 使用 `web_search_20250305` 工具。
- 对于 Kimi Code 等兼容接口，可在“原生联网参数 JSON”中覆盖或补充请求体字段。
- 开启“搜索增强”后，系统提示会要求模型主动检索外部资料，并在回答中保留可核对来源。

Agent 工作模式：

- 一次聊天请求最多连续执行 5 轮。
- 每轮包含模型规划、低风险工具执行、工具结果观察和下一步规划。
- 已成功执行过的重复工具调用会被跳过，避免重复创建任务或资料。
- 如果本轮出现危险操作，系统不会执行同轮工具，而是停止并生成确认卡片。
- 图片和文档附件只在第一轮完整发送给模型，后续轮次仅保留附件引用信息，避免上下文膨胀。

文件入口：

- “看文件”：文件只作为本轮对话附件交给 AI 分析。图片按多模态输入发送，PDF、Word、Excel、PPT 和文本文件会在本机解析后发送文本。
- “入库”：文件保存到本地资料库，并交给 AI 判断是否需要关联任务或创建新任务。

联网资料入库：

- AI 搜索得到的外部网页、论文页面、课程或视频教程不会被后台自动下载。
- AI 会生成链接资料导入请求，用户确认后保存到资料库。
- 视频教程保存为 `video` 类型链接，点击后跳转到原始视频页面。

## 数据与备份

- 所有运行数据默认位于 `data/` 目录，该目录不应提交到远程仓库。
- SQLite 主库为 `data/app.db`。
- 资料库文件位于 `data/files/`。
- AI 对话附件缓存位于 `data/ai_attachments/`。
- 自动备份位于 `data/backup/`。
- 迁移或冷备份时，可以复制整个 `data/` 目录。

## 安全边界

- AI 只能调用后端白名单工具。
- 创建任务、创建提醒、查看资料、保存附件等低风险操作可直接执行。
- 修改已有任务、删除、批量操作、清空回收站、导入联网资料等操作需要确认。
- 危险操作不会由模型直接执行，必须通过确认卡片完成。
- 自定义 Skill 仅作为文本规则注入，不作为代码执行，也不能覆盖系统安全规则。

## 许可证

本项目基于 [MIT License](LICENSE) 发布。
