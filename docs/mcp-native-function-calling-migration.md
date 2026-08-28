# 工具系统迁移至原生 Function-Calling 的分析与路线

> 状态：**迁移完成（阶段 1-7 全部上线）**。原生 function-calling 是唯一的工具调用方式，JSON-plan 路径已硬删。本文档保留作为迁移决策的历史记录。
>
> 最近更新：2026-07-23。本次随「Agent 体验对齐」一并落地：原生 function-calling 全量启用、危险操作拒绝能力（pending→rejected）、确认后回灌续跑（`POST /ai/chat/resume` 与 `/ai/chat/resume/stream`）、工具调用可视化卡片、Markdown 渲染（无 v-html）、按域刷新、SSE 流式（`/ai/chat/stream`）、中断链路（`/ai/chat/cancel` + 停止按钮）、上下文回放修复（`build_replay_messages` 按轮截断 + tool 链展开）、JSON-plan 路径硬删（`_run_plan_agent_loop`/`execute_plan_tools`/`has_valid_dangerous_actions`/`parse_assistant_plan`/plan prompt 段/设置 UI「兼容 JSON 模式」选项全部移除；`AIConfig.tool_calling_mode` 列保留但运行时忽略，免迁移）。

---

## 1. 现状：提示词驱动的 JSON plan

知时的 AI 工具调用**不是** OpenAI/Anthropic 原生 function-calling，而是一套自研的、provider 无关的方案：

1. **工具以文本写进 system prompt**：`ai_prompt_service.build_system_prompt` 把每个工具的名字、参数、用途用自然语言描述进提示词（见 `ai_prompt_service.py:84-135` 的「日程工具」「危险 action_type」段落，以及 `:121` 的低风险工具清单）。
2. **模型只输出一个 JSON 代码块**：prompt 强制要求 `{"reply":..., "plan":{...}, "tools":[{"name":..., "args":{}}], "dangerous_actions":[...], "done":bool}`。
3. **解析**：`ai_client.parse_assistant_plan` 从模型文本里抽出该 JSON（`ai.py:284`）。
4. **分发**：
   - `tools[]` → `execute_plan_tools` → `ai_tool_service.execute_tool`（白名单 `SAFE_TOOLS` 直接执行；`CONFIRMATION_REQUIRED_TOOLS` 拒绝直接执行）。
   - `dangerous_actions[]` → `ai_action_service.create_pending_action` 生成待确认动作，前端两段确认（`/ai/actions/{id}/confirm` → `/execute`）。
5. **Agent 循环**：`ai.py:run_agent_loop` 把工具结果拼成 observation 消息回喂模型，最多 `AGENT_MAX_STEPS=5` 轮。

关键文件：

| 职责 | 文件 |
|---|---|
| 工具清单（文本）+ 输出格式约束 | `backend/app/services/ai_prompt_service.py` |
| 请求构造（3 套 provider，无 `tools` 参数） | `backend/app/services/ai_client.py` |
| Agent 循环 + plan 解析入口 | `backend/app/routers/ai.py`（`run_agent_loop` / `execute_plan_tools`） |
| 工具执行白名单 | `backend/app/services/ai_tool_service.py` |
| 危险动作两段确认 | `backend/app/services/ai_action_service.py` |
| plan 解析 / 文本抽取 | `backend/app/services/ai_client.py`（`parse_assistant_plan` / `extract_text`） |

## 2. 原生 function-calling 是什么样

把工具以**结构化 schema** 传给模型，模型返回**结构化 tool_calls**，而不是模型自己吐 JSON 文本：

- **请求**里带 `tools` 参数（每家格式不同，见 §3）。
- **响应**里带 `tool_calls`（OpenAI）/ `tool_use`（Claude），含工具名 + 结构化参数。
- **结果回喂**用专门的 `tool` 角色 message（OpenAI）/ `tool_result` block（Claude）。
- 循环到模型不再发 tool_call、只给最终文本为止。

## 3. provider 差异（最大工作量来源）

当前三套 provider 各有**不同**的 tools 格式与响应结构，`ai_client.build_provider_request`（`ai_client.py:128-187`）现在三家 payload 都不含 `tools`：

| provider | 工具参数格式 | 模型返回 | 结果回喂 |
|---|---|---|---|
| `openai_chat` | `tools: [{"type":"function","function":{"name","description","parameters":<JSONSchema>}}]` | `choices[].message.tool_calls[].function.{name,arguments(JSON 字符串)}` | `{"role":"tool","tool_call_id":...,"content":...}` |
| `openai_responses` | `tools: [{"type":"function","name","description","parameters":...}]`（Responses API 形态，与 chat 不同） | `output[]` 里 `function_call` 项 | `{"type":"function_call_output","call_id":...,"output":...}` |
| `claude_messages` | `tools: [{"name","description","input_schema":<JSONSchema>}]` + 需配 `tool_choice` | `content[]` 里 `tool_use` block（含 `id`/`name`/`input`） | `{"role":"user","content":[{"type":"tool_result","tool_use_id":...,"content":...}]}` |

