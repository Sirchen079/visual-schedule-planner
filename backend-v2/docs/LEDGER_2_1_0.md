# 知时 v2.1.0：个人账本

日期：2026-09-05。总体私人秘书目标继续进行，本批将收支记账从缺失功能接成真实可用的后端、对话与界面。

## 最终交付

- 安装包：`E:\知时\backend-v2\release\desktop-2.1.0\zhishi-v2-Setup-2.1.0.exe`，137271251 字节。
- SHA256：`508197e7f2158ff2eb8a1bc9ef32a2c6ffbfe567cdd3f575320ca6a7e01f5446`。
- Electron 网络下载超时后使用本机相同33.4.11发行文件完成构建。最终壳10个运行文件/图标、前端全部资源、冻结后端二进制与验证产物逐字节/哈希一致。
- 最终桌面自检：`release/widget-check-20260905-230415/stdout.log`，真实SPA挂载、窗口可见、悬浮窗记事/完成、置顶/收起/隐藏、托盘隐藏与退出PID清理全部通过。
- 本批没有覆盖用户现有安装，也没有重复验证 NSIS 安装/卸载；验证对象为最终包的 win-unpacked 程序。桌面显示版本2.1.0，兼容后端协议 `/health` 版本仍为2.0.0。

## 使用

- 左侧新增「账本」；可手动记收入/支出，按月份、币种、账户过滤，搜索分类/商户/备注，查看净收支和分类汇总。
- 对话可表达实际收支，例如“今天午饭花了 28.50 元”。模型使用 `record_transaction` 保存，用 `summarize_transactions` 查账。
- 收据仍从主对话附件上传，模型读文本或图像后可填写来源附件与摘录。金额不清或支付状态不明确时应澄清；预算和报价不作为实际支出。
- 修改、删除、恢复都使用最近读取的版本号。删除移入独立账本回收站，界面提供撤销；过期版本返回 409。
- 收支数据保存在 v2 SQLite；使用外部 AI 时，相关消息/附件/工具结果可能发给配置的模型服务。界面已纠正旧的“数据不出设备”绝对承诺。

## 数据与接口

- `ledger_entries` 在启动时由 create_all 幂等创建；存量 v2 数据库无需清空。原任务保留的升级测试通过。
- 金额为正数，收支方向单独存储；CNY/USD/EUR/GBP/HKD 使用整数分，JPY 使用整数元。响应金额为定点字符串，浮点数不参与加总；不支持的币种和过多小数明确报错，不偷偷舍入。
- 字段：日期、方向、币种、金额、分类、账户标签、商户/对方、备注、来源附件 id/原文摘录、版本与回收时间。账户是记账标签，不是银行连接或真实余额。
- `idempotency_key` 全局唯一；同键同原始内容重试返回原记录的当前状态，不覆盖修正、不复活删除。不同内容返回冲突；数据库唯一约束处理并发。同一附件同一条目应复用 key。
- 删除来源文件后外键置空，账目和原文摘录保留。
- `GET/POST /api/ledger`；`GET/PUT/DELETE /api/ledger/{id}`；`POST /api/ledger/{id}/restore`；`GET /api/ledger/summary?start=&end=`。列表分页 50，最大 200；摘要覆盖完整筛选范围，不受列表分页限制。
- 7 个工具共用原权限门：record 为 safe，list/get/summarize 为 readonly，update/delete/restore 为 confirm；谨慎档所有写入确认。
- REST 契约已导出，SSE 19 事件契约没有变化。前端类型生成需 `openapi-typescript --default-non-nullable false`，保留后端默认字段的可选语义。

## 验证

- 后端最终全量：344 passed / 1 skipped / 1 warning；跳过为既有项，警告为 Starlette/AnyIO 弃用提示。
- 前端：243 tests / 19 files；类型检查与最终生产构建通过。
- 新增后端 17 项：精确小数、超精度/非有限金额拒绝、日元整数、分币种/账户汇总、字面搜索、分页、版本冲突、删除恢复、来源文件清除、并发去重、存量库加表、重启和对话链路。
- 附件 E2E：真实上传和解析文本收据，FunctionModel 替身校验附件正文进入模型输入、调用真实记账工具，重复执行同键仍只有一笔，来源摘录可追溯。模型替身不冒称真实供应商 OCR 成功率。
- 实际浏览器隔离库：28.50 新增 → 29.00 修改 → 删除汇总归零 → 撤销恢复29.00；USD/月筛选隔离；刷新仍保留；深色与浅色截图检查。
- PyInstaller 构建及 health/shutdown 冒烟通过。`scripts/verify_ledger.py` 对冻结程序实测精确0.10+0.20、幂等、修改、恢复及两次独立进程重启，人民币29.30/USD5.00分别保留。
- 冻结验证资料根：`C:\Users\USER\AppData\Local\Temp\zhishi-ledger-frozen-vm2ebkkg`，first.log/restart.log。最终桌面包验证见下续记。

## 未完成的总体范围

跨文件重复上传内容识别、批量账单/收据候选审核、预算与转账、学习研究项目和自主资料库规划仍待实现。当前幂等依据调用方稳定 key，尚不自动判定新上传图片是否与旧收据是同一笔消费。未调用真实模型或更改用户现有安装/数据；新桌面安装包不能替代生产数据升级及真实模型场景验收。

## 源码

后端：`domain/ledger`、`models.LedgerEntry`、`routes/ledger.py`、`tools/ledger_tools.py` 与内置账本技能。
前端 `E:\知时\frontend-v2\app`：`views/LedgerView.vue`、`api/ledger.ts`/tests、REST 类型、导航/图标和 App 的外部 AI 说明。
桌面 `E:\知时\electron-v2`：版本2.1.0；保留2.0.1图标和悬浮窗。
