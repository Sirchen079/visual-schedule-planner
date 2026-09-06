# 知时

本地优先的日程管理与 AI 私人秘书。当前版本 **2.14.2**。

支持日历与课程安排、任务和提醒、个人账本与周期账单、资料库与学习研究计划，以及通过原生工具调用执行事务的 AI 对话。主窗口与悬浮窗可恢复各自会话和草稿。

喜欢知时，欢迎点一个 **Star**；问题与建议请提交 [Issue](https://github.com/Sirchen079/visual-schedule-planner/issues)。

## 当前版本

- 应用、窗口与快捷方式名称统一为“知时”；安装包为 `zhishi-Setup-2.14.2.exe`。
- 主界面常驻 GitHub · Star 链接，设置页提供项目支持入口。
- 日历日/周/月视图可点击编辑行程；重复行程修改整个系列。
- 日历右上角可手动导出 ICS 文件，支持全天、仅开始时间、重复规则、地点和备注。文件不是自动同步；手机提醒需在接收日历中设置。
- 接受的聊天输入、流检查点、工具结果及压缩前历史分别持久保存，审批与草稿可在重启后恢复。

**本版不兼容老知时（1.x）的数据格式，不扫描、不导入、不自动迁移老版数据库。** 2.x 使用独立数据目录。仓库原有 `backend/`、`frontend/`、`desktop/` 保留为旧实现参考，当前入口和构建只使用下面的新代码目录。旧版说明保存在 `docs/legacy/`。

## 源码布局

| 目录 | 用途 |
| --- | --- |
| `backend-v2/` | Python / FastAPI / SQLAlchemy / PydanticAI 后端与测试 |
| `frontend-v2/app/` | Vue / TypeScript / Vite 前端与测试 |
| `electron-v2/` | Electron 窗口、托盘、通知与 Windows 安装包 |

目录后缀仅用于区分仓库内旧实现，产品显示名称为“知时”。

## Windows 本地构建

需要 Python 3.12+、Node.js 和 npm。以下命令从仓库根目录执行。依赖锁记录了本次验收环境中的 Python 包版本。

```powershell
python -m venv backend-v2/.venv
backend-v2/.venv/Scripts/python.exe -m pip install -r backend-v2/requirements-lock.txt
backend-v2/.venv/Scripts/python.exe -m pip install -e "./backend-v2[dev]"
npm --prefix frontend-v2/app ci
npm --prefix frontend-v2/app run build
backend-v2/.venv/Scripts/python.exe backend-v2/scripts/build.py
npm --prefix electron-v2 ci
npm --prefix electron-v2 start
```

生成安装包：`npm --prefix electron-v2 run dist`，产物在 `electron-v2/dist/`。完成构建后也可双击根目录 `start.bat`。

后端独立开发：进入 `backend-v2/`，运行 `.venv/Scripts/python.exe -m zhishi.server.app --port 8421`；前端运行 `npm --prefix frontend-v2/app run dev`。

## 测试

```powershell
cd backend-v2
.venv/Scripts/python.exe -m pytest
cd ..
npm --prefix frontend-v2/app test
npm --prefix electron-v2 test
```

真实个人课表样本不发布，依赖这些样本的测试会跳过；测试代码中的其他样本由程序合成。`backend-v2/scripts/verify_*.py` 提供冻结程序的隔离验收，一些历史脚本需要手动指定对应旧版安装产物。

## 数据与隐私

- 运行记录保存在本机独立数据库。仓库不包含数据库、真实附件、日志、备份、API 密钥或安装包。
- 模型密钥由系统凭据库保存；请在应用设置中自行配置，勿提交到 Git。
- 使用外部 AI、联网检索或 MCP 时，相关消息、附件或查询会发送给所配置的服务；“本地保存”不表示这些调用离线运行。
- 默认后端仅监听本机回环地址，校验 Host 和 Origin；当前没有面向公网的账号认证，不应直接作为公网服务发布。
- 软件退出后，本机定时任务暂停。长对话摘要可能遗漏细节，可回查原文；硬终止可能丢失最近一次检查点之后的极短输出。

详细功能与验证记录见 `backend-v2/docs/`。软件许可证沿用仓库现有 [MIT License](LICENSE)。