意味着原生方案要在 `ai_client` 里**三套分别实现**：工具 schema 序列化、tool_calls 解析、tool 结果消息构造。`_provider_messages` / `_provider_content` 现在只处理文本与附件，要扩展到 tool 消息。

## 4. 最大设计难点：危险动作两段确认

这是知时特有的安全层，**原生 function-calling 没有对应语义**。

- 现状：plan 里 `tools[]`（直接执行）和 `dangerous_actions[]`（需用户确认）是两个独立字段，模型在生成时就区分好「这个能直接干」「那个要先问用户」。
- 原生：所有工具调用长得一样（都是 tool_call），模型无法在协议层表达「这个要等人确认」。

**改造选项**：
- **A. 分发层闸门**：所有 tool_call 先到分发层，命中需确认集合（delete/update/bulk 等）时不执行，转成 pending action 并把「等待用户确认」作为 tool_result 回喂模型。需维护一份「工具 → 是否需确认」映射（类似现有 `CONFIRMATION_REQUIRED_TOOLS`，但要覆盖更全的危险集合）。
- **B. 双层工具**：把危险动作暴露成单独的「需确认工具」，让模型显式选择。破坏了「一个动作一个工具」的直观性，不推荐。
- **C. 保留 plan JSON 复合方案**：工具走原生 tool_calls，但危险动作仍让模型在文本里额外输出一个 `dangerous_actions` JSON 段。混合两套机制，复杂度最高。

推荐 **A**：分发层拦截 + pending action 复用现有 `ai_action_service` 两段确认管道。MCP 工具的「默认确认 / 只读免确认」也可挂在同一闸门上（按服务器 `auto_approve_readonly` + 工具 `readOnlyHint` 判定）。

## 5. 内置工具需要补正式 JSON Schema

现状 25 个内置工具只有 prompt 里的文字说明，没有机器可读的参数 schema。迁原生必须为每个工具定义 `input_schema`（参数类型、必填、枚举）。这是一份不小但机械的工作，建议提取到一个 `tool_registry`（每个工具：name / description / input_schema / safe_or_confirm / handler），同时成为 MCP 工具与内置工具的统一来源——也能顺带干掉 prompt 里那段冗长的工具文本。

## 6. 范围与风险

| 维度 | 评估 |
|---|---|
| 改动面 | `ai_client`（三套 provider tools + 解析）、`ai.py` Agent 循环、`ai_prompt_service`（去掉工具文本 + 输出格式）、新增 `tool_registry`、`ai_action_service`（确认闸门接入点） |
| 回归风险 | **高**：触及 chat / autopilot / 每日晨报 / 日报周报 / 危险确认等全部现有 AI 功能 |
| 收益 | 工具调用更稳（不依赖模型输出合法 JSON）、标准 schema、MCP 天然契合、多步 agent 更可靠 |
| 周期 | 粗估显著超过 MCP 任务本身；应作为独立里程碑，不与 MCP 耦合 |

## 7. 为什么「MCP 先按 JSON-plan 落地」是安全的踏脚石

- MCP 工具的 `inputSchema` **本身就是 JSON Schema**，与原生 function-calling 的 `parameters` / `input_schema` 完全同构 → 将来迁原生时，MCP 工具零改动即可挂上。
- 本次只新增 `mcp__s{id}__原名` 命名空间路由 + prompt 注入 + `mcp_tool_call` 危险动作类型，**不改动**现有内置工具与确认管道 → 回归面隔离在 MCP 自身。
- 迁原生时可先把 `tool_registry` 建起来，内置工具逐个迁，MCP 工具直接接入，最后切换 `ai_client` 的请求/响应处理。

## 8. 建议的迁移路线（独立里程碑）

1. **建 `tool_registry`**：把现有 25 个内置工具的 name/description/input_schema/safety/handler 落成单一数据源，`ai_tool_service` 与 prompt 都从它生成（此步即可回归验证，不碰 provider）。
2. **`ai_client` 加 tools 支持**：先 `openai_chat` 一家打通（tools 参数 + tool_calls 解析 + tool 结果消息），Agent 循环切换到原生路径，与 JSON-plan 路径并存、可开关。
3. **补 `claude_messages` 与 `openai_responses`** 两套适配。
4. **确认闸门接入分发层**（§4 方案 A）：tool_call 命中危险集合 → pending action → tool_result 回喂「等待确认」。
5. **MCP 工具接入 `tool_registry`**：移除 prompt 注入，改由 registry 统一序列化。
6. **下线 JSON-plan 路径**：确认全 provider、全功能稳定后删除 `parse_assistant_plan` 与 prompt 里的输出格式约束。

每步独立可验证、可回滚；第 2-3 步是最重的回归点。

## 9. 待确认问题

- 是否所有目标 provider 都需要原生支持？若只需 `openai_chat`（最通用，DeepSeek/通义/智谱/Kimi 都是它），工作量大幅下降，可只做一家。
- 是否接受「工具走原生、危险动作仍走 JSON 复合段」（§4-C）作为过渡？会降低一致性但缩短周期。
- 迁移期间是否保留 JSON-plan 作为 fallback 开关，还是一次性切换？
