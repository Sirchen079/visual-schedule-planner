# 知时

知时是一个本地优先的个人日程、任务与资料管理**桌面应用**。项目以 Electron 封装 FastAPI + SQLite + Vue 3，提供看板、总览、日历、时间轴、资料库、AI 助手，以及开机自启、DDL 提醒小窗、自动备份等能力。所有数据保存在本机，无需联网即可使用（AI 功能需自行配置接口）。

> 📥 **[点击此处下载最新版「知时 Setup.exe」（Windows）](https://github.com/Sirchen079/visual-schedule-planner/releases/latest/download/Setup.exe)**　·　[查看所有版本](https://github.com/Sirchen079/visual-schedule-planner/releases)

## 功能概览

### 任务与日程

- 看板任务：创建、编辑、拖拽变更状态、软删除与回收站恢复。
- 子任务：拆分为可勾选的小步骤，按完成率更新进度。
- 提醒：基于任务截止时间提供「即将到期」和「已逾期」提醒。
- 多视图：总览、日历、时间轴，查看截止日期、进度与并行安排。
- 标签：按标签组织任务，日历视图按标签颜色显示。

### 资料库

- 本地资料库：上传文件、搜索、图片预览、PDF 预览、删除与恢复。
- 任务资料关联：任务详情中添加或移除相关资料。
- 链接资料：AI 在确认后可把联网搜索得到的网页、论文、课程或视频保存为链接资料。
- 视频资料：保存为 `video` 类型链接，点击跳转原始页面。

### 桌面应用

- 常驻托盘：关闭主窗口即最小化到系统托盘，后台保持运行。
- 开机自启：可在「设置」中开启，开机后自动启动。
- DDL 提醒小窗：开机自启时主窗口静默到托盘，仅在屏幕右下角弹出独立的截止提醒小窗；手动启动则在主窗口内弹出当日提醒。
- 单实例：重复启动会聚焦已有窗口。

### AI 助手

- 悬浮式助手：展开对话、全屏使用、拖动、查看历史会话与新建会话。
- 模型接入：支持 OpenAI Chat Completions、OpenAI Responses、Claude Messages 三种接口。
- 自定义接入：API Key、自定义 Base URL、完整请求 URL、额外请求头、HTTP Proxy。
- 模型列表：从当前配置一键获取模型列表。
- 人设与 Skill：助手人设与 Skill 分离，内置默认人设，支持导入自定义 Skill。
- 受控 Agent：复杂请求后端最多连续 5 轮，可查看状态、执行低风险工具、读取结果并继续规划。
- 多模态：图片、PDF、Word、Excel、PPT、文本文件可作为对话附件分析。
- 联网搜索：支持模型原生联网搜索与搜索增强。

### 数据安全

- 本地存储：所有数据保存在软件安装目录下的 `data\`（便携式，跟随软件，不占 C 盘 AppData），卸载程序不会删除。
- 自动备份：启动时按天备份，退出时再备份一次，默认保留最近 7 份。
- 回收站：任务和文件删除后进入回收站，默认保留 30 天。
- 密钥保护：AI API Key 只保存在本机后端，接口返回时脱敏；备份时清理密钥与敏感请求头。

---

## 用户指南

### 安装

从 [GitHub 发布页](https://github.com/Sirchen079/visual-schedule-planner/releases/latest) 获取安装包，或 [点击此处直接下载 `知时 Setup.exe`](https://github.com/Sirchen079/visual-schedule-planner/releases/latest/download/Setup.exe)。双击运行，按向导选择目录完成安装。安装程序在复制文件前会自动关闭正在运行的旧版知时（先优雅退出并备份，再覆盖），无需手动结束进程。

### 启动与退出

- 启动：从开始菜单或桌面快捷方式打开「知时」。
- 最小化到托盘：点击主窗口的关闭按钮，窗口隐藏到系统托盘，应用继续运行。
- 完全退出：右键托盘图标 →「退出」；此时会执行一次数据库备份再退出。主窗口内的「关闭服务」按钮等效于退出整个应用。

### 开机自启与 DDL 提醒

- 打开主窗口右上角「设置」，开启「开机自启动」。
- 开启后，每次开机知时会自动启动：**主窗口静默到托盘**，仅在屏幕右下角弹出独立的 DDL 提醒小窗，列出今日事项与按紧迫度分档的截止提醒（已逾期 / 今天截止 / 还剩 N 天 / 还有 N 天）。
- 小窗中「去处理」会唤出主窗口并定位到最紧迫的任务；「知道了」关闭小窗，主窗口留在托盘。
- 若当日没有任何截止或安排，小窗不出现，完全不打扰。
- 手动启动（非开机自启）时，则在主窗口内弹出当日提醒。

### 数据位置与备份

数据目录：软件安装目录下的 `data\`（如 `D:\知时\data\`，便携式跟随软件）

- `app.db`：SQLite 主库
- `files/`：资料库文件
- `ai_attachments/`：AI 对话附件缓存
- `backup/`：自动备份

> 从旧版升级后，安装目录下还会出现 `migration-backup\` 文件夹，存放迁移前（即更新前）的完整数据快照，仅保留最近一次，便于回退/恢复；确认无误后可手动删除。

冷备份或迁移：复制安装目录下的整个 `data\` 文件夹到新机器的知时安装目录下即可（数据库内文件路径为相对路径，整目录搬迁无需改写）。

### 升级与卸载

- 升级：直接运行新版 `知时 Setup.exe`，安装程序自动关闭旧版（含备份）并覆盖。用户数据存放在安装目录下的 `data\`，升级覆盖不会触碰该目录，数据天然保留。
- 旧版数据迁移：从 v1.2.1 之前的版本升级时，新版首次启动会自动把历史数据从 `%APPDATA%\知时\data\` 迁移到安装目录下的 `data\`，并把更新前的数据备份到安装目录下的 `migration-backup\`（仅保留最近一次），随后清除 C 盘旧位置以释放空间。
- 卸载：从「设置 → 应用」卸载，仅删除程序文件，**用户数据保留**（位于安装目录的 `data\`）；如需彻底清除，手动删除安装目录下的 `data\` 文件夹。

---

## 开发者指南

### 环境要求

- Python 3.11+
- Node.js 18+
- Inno Setup 6（编译安装包）
- Windows（当前仅打包 Windows 桌面应用）

### 项目结构

```text
.
├── backend/        # FastAPI 应用（SQLAlchemy + SQLite）
├── frontend/       # Vue 3 + Vite 前端
├── desktop/        # Electron 主进程 + 打包脚本 + Inno Setup 安装器
├── data/           # 开发模式运行数据（gitignore；安装版数据在安装目录 data/）
└── docs/           # 项目文档
```

### 后端开发

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 18731 --app-dir backend
```

### 前端开发

```powershell
cd frontend
npm install
npm run dev
```

开发服务器默认在 `http://localhost:5173`，经 Vite 代理访问后端 API。

### 桌面应用调试

先构建一次后端产物（供 Electron 拉起），再启动壳：

```powershell
cd desktop
npm install
npm start
```

可用 `npm start -- --autostart` 触发开机自启分支（静默到托盘 + DDL 小窗），便于测试。

### 构建与打包

完整流程见 [`desktop/README.md`](desktop/README.md)：构建前端 → PyInstaller 打包后端 → electron-builder 生成 win-unpacked → Inno Setup 生成安装包。

### 测试

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
```

### 配置

应用配置位于 `backend/app/config.py`，可通过项目根目录的 `.env` 文件或带 `APP_` 前缀的环境变量覆盖（桌面应用通常无需修改）。

| 配置项 | 环境变量 | 默认值 | 说明 |
| --- | --- | --- | --- |
| 监听地址 | `APP_HOST` | `127.0.0.1` | 服务绑定地址 |
| 端口 | `APP_PORT` | `18731` | 服务端口（被占用时自动顺延） |
| 备份保留份数 | `APP_BACKUP_KEEP` | `7` | 自动备份保留数量 |
| 回收站保留天数 | `APP_TRASH_RETAIN_DAYS` | `30` | 删除内容可恢复天数 |
| 单文件上传上限 | `APP_MAX_UPLOAD_MB` | `100` | 资料库单文件上限 |
| AI 对话附件上限 | `APP_MAX_AI_ATTACHMENT_MB` | `50` | AI 对话附件单文件上限 |
| AI 图片识图上限 | `APP_MAX_AI_INLINE_IMAGE_MB` | `12` | 多模态单张图片上限 |
| AI 文档文本上限 | `APP_MAX_AI_TEXT_CHARS` | `120000` | 文档解析后传给模型的文本上限 |

## AI 助手配置

在主界面右下角打开「知时助手」，进入「设置」新增或启用模型配置。

| Provider | 接口格式 | 默认路径 |
| --- | --- | --- |
| OpenAI Chat | Chat Completions | `/v1/chat/completions` |
| OpenAI Responses | Responses API | `/v1/responses` |
| Claude Messages | Messages API | `/v1/messages` |

URL 规则：

- 填 Base URL 时，后端按 Provider 自动拼接默认路径。
- 填 Full URL 时，后端直接请求该完整地址。
- 可使用官方接口，或兼容上述格式的第三方 / 本地代理。
- 如需 HTTP 代理，填写 `http://127.0.0.1:7890` 这类 Proxy URL。

联网搜索：

- 开启「模型原生联网搜索」后，后端把联网参数随请求发送。OpenAI Chat 用 `web_search_options`，OpenAI Responses 用 `web_search_preview`，Claude Messages 用 `web_search_20250305`。
- 兼容接口可在「原生联网参数 JSON」中覆盖。
- 开启「搜索增强」后，系统提示会要求模型主动检索外部资料并保留可核对来源。

Agent 工作模式：

- 一次请求最多连续 5 轮（规划 → 低风险工具执行 → 结果观察 → 下一步）。
- 已成功的重复工具调用会被跳过。
- 危险操作不执行，改为生成确认卡片。

## 安全边界

- AI 只能调用后端白名单工具。
- 创建任务、提醒、查看资料、保存附件等低风险操作可直接执行。
- 修改已有对象、删除、批量操作、清空回收站、导入联网资料等需确认。
- 危险操作必须经确认卡片完成，模型不会直接执行。
- 自定义 Skill 仅作为文本规则注入，不作为代码执行，不能覆盖安全规则。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 桌面壳 | Electron 31 |
| 后端 | Python 3.11+、FastAPI、SQLAlchemy 2、SQLite、Uvicorn、httpx |
| 前端 | Vue 3、Vite、vuedraggable |
| 打包 | PyInstaller（后端）、electron-builder + Inno Setup（安装包） |
| 测试 | pytest |

## 许可证

本项目基于 [MIT License](LICENSE) 发布。
