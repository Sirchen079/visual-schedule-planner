# v2.14.1 日历导出入口

用户反馈“导出日历的按钮看不到”。排查确认后端已有 `/api/ical/export`，前端未提供入口。

## 使用

安装 `release/desktop-2.14.1/zhishi-v2-Setup-2.14.1.exe` 后，打开左侧日历，点击右上角 **导出日历**。下载文件名为 `知时日程-YYYY-MM-DD.ics`。将文件传到手机，在支持 ICS 导入的日历应用中打开。

按钮在日/周/月视图共用的工具栏中。它导出全部已保存的独立日程，不受当前显示日期范围限制；不包括任务排期、账单或聊天记录。导出过程中禁止重复点击；请求失败显示错误及重试按钮。界面只提示发起下载，用户仍可在系统保存对话框中取消。

这是手动文件导出，后续修改需重新导出；重复导入的合并方式由接收日历应用决定，不保证去重或自动删除旧日程。原有知时提醒设置暂不写入 ICS，手机提醒应在接收的日历应用中设置。

## 文件修复

- 增加稳定 UID 和 UTC DTSTAMP，编辑同一记录后再次导出保持 UID。
- 全天行程使用 DATE 类型与次日排他结束日期，避免被识别为零点的定时事件。
- 只有开始时间的行程保留真实开始时间，不再降成零点。
- 保留重复 RRULE、地点和中文多行备注。日程时间采用与现有本地数据一致的 floating local time，不增加尚不存在的时区选择。
- 导出响应增加下载文件名及 `Cache-Control: no-store`。

## 验证

- `tests/domain/test_ical.py`、`tests/server/test_routes_smoke.py`、`tests/server/test_typed_responses.py`：19 passed；1 条既有 Starlette/AnyIO 弃用警告。
- TypeScript 与 Vite 构建通过。
- 冻结后端启动、`/health` 和正常关闭通过。
- `scripts/verify_calendar_export.py` + `.cjs` 在隔离临时数据中打开实际 Electron 界面、点击按钮、阻断请求再重试，收到 `will-download` 完成事件并保存文件；解析实际下载内容验证中文备注、RRULE、UID、全天 DATE 和仅开始时间。
- 1450px/900px 截图检查，900px 下按钮可见。报告 `release/desktop-2.14.1/qa/export.json`、`export-ui.json`，下载样本 `downloaded-calendar.ics`，截图 `export-wide.png`、`export-narrow.png`。
- 测试进程已退出，未使用正式用户数据库或模型凭据。未在真实手机日历中执行导入，也未运行 NSIS 安装向导；安装包与验收资源的逐文件一致性及 SHA256 见 `verification.json`。

v2.14.0 的会话完整性与日历编辑改动继续保留，详情见 [SESSIONS_AND_CALENDAR_2_14_0.md](SESSIONS_AND_CALENDAR_2_14_0.md)。本轮仅处理日历导出，不开展新的自主迭代。
