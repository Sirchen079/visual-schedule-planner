# 知时 v2 前端交接手册

> 面向：负责前端规划与开发的 AI / 工程师。后端已完成（v2.0.0-backend，201 tests）。
> 本文档 + `docs/contracts/` 下三份机器可读契约 = 前端开发的全部依据。

## 1. 契约物料（全部自动生成，勿手改）

| 文件 | 内容 | 权威来源 |
|---|---|---|
| `openapi.json` | 全部 REST 端点（请求/响应 schema） | FastAPI 自动导出，运行时 `/docs` 有可交互版 |
| `events.d.ts` | 19 个 SSE 事件的 TypeScript 类型（判别联合 `SSEEvent`） | `src/zhishi/agent/events.py` |
| `events.schema.json` | 同上的 JSON Schema（非 TS 技术栈用） | 同上 |

契约变更流程：后端改 `events.py` → 跑 `python scripts/export_contracts.py` → 快照对比。前端可把「events.d.ts 不变」当作兼容性哨兵。

## 2. 运行环境

- 开发启动：`cd backend-v2 && .venv/Scripts/python -m zhishi.server.app --port 8421`
- 前端静态托管：已内置。把构建产物放到 `ZHISHI_FRONTEND_DIR` 指向的目录（或仓库 `frontend/dist/`），后端自动挂在 `/`（SPA html 模式）。`/api/*`、`/ai/*`、`/health` 优先于静态路由。**注意：静态目录只在后端启动时探测一次——产物生成晚于启动的话 `GET /` 会 404，重启后端即恢复；开发期建议走 Vite 代理。**
- 无 token 鉴权，但有双重本地防护：请求 Host 钉死回环白名单（127.0.0.1/localhost/::1，根治 DNS rebinding）+ 跨站 Origin 拦截 403。同源（含 Vite 代理）与无 Origin（Electron/curl）放行；环境变量 ZHISHI_TRUSTED_HOSTS 可扩展白名单（测试用）。
- 数据根：`ZHISHI_DATA_DIR`（默认 `data/`）→ 实际库 `data/v2/backend.db`（SQLite WAL）。

## 3. REST 面（速览，全量见 openapi.json）

七域 CRUD 全部在前缀 `/api/` 下：`tasks`（含子任务——清单随 `GET /api/tasks` 与 `GET /api/tasks/{id}` 的 `subtasks` 字段带出（re #B4）/回收站/标签）、`schedule`（entries 列表 `GET /api/schedule/entries?task_id=&date_from=&date_to=`（默认近 30 天，re #B5）/events/`day`/`month`/`range`/`conflicts`/`free-slots`）、`goals`（含 key-results/progress/回收站）、`habits`（check-in/uncheck，uncheck 的 date 可省略=今天）、`journal`、`focus`（start/stop/stats）、`files`（含 links/attach/trash）、`notifications`、`stats`（summary/daily/by-tag/by-priority/risk）、`settings`、`ical`（export/import）。

**goals 回收站语义（re #B2）**：`DELETE /api/goals/{id}` 是软删除（进回收站）；`GET /api/goals/trash` 列已删项、`POST /api/goals/{id}/restore` 恢复、`DELETE /api/goals/{id}/purge` 硬删（级联 key_results，仅回收站中的可 purge，未软删返回 409）。列表参数为 `include_deleted`（旧名 `include_archived` 兼容保留但已标 deprecated，语义同为「含已删」）；已删项 `status` 保持原值，以 `deleted_at` 非空辨识，勿按 status 判断删除态。

**files 上传（re #B6）**：`POST /api/files` 的 `notes` 是 multipart 表单域（与 `file` 同在 form-data），不是 query 参数——query 传法不再支持。

**日程视图选型（端点语义勿混用，re #017）**：
- **周/多日视图用 `GET /api/schedule/events/expand`**：RRULE 展开后的日程出现列表（单双周规则已展开），返回 `[{event_id, title, date, start_time?, end_time?, location, category}]`，按 date+start_time 排序。
- `GET /api/schedule/day`：统一日视图 `{date, items:[{kind:"event"|"task", …}]}`——独立日程与任务排期合并，日视图直接用它。
- **`GET /api/schedule/range` 是任务负载视图（不含独立日程）**：`{"日期": {items:[{task_id,title,start_time?,end_time?,estimated_minutes}], estimated_minutes}}`，供负载热力/排程界面使用，别拿它画周日历。
- **不存在 `GET /api/events`**：日程读取走 `events/expand`（展开视图）或 `/api/schedule/events/{id}`（单条）；创建/修改用 `POST/PATCH/DELETE /api/schedule/events…`。
- `GET /api/schedule/conflicts` → `[{date, items:[两条冲突项]}]`；`GET /api/schedule/free-slots` → `[{start, end, minutes}]`。

AI 管理面在 `/ai/` 下：`configs`（CRUD+enable，key 走系统凭据库）、`conversations`（CRUD）、`skills`（CRUD+enable）、`mcp/servers`（CRUD+test+tools）、`grants`（「始终允许」规则的查询与撤销，见 §4）、`reports`（daily/weekly/briefing）、`attachments`（上传即解析）。

## 4. SSE 对话协议（核心交互）

