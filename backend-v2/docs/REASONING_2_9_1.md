# v2.9.1 模型思考程度

入口：设置 → AI 模型 → 添加配置 / 编辑 → 模型能力 → 思考程度。

每个模型分别保存思考程度，旧配置默认“跟随服务商”。默认值不发送思考参数，避免使未声明支持该参数的兼容服务改变行为。选择档位后，聊天、审批续跑、子代理和单次生成使用同一模型配置；上下文摘要的配置快照保留档位。该设置调节模型推理投入，不承诺模型公开内部思考过程。

| 选择 | OpenAI Chat / Responses | Anthropic 原生 |
| --- | --- | --- |
| 跟随服务商 | 不指定参数 | 不指定参数 |
| 关闭 `none` | 显式 `none` | `thinking.type=disabled` |
| 极低 `minimal` | 显式 `minimal` | 不支持，保存前提示 |
| 低 / 中 / 高 / 很高 / 最高 | `low` / `medium` / `high` / `xhigh` / `max` | 同档位 effort，启用 adaptive thinking |

OpenAI Chat 映射为 `reasoning_effort`，Responses 映射为 `reasoning.effort`。Anthropic 使用 `thinking` 和 `output_config.effort`。可用档位由具体模型及服务商决定；兼容服务可能忽略或拒绝标准字段，旧 Anthropic 模型可能不支持 adaptive thinking。用户需要按服务商说明选择，程序不根据模型名称猜测，也不在服务报错后静默改档位。说明依据：[OpenAI reasoning](https://developers.openai.com/api/docs/guides/reasoning)、[OpenAI max 档位实例](https://developers.openai.com/api/docs/models/gpt-5.6-sol)、[Anthropic effort](https://platform.claude.com/docs/en/build-with-claude/effort)、[Anthropic thinking](https://platform.claude.com/docs/en/build-with-claude/thinking-steering-and-cost)。

更高档位通常需要更多时间与输出 token。思考 token 与回答共用最大输出限制，不能把“最高”理解成突破已设置的 token 上限。编辑可切回默认；保存失败保留草稿，切换到 Anthropic 时原有 minimal 不会静默变成其他档位。

数据库通过幂等补列迁移，旧记录保持默认。模型 API 返回新字段但不返回 Key，空白 Key 编辑继续保留凭据。使用本机模拟服务验证字段和原生界面，不使用用户真实密钥。

v2.9.0 的模型能力、上下文压缩、内置/Tavily/MCP 搜索与读取、原生图片与视觉 MCP 分流，以及此前悬浮窗、设置与提醒修复全部保留。媒体边界仍见 [v2.9.0 说明](MODELS_WEB_2_9_0.md)。

验证结果：后端 712 通过 / 2 跳过，前端 288 通过，桌面 9 通过，前端类型检查与生产构建通过。24 个协议/档位组合测试直接检查 SDK 发出的 HTTP 请求，包含默认省略字段、关闭与各档位；Anthropic minimal 在发送前明确拒绝。包内后端完成 7 项媒体/联网/思考参数/重启联调，测试凭据已删除并验证；2.9.0 → 2.9.1 的实际后端升级验证旧配置保留、档位编辑、重启和清除。

最终安装包：`release/desktop-2.9.1/zhishi-v2-Setup-2.9.1.exe`，137,380,219 字节，SHA256 `cded6795775868a12742c004f8f3203e2aec3667c9f34327768a8030f2c607af`。包内 1,482 个后端文件、4 个前端文件、10 个桌面文件与最终构建一致。原生桌面验收使用同次生成的 `win-unpacked`；未运行 NSIS 安装向导，未改动用户生产资料。证据见 `release/desktop-2.9.1/qa` 和 `verification.json`。

原生设置界面实际选择“低（low）”、保存并重启通过，旧模型默认档位、列表拉取、空白 Key 编辑、悬浮窗开关、联网配置也通过；界面截图已检查。最初一次验收的外层日志名与脚本重启日志重名，导致 Windows 文件锁错误；改用独立日志名后完整验收通过，应用代码无需修改。
