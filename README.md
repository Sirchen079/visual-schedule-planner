# 知时

把日程、任务和零散想法放在一起的桌面助手。

知时可以手动管理日历、待办和账本，也可以连接你自己的 AI 服务，用自然语言整理资料、安排计划、记录开支。数据保存在本机，AI 执行过程和需要确认的操作会显示在对话中。

**当前源码版本：2.14.2 · 桌面构建目标：Windows x64 · MIT 开源**

[AI 接入新手指南](docs/ai-api-guide.md) · [源码构建](#从源码运行) · [问题反馈](https://github.com/Sirchen079/visual-schedule-planner/issues)

## 能做什么

| 你想做的事 | 知时提供的功能 |
| --- | --- |
| 安排一天、一周或一个学期 | 日 / 周 / 月日历，重复日程，课程导入，冲突检查，提醒与 ICS 导出 |
| 管理待办和长期目标 | 任务、子任务、看板、时间轴、习惯打卡、目标与专注计时 |
| 记账和管理固定开支 | 收支记录、分类汇总、周期账单及到期提醒 |
| 收集资料、推进学习和研究 | 收件箱、资料库、学习与研究计划、进度跟进 |
| 用一句话处理事务 | AI 对话、工具调用、操作审批，以及可选的联网和 MCP 扩展 |
| 随手记录，不打断当前工作 | 桌面悬浮窗、托盘和通知；主窗口与悬浮窗各自保留会话与草稿 |

未配置 AI 时，仍可使用手动日程、任务和账本等功能。AI 对话需要自行配置模型服务，相关费用由服务方收取。

## 第一次使用

### 1. 获取应用

如果你已拿到 `zhishi-Setup-2.14.2.exe`，双击安装，再从桌面快捷方式打开“知时”。安装版自带运行环境，不需要另外安装 Python 或 Node.js。

**当前 [GitHub Releases](https://github.com/Sirchen079/visual-schedule-planner/releases) 中只有 1.x 安装包，尚未发布 2.14.2 安装包。** 要使用本页介绍的版本，请使用对应的 2.14.2 安装包，或按下方步骤从源码构建。GitHub 的 “Source code” 压缩包是源码，不能直接当作安装程序运行。

2.x 使用独立数据目录，**不兼容、不会自动导入或迁移 1.x 数据**。如仍在使用旧版，请保留原应用和原数据备份。

### 2. 先试一个简单操作

打开 **看板 → 新建任务**，填写标题、截止日期和优先级，点击“创建”。再试着勾选完成或删除这条任务。暂时不使用 AI，也可以先从这里开始。

### 3. 连接 AI（可选）

准备好服务商提供的 **API Key、Base URL 和模型名称**，然后：

1. 打开 **设置 → AI 模型 → 添加配置**。
2. 填写配置名称，按服务商文档选择接口格式。
3. 填入 Base URL 和 API Key，点击“获取模型列表”，选择模型；也可手动填写模型名称。
4. 点击“添加”，在配置列表中点击“启用”。看到“启用中”后，再回到对话区发送一句“你好”。

不熟悉这些名词，或遇到连接失败，请看 [AI 接入新手指南](docs/ai-api-guide.md)。初次接入时先保留其他设置的默认值，确认基本对话可用后，再配置图片输入、联网或外部工具。

### 4. 试试这些说法

- “明天下午三点提醒我交报告。”
- “午饭花了 28 元，帮我记到餐饮支出。”
- “看看这周还有哪些任务没完成。”
- “把这份课程表整理成日历，先让我确认日期和重复规则。”

执行前检查 AI 理解的日期、金额和内容；出现审批卡时，确认无误再批准。你也可以直接在对应页面手动修改。

## 常见问题

| 问题 | 说明 |
| --- | --- |
| AI 没有回复 | 检查配置是否“启用中”，再核对密钥、接口格式、基础地址、模型名称和网络。详见 [排错指南](docs/ai-api-guide.md#常见问题)。 |
| 为什么获取到模型列表，聊天仍失败？ | 获取列表只验证该接口可访问，不保证模型调用权限、额度和工具调用能力可用。 |
| 关闭主窗口后还会提醒吗？ | 主窗口关闭后通常收至托盘；从托盘彻底退出应用后，本机定时任务和提醒暂停。 |
| 能把日历放到手机上吗？ | 日历右上角可导出 ICS，再导入手机日历。导出是一次性文件，不会自动同步；提醒请在接收日历中确认。 |
| 重复日程可以只改一天吗？ | 当前编辑会修改整个重复系列，保存前请确认范围。 |
| 数据在哪里？ | Windows 安装版默认位于 `%APPDATA%\ZhishiV2`，业务数据在其中的 `data` 目录。自定义数据目录时以实际配置为准。 |
| 怎样备份？ | 从托盘彻底退出知时后，复制整个数据目录。模型密钥另存于系统凭据库，换电脑后需要重新填写。 |

## 数据与隐私

日程、任务、会话记录和附件主要保存在本机。连接外部 AI、联网检索或 MCP 服务后，完成请求所需的消息、附件或查询可能发送到所配置的服务；“本地保存”不代表 AI 调用离线运行。

模型密钥通过系统凭据库保存，应用不会在配置列表中回显密钥。长对话会生成摘要以控制上下文长度，摘要可能省略细节，原始记录可供回查。强制结束进程时，最近一次保存之后的少量输出可能丢失。

后端仅为本机桌面使用设计，默认监听回环地址并校验 Host / Origin；没有面向公网的账号认证，请勿直接开放到公网。更多边界说明见 [安全说明](SECURITY.md)。

## 从源码运行

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

安装包输出到 `electron-v2/dist/zhishi-Setup-2.14.2.exe`。构建产物、数据库和密钥不应提交到仓库。

## 开发与测试

| 目录 | 内容 |
| --- | --- |
| `backend-v2/` | Python、FastAPI、SQLAlchemy、PydanticAI 后端与测试 |
| `frontend-v2/app/` | Vue、TypeScript、Vite 前端与测试 |
| `electron-v2/` | Electron 窗口、托盘、通知与安装包配置 |
| `docs/` | 用户指南和开发说明 |

需要修改源码、运行测试或更新接口类型，请阅读 [开发指南](docs/development.md)。测试使用隔离数据和模型替身；个人课表原始附件不随仓库发布，对应测试在缺少样本时跳过。

欢迎提交 [Issue](https://github.com/Sirchen079/visual-schedule-planner/issues) 或 Pull Request。反馈问题时请附应用版本、复现步骤和去除敏感信息的报错。觉得知时有用，也欢迎给项目点一个 **Star**。

本项目使用 [MIT License](LICENSE)。