**发消息**：`POST /ai/chat/stream`，body `{"message": string, "conversation_id"?: number, "attachment_ids"?: number[]}`。
响应 `text/event-stream`，每帧 `event: <type>\ndata: <json>\n\n`，json 含 `v:1`。

**消费要点**：
- 首帧恒为 `run_started`（拿 run_id/conversation_id），末帧恒为 `done`（权威收敛）。`run_completed`/`run_error` 在 done 前面给出终态与用量。
- **活性保证**：`stage_changed` 标注阶段（preparing/connecting/waiting_first_token/streaming_reasoning/streaming_text/executing_tools/awaiting_approval/finalizing）；模型超过 5s 无输出时每 5s 一帧 `heartbeat`。UI 任何时刻可显示"AI 在干什么"。
- **思维链** `reasoning_delta`（可折叠展示）、**正文** `text_delta`（追加渲染）、**工具** `tool_call_started/args_delta/result`（可展开的工具卡片）、**用量** `usage_updated`（累计 tokens_in/out/成本）。
- **工具名是裸名**：事件帧的 `tool` 字段形如 `create_event`、`delete_task`，**不带** `schedule.create_event` 这类命名空间前缀（内置工具注册即裸名，卡片直接展示）；唯一带前缀的是 MCP 工具 `mcp__{server_id}__{原名}`（见 §6）。
- **审批门**：`tool_approval_requested` 到达 → 流以 `run_completed{done_reason:"awaiting_approval"}` 结束。UI 渲染确认卡片（含 args 与 preview）。**args 字段名是工具层命名**：日程/打卡/日记类参数用 `day`（如 `create_event` 的 `{"title", "day"}`），与 REST 端点的 `date` 字段不同——工具层沿用领域层 day 命名，前端透传展示、勿与 REST 字段混拼。事件帧的 `grant_available=false` 表示不可豁免高危工具（清空回收站/批量删任务/批量删资料/批量导入网页）——UI 不得展示「始终允许」，强行带 `grant_always` 会被 400 拒绝（re #019）。用户选择：
  - 批准：`POST /ai/actions/{action_id}/approve`（body 可选 `{"grant_always": true}` 建立始终允许规则）→ 响应给 `resume` URL → `POST /ai/conversations/{cid}/resume/stream` 开新流继续。
  - **同轮多个待批卡须逐张处理完再 resume**（re #020）：仍有未决卡时 resume 返回 400，响应体 `{"pending": [{"action_id", "tool_name"}]}` 列出未决清单（typed schema 见 openapi），前端据此提示用户逐张批准/拒绝。
  - **ready_to_resume**（re #023）：approve/reject 响应含 `ready_to_resume`——同一 run 批次内已无 pending（全部 confirmed/rejected/executed）时为 `true`；**前端只在 true 后才调 resume**，false 时继续等用户处理其余卡片。
  - **resume 消费幂等**（re #023）：resume 成功启动续跑后该批 confirmed 自动转 `executed`（卡片不再可决议）；同批**重复 resume 返回 400** typed `{"pending": [], "consumed": true, "message": "该批次已被消费，无可恢复审批"}`——不会重复回填/重复执行，前端收到 `consumed=true` 应直接刷新会话视图而非报错弹窗。
  - 拒绝：`POST /ai/actions/{action_id}/reject`，同样 resume 续跑（模型会收到"不得重试"约束）。
  - 已建立的始终允许规则可审计可撤销：`GET /ai/grants`（列表）、`DELETE /ai/grants/{id}`（204）。
- **计划模式**：`plan_card` 事件渲染计划卡；批准 `POST /ai/conversations/{cid}/plans/{plan_id}/approve`、拒绝 `/reject`（plan_id 仅会话内唯一，路径必须带会话）。
- **并发**：同一 conversation 同时只允许一个 run，冲突返回 **409**。取消幂等：`POST /ai/runs/{run_id}/cancel`（未知 run 返回 `ok:false` 不报错）。
- **附件**：先 `POST /ai/attachments`（multipart，返回 file_id；pdf/docx/xlsx/csv/txt 上传即解析，图片走视觉）→ 聊天带 `attachment_ids`。

## 5. UI 设计的非协商约束

1. **等待不沉默**：阶段跳变/心跳/token 增长/思维流，四个活性信号至少有一个永远在屏。
2. 工具调用必须可见（开始→参数→结果，可折叠），这是本产品与"聊天机器人"的本质区别。
3. 审批卡片是安全边界：confirm 级操作在用户点批准前不得显示为"已完成"。
4. `done` 帧是流的唯一权威终点——收到它之前 UI 保持"进行中"状态。

## 6. 已知边界（前端需感知）

- 上下文压缩当前为轮边界硬截断（长会话旧轮被裁剪，属正常）。
- `.doc` 老格式解析返回 unsupported（解析器会引导转换格式）。
- MCP 工具名形如 `mcp__{server_id}__{原名}`，工具卡片按 `__` 切分显示来源。
- 图片附件在不支持视觉的模型上会降级为文字提示。

## 7. 验收基线

后端已达成（真模型实测）：SSE 首事件 0.44s、课表导入 2 次工具调用、17 条课程全建零误杀、审批暂停/恢复正常、150s 长任务心跳无静默。前端联调时可按这些基线感知回归。
